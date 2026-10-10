#!/usr/bin/env python3
"""Write runs/<run>/summary/report.html from summary/scores.json, in the 4Minds web style.

  ./bench graphrag-bench report_pilot eval make_report.py --run runs/2026-10-09_gemini-pilot
  ./bench graphrag-bench report eval make_report.py --run runs/<run>

The page is one file: inline CSS and logo, fonts from Typekit/Google Fonts (system fallback
when offline). Links to the audit files are relative to the summary folder.
"""
import argparse
import json
from html import escape
from pathlib import Path

import bench_common as bc
import run_readme
from report_html import SYSTEM_COLORS, bar, head, header, pct, quality_latency, rel, title_with_info

# From Evaluation/metrics/*.py and generation_eval.py at the pinned commit (judge and embeddings: see Method).
METRIC_HELP = {
    "rouge_score": (
        ["Word overlap with the gold answer: the longest sequence of words that both texts have in the same order "
         "(the words do not have to be next to each other). Words are stemmed. No LLM is used.",
         "The score is the F-measure of precision (the share of the answer in that sequence) and recall (the share of the "
         "gold answer in that sequence). It is 0 if one of the texts is empty.",
         "A correct answer with different words gets a low score."],
        "Evaluation/metrics/rouge.py: rouge_score RougeScorer('rougeL', use_stemmer=True), fmeasure"),
    "answer_correctness": (
        ["0.75 × factuality + 0.25 × semantic similarity.",
         "Factuality: the judge splits the answer and the gold answer into statements. It labels each answer statement as "
         "supported by the gold answer (TP) or not supported (FP), and each gold statement that the answer does not have as "
         "missing (FN). The score is F1 = TP / (TP + (FP + FN) / 2). If the judge output is not valid JSON, factuality is 0.",
         "Semantic similarity: the cosine similarity of the embeddings of the two texts, scaled to 0–1 as (cosine + 1) / 2. "
         "This part is almost never below 0.5, so it raises all scores a little."],
        "Evaluation/metrics/answer_accuracy.py: compute_answer_correctness, weights [0.75, 0.25], beta 1"),
    "coverage_score": (
        ["The share of the gold answer's facts that the answer contains (recall).",
         "The judge splits the gold answer (first 3,000 characters) into facts. Then it marks each fact as covered (1) or "
         "not covered (0) by the answer (first 3,000 characters). Score = covered facts / all facts.",
         "Extra or wrong content in the answer does not decrease the score. If the judge output cannot be parsed, the "
         "score is NaN and is not in the mean."],
        "Evaluation/metrics/coverage.py: compute_coverage_score"),
    "faithfulness": (
        ["The share of the answer's statements that the retrieved context supports. The gold answer is not used.",
         "The judge splits the answer (first 3,000 characters) into statements. Then it gives each statement a verdict, 1 "
         "or 0, against the context that the system returned (first 10,000 characters). No context gives 0.",
         "A correct answer from the model's own knowledge, without support in the context, gets a low score.",
         "At this commit the verdict prompt does not ask for JSON, so most verdicts cannot be parsed and the score is NaN."],
        "Evaluation/metrics/faithfulness.py: compute_faithfulness_score"),
    "faithfulness_jsonfix": (
        ["The same code, judge, context limit and answers as Faithfulness (official), with one sentence added to the end "
         "of the verdict prompt. The sentence asks for the JSON format of the prompt's own examples.",
         "Not part of the official protocol. The diff is in audit/patches/faithfulness-fdbab59-json-format.diff."],
        "score_faithfulness.py (this repo)"),
}

# Levels and metric sets: upstream README.md and generation_eval.py. Medians: data/Questions/medical_questions.json.
TYPE_HELP = {
    "Fact Retrieval": [
        "Level 1 of 4. The question asks for one fact, which is usually in one location in the corpus.",
        "Gold answers are short: median 10 words, 2 evidence statements (1,098 questions in the Medical set).",
        "Example: \"Are organ transplant recipients at higher risk for BCC?\""],
    "Complex Reasoning": [
        "Level 2 of 4. The answer must connect facts from different locations (multi-hop) to explain a relation or a cause.",
        "Gold answers: median 17 words, 3 evidence statements (509 questions).",
        "Example: \"How does the presence of a lung nodule on imaging affect the diagnostic workflow for lung cancer?\""],
    "Contextual Summarize": [
        "Level 3 of 4. The answer must collect the related facts about one topic and summarize them.",
        "Gold answers: median 29 words, 5 evidence statements (289 questions).",
        "Example: \"What assessments and counseling are recommended for patients with nasopharyngeal carcinoma (NPC) prior "
        "to treatment?\""],
    "Creative Generation": [
        "Level 4 of 4. The answer is a new text in a given role or format (for example an advisory or an article). It must "
        "still contain the facts from the corpus.",
        "Gold answers: median 120 words, 13 evidence statements (166 questions).",
        "Example: \"As a public health officer, draft a community health advisory on lung cancer prevention and early "
        "detection...\""],
}

TYPE_METRIC_NOTE = {
    ("Fact Retrieval", "rouge_score"):
        "The gold answer is short. A correct answer that adds more detail has low precision, so its score decreases.",
    ("Fact Retrieval", "answer_correctness"):
        "The gold answer has few statements. One missing or one extra statement changes the factuality part by a large "
        "amount.",
    ("Complex Reasoning", "rouge_score"):
        "There are many correct ways to explain a relation. An answer that uses different words or a different order of "
        "steps gets a low score.",
    ("Complex Reasoning", "answer_correctness"):
        "The judge checks each step of the explanation. A correct conclusion with a missing step gets a missing (FN) "
        "statement.",
    ("Contextual Summarize", "answer_correctness"):
        "The gold summary has many statements. Each fact that the answer leaves out is FN. Each true fact that is not in "
        "the gold summary is FP.",
    ("Contextual Summarize", "coverage_score"):
        "This metric shows how complete the summary is. A long answer that includes all gold facts gets a high score, "
        "also if it contains extra text.",
    ("Creative Generation", "answer_correctness"):
        "Creative text contains framing and style statements that are not in the gold answer. The judge can label them "
        "FP, and this decreases the factuality part.",
    ("Creative Generation", "coverage_score"):
        "The gold answer has many facts. The judge reads only the first 3,000 characters of the answer, so it does not "
        "count facts after that point in a long answer.",
    ("Creative Generation", "faithfulness"):
        "Only this type uses this metric. It checks that the creative text does not add facts that the retrieved sources "
        "do not support.",
    ("Creative Generation", "faithfulness_jsonfix"):
        "Only this type uses this metric. It checks that the creative text does not add facts that the retrieved sources "
        "do not support.",
}


def card_help(qt, metric):
    """Tooltip blocks for one card: the question type, the metric on this type, then the metric."""
    paragraphs, source = METRIC_HELP[metric]
    blocks = [(f"Question type: {qt}", TYPE_HELP[qt])] if qt in TYPE_HELP else []
    if (qt, metric) in TYPE_METRIC_NOTE:
        blocks.append(("On this question type", [TYPE_METRIC_NOTE[(qt, metric)]]))
    return blocks + [("Metric", paragraphs)], source


def diff_bar(name, sub, r, color, span=0.5):
    if not r:
        return ""
    pos = lambda v: max(0.0, min(100.0, 50 + v / span * 50))
    d = r["diff_mean"]
    left, right = sorted((pos(0), pos(d)))
    cls = "pos" if r["ci_low"] > 0 else "neg" if r["ci_high"] < 0 else "neutral"
    verdict = ("4Minds higher" if cls == "pos" else "4Minds lower" if cls == "neg" else "no clear difference")
    return (f'<div class="bar-row"><div class="bar-name">{escape(name)}<small>{escape(sub)}</small></div>'
            f'<div class="track"><div class="zero"></div><div class="fill" style="left:{left:.2f}%;width:{right - left:.2f}%;'
            f'background:{color}"></div><div class="ci" style="left:{pos(r["ci_low"]):.2f}%;'
            f'width:{pos(r["ci_high"]) - pos(r["ci_low"]):.2f}%"></div></div>'
            f'<div class="val {cls}">{d * 100:+.1f}<small>{pct(r["ci_low"])} to {pct(r["ci_high"])} · {verdict}</small></div></div>')


def build(out, timing, summary_dir):
    systems = out["systems"]
    names = {s["key"]: s["name"] for s in systems}
    colors = {s["key"]: s.get("color") or SYSTEM_COLORS.get(s["key"], "#80aeff") for s in systems}
    color = colors.get
    label = out.get("label") or ""
    snapshots = ", ".join(out["benchmark"]["judge_snapshot"]) or out["benchmark"]["judge"]
    commit = ", ".join(c[:7] for c in out["benchmark"]["commit"]) or bc.UPSTREAM_COMMIT[:7]
    n_questions = max((s["operations"].get("questions") or 0) for s in systems) if systems else 0
    ranked = sorted(systems, key=lambda s: -((out["overall"][s["key"]]["answer_correctness"] or {}).get("mean") or 0))

    h = head(f"GraphRAG-Bench Medical{(' · ' + escape(label)) if label else ''} · 4Minds")
    h.append(header(f"Generated {escape(out['generated'])}<br>GraphRAG-Bench commit {escape(commit)}"))

    h.append("<div class='label'>Benchmark report</div>")
    h.append(f"<h1>GraphRAG-Bench · Medical{(' · ' + escape(label)) if label else ''}</h1>")
    h.append("<p class='lead'>Does 4Minds give answers of similar quality to the RAG systems that customers already use? "
             f"All systems answered the same {n_questions} medical questions over the same source text. The official "
             "GraphRAG-Bench scorer graded every answer against the gold answer.</p>")
    h.append(f"<span class='pill'>Judge {escape(snapshots)}</span><span class='pill'>Embeddings {escape(out['benchmark']['embedding_model'])}</span>"
             f"<span class='pill'>Generation metrics only</span>")
    if label:
        h.append(f"<span class='pill warn'>{escape(label)}: small sample, wide confidence intervals. Do not use for conclusions.</span>")

    h.append("<section><div class='label'>Headline</div><h2>Answer correctness, all questions</h2>"
             "<p class='sub'>The official answer-correctness metric (0–100): the judge's factual agreement with the gold answer, "
             "combined with semantic similarity. Bars show the mean; the white whisker is the 95% bootstrap confidence interval.</p>"
             "<div class='card'>")
    for s in ranked:
        h.append(bar(s["name"], s["description"].split(",")[0], out["overall"][s["key"]]["answer_correctness"], color(s["key"])))
    h.append("</div></section>")

    points = []
    for s in ranked:
        r, lat = out["overall"][s["key"]]["answer_correctness"] or {}, s["operations"].get("latency") or {}
        cost = s["operations"].get("estimated_cost_usd")
        points.append({"key": s["key"], "name": s["name"], "quality": r.get("mean"), "quality_low": r.get("ci_low"),
                       "quality_high": r.get("ci_high"), "latency": lat.get("median_s"), "latency_p90": lat.get("p90_s"),
                       "hover": [f"Est. cost: {'n/a (subscription)' if cost is None else f'${cost:.3f}'}"]})
    h.append("<section><div class='label'>Quality and speed</div><h2>Answer correctness and latency</h2>"
             "<p class='sub'>One point for each system: answer correctness and the median latency per question. Move the "
             "pointer over a point for the 95% confidence interval, the 90th-percentile latency and the cost.</p>"
             "<div class='card'>")
    h.append(quality_latency("quality-latency", points, "Answer correctness"))
    h.append(f"<p class='note'>With {n_questions} questions the confidence intervals overlap (see the headline chart). "
             "Latency depends on the number of workers, the network and the load on each service during the run (see "
             "Operations).</p></div></section>")

    if out.get("paired"):
        ref = names.get(out["reference_system"], out["reference_system"])
        h.append(f"<section><div class='label'>Head to head</div><h2>{escape(ref)} compared with each system</h2>"
                 "<p class='sub'>Paired difference in answer correctness on the same questions (points, 0–100 scale). "
                 "Right of the center line means 4Minds scored higher. When the whisker crosses the line, the data does not "
                 "show a clear difference.</p><div class='card'>")
        for other, by_type in out["paired"].items():
            h.append(diff_bar(names[other], "All questions", by_type.get("All questions", {}).get("answer_correctness"), color(other)))
        h.append("</div></section>")

    h.append("<section><div class='label'>By question type</div><h2>Official metrics per question type</h2>"
             "<p class='sub'>GraphRAG-Bench uses a different metric set for each question type. Faithfulness (Creative Generation) "
             "reads the retrieved context that each system returns.</p><div class='grid'>")
    for qt in out["types"]:
        for metric in out["metric_set"][qt]:
            title = f"{qt} · {out['metric_names'][metric]}"
            title = title_with_info(title, *card_help(qt, metric)) if metric in METRIC_HELP else escape(title)
            h.append(f"<div class='card'><h3>{title}</h3>")
            for s in systems:
                r = out["metrics"][s["key"]][qt].get(metric)
                if metric.startswith("faithfulness") and not s.get("faithfulness_available"):
                    h.append(bar(s["name"], "no retrieved context returned", None, color(s["key"])))
                elif metric == "faithfulness":
                    h.append(bar(s["name"], f"NaN for {s.get('faithfulness_official_nan')}/"
                                 f"{s.get('faithfulness_items')} answers", r, color(s["key"])))
                else:
                    h.append(bar(s["name"], "", r, color(s["key"])))
            if metric == "faithfulness":
                h.append(f"<p class='note'>The official verdict prompt does not ask for JSON; "
                         f"{escape(out['benchmark']['judge'])} can answer in prose, and those answers score NaN. "
                         "See the caveats.</p>")
            elif metric == "faithfulness_jsonfix":
                h.append("<p class='note'>Not part of the official protocol: the same code and judge with one "
                         "sentence that asks for JSON output.</p>")
            h.append("</div>")
    h.append("</div></section>")

    if out.get("paired"):
        h.append("<section><div class='label'>Detail</div><h2>Paired differences per type and metric</h2>"
                 f"<p class='sub'>{escape(names.get(out['reference_system'], ''))} minus the other system, in points. "
                 "Green: 4Minds higher with 95% confidence. "
                 "Red: 4Minds lower with 95% confidence. Grey: no clear difference.</p><div class='card'><table>"
                 "<tr><th>Compared with</th><th>Question type</th><th>Metric</th><th>Difference</th><th>95% CI</th><th>n</th></tr>")
        for other, by_type in out["paired"].items():
            for qt, by_metric in by_type.items():
                for metric, r in by_metric.items():
                    if not r:
                        continue
                    cls = "pos" if r["ci_low"] > 0 else "neg" if r["ci_high"] < 0 else "neutral"
                    h.append(f"<tr><td><span class='dot' style='background:{color(other)}'></span>{escape(names[other])}</td>"
                             f"<td>{escape(qt)}</td><td>{escape(out['metric_names'][metric])}</td>"
                             f"<td class='{cls}'>{r['diff_mean'] * 100:+.1f}</td><td>{pct(r['ci_low'])} to {pct(r['ci_high'])}</td>"
                             f"<td>{r['n']}</td></tr>")
        h.append("</table></div></section>")

    for check in out.get("sensitivity", []):
        h.append(f"<section><div class='label'>Sensitivity check</div><h2>{escape(check['name'])}</h2>"
                 f"<p class='sub'>{escape(check['description'])} Excluded for all systems: {check['n_excluded']} "
                 f"{escape(check['rule_description'])}.</p><div class='card'><table>"
                 f"<tr><th>System</th><th>Answer correctness</th><th>95% CI</th><th>n</th>"
                 f"<th>{escape(names.get(out['reference_system'], ''))} minus system</th><th>95% CI</th></tr>")
        for s in systems:
            r, p = check["overall"].get(s["key"]), check["paired"].get(s["key"])
            diff = (f"<td>{p['diff_mean'] * 100:+.1f}</td><td>{pct(p['ci_low'])} to {pct(p['ci_high'])}</td>" if p
                    else "<td>(reference)</td><td></td>" if s["key"] == out["reference_system"] else "<td>n/a</td><td></td>")
            h.append(f"<tr><td><span class='dot' style='background:{color(s['key'])}'></span>{escape(s['name'])}</td>"
                     + (f"<td>{pct(r['mean'])}</td><td>{pct(r['ci_low'])} to {pct(r['ci_high'])}</td><td>{r['n']}</td>"
                        if r else "<td>n/a</td><td></td><td></td>") + diff + "</tr>")
        h.append("</table></div></section>")

    h.append("<section><div class='label'>Operations</div><h2>Reliability, latency and cost</h2>"
             "<p class='sub'>From the run manifests. Cost is the estimated model cost for answering (list prices), not the index "
             "build; 4Minds is a subscription, so no per-question cost is shown. Not scored: answers that the judge "
             "could not score; they are not in the means.</p><div class='card'><table>"
             "<tr><th>System</th><th>Answered</th><th>Failed</th><th>Not scored</th><th>“I don't know”</th>"
             "<th>Latency median / p90 (s)</th>"
             "<th>Est. cost (USD)</th><th>Run</th></tr>")
    for s in systems:
        o, lat = s["operations"], s["operations"].get("latency") or {}
        cost = o.get("estimated_cost_usd")
        h.append(f"<tr><td><span class='dot' style='background:{color(s['key'])}'></span>{escape(s['name'])}</td>"
                 f"<td>{o.get('answered')}/{o.get('questions')}</td><td>{o.get('failed')}</td>"
                 f"<td>{(s.get('scoring') or {}).get('failed_samples', 'n/a')}</td><td>{o.get('dont_know')}</td>"
                 f"<td>{lat.get('median_s', 'n/a')} / {lat.get('p90_s', 'n/a')}</td>"
                 f"<td>{'n/a' if cost is None else f'{cost:.3f}'}</td>"
                 f"<td><small>{escape(str(s.get('run_started') or ''))}<br>workers {o.get('workers')}</small></td></tr>")
    h.append("</table></div></section>")

    if timing:
        h.append("<section><div class='label'>Planning</div><h2>Full-run time estimate</h2>"
                 f"<p class='sub'>{escape(timing.get('method', ''))}</p><div class='card'><table>"
                 "<tr><th>System</th><th>Index build</th><th>Mean latency (s)</th><th>Workers</th><th>Est. answering time, 2,062 questions</th>"
                 "<th>Est. scoring time</th><th>Est. answer cost (USD)</th></tr>")
        for key, t in timing.get("systems", {}).items():
            h.append(f"<tr><td><span class='dot' style='background:{color(key)}'></span>{escape(names.get(key, key))}</td>"
                     f"<td>{escape(str(t.get('index_build', 'n/a')))}</td><td>{t.get('mean_latency_s', 'n/a')}</td>"
                     f"<td>{t.get('workers', 'n/a')}</td><td>{t.get('est_full_answer_h', 'n/a')} h</td>"
                     f"<td>{t.get('est_full_score_h', 'n/a')} h</td><td>{t.get('est_full_cost_usd', 'n/a')}</td></tr>")
        h.append(f"</table><p class='sub' style='margin:20px 0 0'>{escape(timing.get('total', ''))}</p></div></section>")

    h.append("<section><div class='label'>Method</div><h2>How the benchmark ran</h2><div class='grid'>")
    h.append("<div class='card'><h3>Protocol</h3><ul class='caveats'>"
             f"<li>Dataset: GraphRAG-Bench, Medical subset (official repo, commit {escape(commit)}).</li>"
             "<li>Every system got the same source text and the official system prompt.</li>"
             f"<li>Scoring: the official <code>Evaluation/generation_eval.py</code>, judge {escape(snapshots)}, "
             f"embeddings {escape(out['benchmark']['embedding_model'])}, temperature 0, seed 42.</li>"
             f"<li>Confidence intervals: {out['benchmark']['bootstrap_resamples']} bootstrap resamples per number; paired "
             "bootstrap for the differences.</li>"
             "<li>No system answered a question before its index build was complete (a readiness check gates each run).</li></ul></div>")
    h.append("<div class='card'><h3>Systems</h3><ul class='caveats'>")
    for s in systems:
        h.append(f"<li><span class='dot' style='background:{color(s['key'])}'></span><strong style='font-weight:500'>"
                 f"{escape(s['name'])}</strong>: {escape(s['description'])}.</li>")
    h.append("</ul></div></div></section>")

    h.append("<section><div class='label'>Read before you share</div><h2>Notes and caveats</h2><div class='card'><ul class='caveats'>")
    h += [f"<li>{escape(c)}</li>" for c in out["caveats"]]
    h.append("</ul></div></section>")

    root = Path(out["results_root"])
    links = [("Summary data (JSON)", summary_dir / "scores.json"), ("Scores (CSV)", summary_dir / "scores.csv"),
             ("Paired differences (CSV)", summary_dir / "paired.csv"), ("Audit log (JSON lines)", bc.AUDIT_DIR / "audit.log"),
             ("Step logs", bc.AUDIT_DIR / "steps"), ("LightRAG patch", bc.AUDIT_DIR / "patches")]
    for s in systems:
        folder = Path(s["folder"])
        links += [(f"{s['name']}: run manifest", folder / "manifest.json"),
                  (f"{s['name']}: predictions", folder / "predictions.json"),
                  (f"{s['name']}: per-question scores", folder / "generation_scores.json")]
    h.append("<section><div class='label'>Audit trail</div><h2>Files</h2><p class='sub'>Every run, retry, readiness check and "
             "score step is logged. Links are relative to this report.</p><div class='card'><table>")
    h += [f"<tr><td>{escape(n)}</td><td><a href='{escape(rel(p, summary_dir))}'>{escape(rel(p, root.parent))}</a></td></tr>"
          for n, p in links if p.exists()]
    h.append("</table></div></section>")
    h.append(f"<footer>4Minds · GraphRAG-Bench Medical{(' · ' + escape(label)) if label else ''} · generated by make_report.py "
             f"from {escape(rel(summary_dir / 'scores.json', root.parent))}</footer></div></body></html>")
    return "\n".join(h)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", "--results", dest="results", required=True, help="run folder, for example runs/<YYYY-MM-DD>_<name>")
    args = parser.parse_args()
    root = Path(args.results).resolve()
    summary_dir = root / "summary"
    out = json.loads((summary_dir / "scores.json").read_text())
    timing_file = root / "timing.json"
    timing = json.loads(timing_file.read_text()) if timing_file.exists() else None
    target = summary_dir / "report.html"
    target.write_text(build(out, timing, summary_dir))
    run_readme.write(summary_dir.parent)
    bc.audit("report_html", path=str(target), sha256=bc.sha256(target))
    print(f"wrote {target}")


if __name__ == "__main__":
    main()

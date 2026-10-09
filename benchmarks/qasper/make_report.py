#!/usr/bin/env python3
"""Write <results>/summary/report.html from summary/scores.json, in the 4Minds web style.

    ./bench qasper report_pilot eval make_report.py --results results/pilot

Run aggregate.py first. Links to the audit files are relative to the summary folder.
"""
import argparse
import json
from html import escape
from pathlib import Path

import bench_common as bc
from report_html import SYSTEM_COLORS, bar, head, header, pct, quality_latency, rel

TYPES = {"extractive": "Extractive", "abstractive": "Abstractive", "boolean": "Yes/No", "none": "Unanswerable"}
DESCRIPTIONS = {
    "4minds_constellations": "4Minds prod, Constellations engine (WebSocket), model GPT-OSS-120B, chunk-level graph",
    "4minds_symi": "4Minds prod, SYMI engine (REST/SSE), model GPT-OSS-120B, same dataset and persona",
    "gemini": "Gemini 3.8 Flash with Gemini File Search (Interactions API), top-k 5; the model decides how many searches to make",
    "rag_engine": "Gemini 3.8 Flash with Vertex AI RAG Engine (europe-west4, Spanner Basic), top-k 5",
    "lightrag": "LightRAG 1.2.5 with Gemini 3.8 Flash, hybrid mode, top-k 5, bge-large-en-v1.5 embeddings",
}
INGESTION = [
    ("4minds_constellations", "4Minds (both engines)", "4minds/setup.json", "wait_wall_clock_s", None),
    ("gemini", "Gemini File Search", "gemini/setup.json", "setup_wall_clock_s", None),
    ("lightrag", "LightRAG + Gemini", "lightrag/workspace/qasper-test-pilot/index_manifest.json", "index_wall_clock_s",
     "estimated_cost_usd"),
]


def ingestion_rows(results_root):
    rows = []
    for key, name, path, seconds_field, cost_field in INGESTION:
        file = results_root / path
        data = json.loads(file.read_text()) if file.exists() else {}
        cost = data.get(cost_field) if cost_field else None
        rows.append((key, name, data.get(seconds_field), cost, file))
    return rows


def build(out, summary_dir, results_root):
    systems = out["systems"]
    ranked = sorted(systems.items(), key=lambda kv: -kv[1]["answer_f1"])
    color = lambda k: SYSTEM_COLORS.get(k, "#80aeff")
    label = out.get("label") or ""
    n_questions = max((s["questions"] for s in systems.values()), default=0)
    manifest = json.loads((bc.BENCH_DIR / "data" / "pilot_manifest.json").read_text())

    h = head(f"QASPER{(' · ' + escape(label)) if label else ''} · 4Minds")
    h.append(header(f"Generated {escape(out['created'])}<br>QASPER v0.3 test release, official evaluator"))

    h.append("<div class='label'>Benchmark report</div>")
    h.append(f"<h1>QASPER{(' · ' + escape(label)) if label else ''}</h1>")
    h.append("<p class='lead'>Does 4Minds give answers of similar quality to the RAG systems that customers already use? "
             f"All systems answered the same {n_questions} questions about NLP research papers, from the same knowledge base. "
             "The official QASPER evaluator scored every answer against the reference answers.</p>")
    h.append("<span class='pill'>Official evaluator, unchanged</span><span class='pill'>Answer F1 only</span>"
             "<span class='pill'>No retrieval metrics</span>")
    if label:
        h.append(f"<span class='pill warn'>{escape(label)}: small sample, wide confidence intervals. Do not use for conclusions.</span>")

    h.append("<section><div class='label'>Headline</div><h2>Answer F1, all questions</h2>"
             "<p class='sub'>Token overlap (SQuAD F1, 0–100) between the answer and the best-matching reference answer. "
             "Bars show the mean; the white whisker is the 95% bootstrap confidence interval.</p><div class='card'>")
    for name, s in ranked:
        r = {"mean": s["answer_f1"], "ci_low": s["ci95"][0], "ci_high": s["ci95"][1], "n": s["questions"]}
        h.append(bar(name, DESCRIPTIONS.get(s["key"], "").split(",")[0], r, color(s["key"])))
    for name, reason in out.get("not_scored", {}).items():
        h.append(bar(name, "not scored (see below)", None, "#5eead4"))
    h.append("</div></section>")

    points = []
    for name, s in ranked:
        lat, cost = s["operations"].get("latency") or {}, s["operations"].get("estimated_cost_usd")
        points.append({"key": s["key"], "name": name, "quality": s["answer_f1"], "quality_low": s["ci95"][0],
                       "quality_high": s["ci95"][1], "latency": lat.get("median_s"), "latency_p90": lat.get("p90_s"),
                       "hover": [f"Est. cost: {'n/a (subscription)' if cost is None else f'${cost:.2f}'}",
                                 f"Median answer words: {s['answer_words_median']}"]})
    h.append("<section><div class='label'>Quality and speed</div><h2>Answer F1 and latency</h2>"
             "<p class='sub'>One point for each system: Answer F1 and the median latency per question. Move the pointer "
             "over a point for the 95% confidence interval, the 90th-percentile latency and the cost.</p><div class='card'>")
    h.append(quality_latency("quality-latency", points, "Answer F1"))
    h.append(f"<p class='note'>With {n_questions} questions the confidence intervals overlap (see the headline chart). "
             "Latency depends on the number of workers, the network and the load on each service during the run (see "
             "Operations).</p></div></section>")

    if out.get("not_scored"):
        h.append("<section><div class='label'>Not scored</div><h2>Systems without a result</h2><div class='card'><ul class='caveats'>")
        h += [f"<li><strong style='font-weight:500'>{escape(n)}</strong>: {escape(reason)}</li>"
              for n, reason in out["not_scored"].items()]
        h.append("</ul></div></section>")

    h.append("<section><div class='label'>By answer type</div><h2>Answer F1 per answer type</h2>"
             "<p class='sub'>The type of the best-matching reference (official rule). Each type has only 3 to 15 questions "
             "in this pilot, so one question changes a score by many points.</p><div class='card'><table><tr><th>System</th>"
             + "".join(f"<th>{t}</th>" for t in TYPES.values()) + "</tr>")
    for name, s in ranked:
        cells = "".join(f"<td>{pct(s['by_type'][t]['answer_f1'])} <small>n={s['by_type'][t]['n']}</small></td>" for t in TYPES)
        h.append(f"<tr><td><span class='dot' style='background:{color(s['key'])}'></span>{escape(name)}</td>{cells}</tr>")
    h.append("</table></div></section>")

    h.append("<section><div class='label'>Answer style</div><h2>Answer length</h2>"
             "<p class='sub'>Answer F1 is token overlap, so a long answer gets a low score even when it is correct. "
             "Compare the length before you compare the scores.</p><div class='card'><table>"
             "<tr><th>System</th><th>Median words</th><th>Maximum words</th><th>Answered “Unanswerable”</th></tr>")
    for name, s in ranked:
        h.append(f"<tr><td><span class='dot' style='background:{color(s['key'])}'></span>{escape(name)}</td>"
                 f"<td>{s['answer_words_median']}</td><td>{s['answer_words_max']}</td>"
                 f"<td>{s['answered_unanswerable']}/{s['questions']}</td></tr>")
    h.append("</table></div></section>")

    h.append("<section><div class='label'>Operations</div><h2>Reliability, latency and cost</h2>"
             "<p class='sub'>From the run manifests. Cost is the estimated model cost for answering (list prices); "
             "4Minds is a subscription, so no per-question cost is shown.</p><div class='card'><table>"
             "<tr><th>System</th><th>Answered</th><th>Failed</th><th>Latency median / p90 (s)</th>"
             "<th>Est. cost (USD)</th><th>Run</th></tr>")
    for name, s in ranked:
        o, lat = s["operations"], s["operations"].get("latency") or {}
        cost = o.get("estimated_cost_usd")
        h.append(f"<tr><td><span class='dot' style='background:{color(s['key'])}'></span>{escape(name)}</td>"
                 f"<td>{o.get('answered')}/{o.get('questions')}</td><td>{o.get('failed')}</td>"
                 f"<td>{lat.get('median_s', 'n/a')} / {lat.get('p90_s', 'n/a')}</td>"
                 f"<td>{'n/a' if cost is None else f'{cost:.3f}'}</td>"
                 f"<td><small>{escape(str(s.get('run_started') or ''))}<br>workers {o.get('workers')}</small></td></tr>")
    h.append("</table><p class='note'>Gemini File Search made a median of 5 searches per question (maximum 17), "
             "so its latency and cost are higher.</p></div></section>")

    h.append("<section><div class='label'>Ingestion</div><h2>Time to load the corpus</h2>"
             "<p class='sub'>From the setup and index files. The time from the start of the upload until the "
             "system reported that it was ready.</p><div class='card'><table>"
             "<tr><th>System</th><th>Time (s)</th><th>Est. cost (USD)</th></tr>")
    for key, name, seconds, cost, _ in ingestion_rows(results_root.parent):
        h.append(f"<tr><td><span class='dot' style='background:{color(key)}'></span>{escape(name)}</td>"
                 f"<td>{seconds if seconds is not None else 'n/a'}</td><td>{'n/a' if cost is None else f'{cost:.3f}'}</td></tr>")
    h.append("</table></div></section>")

    h.append("<section><div class='label'>Method</div><h2>How the benchmark ran</h2><div class='grid'>")
    h.append("<div class='card'><h3>Protocol</h3><ul class='caveats'>"
             f"<li>Dataset: QASPER v0.3 test release ({manifest['test_papers']} papers, {manifest['test_questions']} questions). "
             f"Pilot: {n_questions} questions, 1 per paper, stratified by answer type, seed {manifest['seed']}.</li>"
             f"<li>Corpus: the {len(manifest['question_papers'])} question papers plus {len(manifest['distractor_papers'])} "
             f"other test papers ({manifest['corpus_papers']} papers, {manifest['corpus_chars']:,} characters), in one text file.</li>"
             "<li>Every system got the same corpus and the same system prompt.</li>"
             "<li>Each query names its paper: <code>In the paper \"&lt;title&gt;\": &lt;question&gt;</code>.</li>"
             "<li>Scoring: the official <code>qasper_evaluator.py</code>, unchanged, on a gold file with only the pilot questions.</li>"
             "<li>No system answered a question before its ingestion was complete (a readiness check gates each run).</li></ul></div>")
    h.append("<div class='card'><h3>Systems</h3><ul class='caveats'>")
    for name, s in ranked:
        h.append(f"<li><span class='dot' style='background:{color(s['key'])}'></span><strong style='font-weight:500'>"
                 f"{escape(name)}</strong>: {escape(DESCRIPTIONS.get(s['key'], ''))}.</li>")
    h.append("</ul></div></div></section>")

    h.append("<section><div class='label'>Read before you share</div><h2>Notes and caveats</h2><div class='card'><ul class='caveats'>")
    h += [f"<li>{escape(c)}</li>" for c in out["caveats"]]
    h.append("</ul></div></section>")

    links = [("Summary data (JSON)", summary_dir / "scores.json"), ("Summary (Markdown)", summary_dir / "report.md"),
             ("Pilot manifest", bc.BENCH_DIR / "data" / "pilot_manifest.json"),
             ("Audit log (JSON lines)", bc.AUDIT_DIR / "audit.log"), ("Step logs", bc.AUDIT_DIR / "steps")]
    for name, s in ranked:
        folder = Path(s["folder"])
        links += [(f"{name}: run manifest", folder / "manifest.json"),
                  (f"{name}: predictions", folder / "predictions.json"),
                  (f"{name}: per-question scores", folder / "per_question.jsonl")]
    links += [(f"{name}: ingestion", file) for _, name, _, _, file in ingestion_rows(results_root.parent)]
    h.append("<section><div class='label'>Audit trail</div><h2>Files</h2><p class='sub'>Every run, retry, readiness check and "
             "score step is logged. Links are relative to this report.</p><div class='card'><table>")
    h += [f"<tr><td>{escape(n)}</td><td><a href='{escape(rel(p, summary_dir))}'>{escape(rel(p, bc.BENCH_DIR))}</a></td></tr>"
          for n, p in links if p.exists()]
    h.append("</table></div></section>")
    h.append(f"<footer>4Minds · QASPER{(' · ' + escape(label)) if label else ''} · generated by make_report.py "
             f"from {escape(rel(summary_dir / 'scores.json', bc.BENCH_DIR))}</footer></div></body></html>")
    return "\n".join(h)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", required=True)
    args = parser.parse_args()
    root = Path(args.results).resolve()
    summary_dir = root / "summary"
    out = json.loads((summary_dir / "scores.json").read_text())
    target = summary_dir / "report.html"
    target.write_text(build(out, summary_dir, root))
    bc.audit("report_html", path=str(target), sha256=bc.sha256(target))
    print(f"wrote {target}")


if __name__ == "__main__":
    main()

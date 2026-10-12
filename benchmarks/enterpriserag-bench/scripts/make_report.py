#!/usr/bin/env python3
"""Write runs/<run>/summary/report.html from summary/scores.json, in the 4Minds web style.

    ./bench enterpriserag-bench report_pilot eval make_report.py --run runs/2026-10-10_gptoss-pilot

Run aggregate.py first. The systems (names, colors, descriptions, ingestion files) come from the
comparison file copy in runs/<run>/config.json. Links to the audit files are relative to the summary folder.
"""
import argparse
import json
from html import escape
from pathlib import Path

import answers_page
import bench_common as bc
import run_readme
from report_html import DOWNLOAD_BUTTON, bar, download_bar, download_script, head, header, pct, quality_latency, rel, tabs

METRICS = [("average_correctness_pct", "Correctness"), ("average_completeness_pct", "Completeness"),
           ("average_recall_pct", "Recall"), ("average_invalid_extra_docs", "Invalid extra docs")]


def ci(s):
    return {"mean": s["official"]["overall_score"] / 100, "ci_low": s["overall_ci95"][0] / 100,
            "ci_high": s["overall_ci95"][1] / 100, "n": s["scored_questions"]}


def ingestion_rows(specs):
    rows = []
    for spec in specs:
        info = spec.get("ingestion")
        if not info:
            continue
        file = bc.BENCH_DIR / info["file"]
        data = json.loads(file.read_text()) if file.exists() else {}
        rows.append((spec, data.get(info["seconds"]), data.get(info["cost"]) if info.get("cost") else None, file))
    return rows


def build(out, config, summary_dir):
    systems = out["systems"]
    specs = {spec["name"]: spec for spec in config["systems"]}
    ranked = sorted(systems.items(), key=lambda kv: -kv[1]["official"]["overall_score"])
    color = lambda name: specs[name]["color"]
    dot = lambda name: f"<span class='dot' style='background:{color(name)}'></span>{escape(name)}"
    label = out.get("label") or ""
    manifest = json.loads((bc.BENCH_DIR / "data" / "pilot_manifest.json").read_text())
    n_questions = manifest["pilot_questions"]
    title = f"EnterpriseRAG-Bench{(' · ' + escape(label)) if label else ''}"

    h = head(f"{title} · 4Minds")
    h.append(header(f"Generated {escape(out['created'])}<br>EnterpriseRAG-Bench {escape(out['upstream_commit'][:7])}, "
                    "official metrics-based evaluation"))
    answers = summary_dir.parent / "answers.html"
    h.append(tabs("report", "#", rel(answers, summary_dir), DOWNLOAD_BUTTON) if answers.exists() else download_bar())
    h.append("<div class='label'>Benchmark report</div>")
    h.append(f"<h1>{title}</h1>")
    h.append(f"<p class='note' style='margin:0 0 16px'>Benchmark: <a href='{escape(bc.profile.UPSTREAM_URL)}/tree/main' "
             "target='_blank' rel='noopener'>onyx-dot-app/EnterpriseRAG-Bench on GitHub</a></p>")
    h.append("<p class='lead'>Does 4Minds answer questions about a company's own documents better than the RAG systems "
             f"that customers already use? {len(config['systems'])} systems with the same model (GPT-OSS-120B) answered the same {n_questions} "
             f"questions from the same {manifest['slice_documents']:,} company documents. The official EnterpriseRAG-Bench "
             f"scorer, with its own judge ({escape(out['judge']['judge'])}), scored each system alone.</p>")
    h.append("<span class='pill'>Official scorer, unchanged</span><span class='pill'>Default settings</span>"
             "<span class='pill'>Leaderboard format</span>")
    if label:
        h.append(f"<span class='pill warn'>{escape(label)}: small sample and a corpus slice. Do not use for conclusions "
                 "and do not compare with the public leaderboard.</span>")

    h.append("<section><div class='label'>Headline</div><h2>Overall score</h2>"
             f"<p class='sub'>The <a href='{escape(bc.profile.LEADERBOARD_URL)}' target='_blank' rel='noopener'>"
             "leaderboard score</a> (0–100): for each question, the completeness of the answer when the judge "
             "says that the answer is correct, else 0. Bars show the mean; the white whisker is the 95% bootstrap confidence "
             "interval.</p><div class='card'>")
    for name, s in ranked:
        h.append(bar(name, specs[name]["short"], ci(s), color(name)))
    for name in out.get("not_scored", {}):
        h.append(bar(name, "not scored (see below)", None, color(name)))
    h.append("</div></section>")
    h.append("<section><div class='label'>All metrics</div><h2>Official metrics</h2>"
             "<p class='sub'>From the official <code>results.json</code> of each system. Recall and invalid extra documents use "
             "the document IDs that the system gave; they apply only to questions with gold documents. "
             "“Overall, missing = 0” counts a question that the official scorer skipped (no answer) as 0.</p>"
             "<div class='card'><table><tr><th>System</th><th>Overall</th><th>Overall, missing = 0</th>"
             + "".join(f"<th>{escape(t)}</th>" for _, t in METRICS) + "<th>Corrected</th><th>Scored</th></tr>")
    for name, s in ranked:
        o = s["official"]
        cells = "".join(f"<td>{o[k]:.2f}</td>" for k, _ in METRICS)
        h.append(f"<tr><td>{dot(name)}</td><td><strong style='font-weight:500'>{o['overall_score']:.2f}</strong></td>"
                 f"<td>{s['overall_missing_as_zero']:.2f}</td>{cells}<td>{len(s['corrected'])}</td>"
                 f"<td>{s['scored_questions']}/{s['run_questions']}</td></tr>")
    h.append("</table><p class='note'>Corrected: questions where 3 judges agreed that a retrieved document that is not gold "
             "has the answer, so that document became gold for that system (official default).</p></div></section>")

    h.append("<section><div class='label'>Leaderboard</div><h2>Rows for the public leaderboard</h2>"
             "<p class='sub'>Made by the leaderboard Space's own <code>transform_raw_data.py</code> from the bundle in "
             "<code>leaderboard/raw_data/</code>. The same files could go to the Space; these pilot rows must not, because "
             "they use 50 questions and a corpus slice.</p><div class='card'><table><tr>"
             + "".join(f"<th>{escape(k)}</th>" for k in (out["leaderboard"][0] if out["leaderboard"] else {})) + "</tr>")
    for row in out["leaderboard"]:
        h.append("<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in row.values()) + "</tr>")
    h.append("</table></div></section>")

    points = []
    for name, s in ranked:
        o = s["operations"]
        lat, cost = o.get("latency") or {}, o.get("estimated_cost_usd")
        points.append({"key": s["key"], "name": name, "color": color(name), "quality": ci(s)["mean"],
                       "quality_low": ci(s)["ci_low"], "quality_high": ci(s)["ci_high"],
                       "latency": lat.get("median_s"), "latency_p90": lat.get("p90_s"),
                       "hover": [f"Est. answer cost: {'n/a (subscription)' if cost is None else f'${cost:.2f}'}",
                                 f"Documents per answer: {s['documents_per_answer']['mean']}"]})
    h.append("<section><div class='label'>Quality and speed</div><h2>Overall score and latency</h2>"
             "<p class='sub'>One point for each system. Move the pointer over a point for the 95% confidence interval, "
             "the 90th-percentile latency and the cost.</p><div class='card'>")
    h.append(quality_latency("quality-latency", points, "Overall score"))
    h.append("<p class='note'>Latency depends on the number of workers, the network and the load on each service during "
             "the run (see Operations).</p></div></section>")

    if out.get("not_scored") or any(s["not_scored"] for s in systems.values()):
        h.append("<section><div class='label'>Not scored</div><h2>Systems and questions without a result</h2>"
                 "<div class='card'><ul class='caveats'>")
        h += [f"<li><strong style='font-weight:500'>{escape(n)}</strong>: {escape(str(r))}</li>"
              for n, r in out.get("not_scored", {}).items()]
        h += [f"<li><strong style='font-weight:500'>{escape(n)}</strong>: question {escape(', '.join(s['not_scored']))} has "
              "no answer, so the official scorer skipped it.</li>" for n, s in ranked if s["not_scored"]]
        h.append("</ul></div></section>")

    types = sorted({t for s in systems.values() for t in s["by_type"]})
    h.append("<section><div class='label'>By question type</div><h2>Overall score per question type</h2>"
             f"<p class='sub'>Each type has only {min(manifest['pilot_question_types'].values())} to "
             f"{max(manifest['pilot_question_types'].values())} questions in this pilot, so one question changes a score "
             "by many points.</p><div class='card'><table><tr><th>System</th>"
             + "".join(f"<th>{escape(t.replace('_', ' '))}</th>" for t in types) + "</tr>")
    for name, s in ranked:
        cells = "".join(f"<td>{s['by_type'][t]['combined_correctness_completeness_score']:.1f} "
                        f"<small>n={s['by_type'][t]['count']}</small></td>" if t in s["by_type"] else "<td>–</td>"
                        for t in types)
        h.append(f"<tr><td>{dot(name)}</td>{cells}</tr>")
    h.append("</table></div></section>")

    h.append("<section><div class='label'>Operations</div><h2>Reliability, latency and cost</h2>"
             "<p class='sub'>From the run and score manifests. Answer cost is the estimated model cost (list prices); "
             "4Minds is a subscription, so no per-question cost is shown. Judge cost is the measured OpenAI cost of "
             "scoring.</p><div class='card'><table><tr><th>System</th><th>Answered</th><th>No context</th>"
             "<th>Docs per answer</th><th>Latency median / p90 (s)</th><th>Answer cost (USD)</th>"
             "<th>Judge cost (USD)</th><th>Run</th></tr>")
    for name, s in ranked:
        o, lat = s["operations"], s["operations"].get("latency") or {}
        cost = o.get("estimated_cost_usd")
        h.append(f"<tr><td>{dot(name)}</td><td>{o['answered']}/{o['questions']}</td><td>{o['no_context']}</td>"
                 f"<td>{s['documents_per_answer']['mean']}</td>"
                 f"<td>{lat.get('median_s', 'n/a')} / {lat.get('p90_s', 'n/a')}</td>"
                 f"<td>{'n/a' if cost is None else f'{cost:.3f}'}</td><td>{s['judge']['cost_usd']:.2f}</td>"
                 f"<td><small>{escape(str(s.get('run_started') or ''))}<br>workers {o.get('workers')}</small></td></tr>")
    h.append("</table><p class='note'>“No context” for GPT-OSS without RAG is by design: that system gets no documents.</p>"
             "</div></section>")

    ingestion = ingestion_rows(config["systems"])
    h.append("<section><div class='label'>Ingestion</div><h2>Time to load the corpus</h2>"
             "<p class='sub'>From the setup and index files: the time from the start of the upload or index build until the "
             "system was ready.</p><div class='card'><table><tr><th>System</th><th>Time (h)</th><th>Est. cost (USD)</th></tr>")
    for spec, seconds, cost, _ in ingestion:
        h.append(f"<tr><td>{dot(spec['name'])}</td><td>{'n/a' if seconds is None else f'{seconds / 3600:.2f}'}</td>"
                 f"<td>{'n/a' if cost is None else f'{cost:.2f}'}</td></tr>")
    h.append("</table></div></section>")

    h.append("<section><div class='label'>Method</div><h2>How the benchmark ran</h2><div class='grid'>")
    h.append("<div class='card'><h3>Protocol</h3><ul class='caveats'>"
             f"<li>Dataset: EnterpriseRAG-Bench (Onyx), commit <code>{escape(out['upstream_commit'][:12])}</code>, "
             f"{manifest['corpus_documents_total']:,} documents and 500 questions.</li>"
             f"<li>Pilot: {n_questions} questions, stratified by question type, seed {manifest['seed']}.</li>"
             f"<li>Corpus slice: the {manifest['gold_documents']} gold documents of the pilot questions plus "
             f"{manifest['distractor_documents']:,} random other documents ({manifest['slice_chars']:,} characters).</li>"
             "<li>Every system got the same documents and the instructions of the official answer prompt.</li>"
             "<li>Scoring: the official <code>metrics_based_eval.py</code>, unchanged, with its default settings and judge "
             f"({escape(out['judge']['judge'])}; {escape(out['judge']['cheap_judge'])} for JSON recovery).</li>"
             "<li>No system answered a question before its ingestion was complete (a readiness check gates each run).</li>"
             "</ul></div>")
    h.append("<div class='card'><h3>Systems</h3><ul class='caveats'>")
    for spec in config["systems"]:
        h.append(f"<li>{dot(spec['name'])}: {escape(spec['description'])}. Leaderboard name: "
                 f"“{escape(spec['leaderboard_name'])}”.</li>")
    h.append("</ul></div></div></section>")

    h.append("<section><div class='label'>Read before you share</div><h2>Notes and caveats</h2><div class='card'>"
             "<ul class='caveats'>")
    h += [f"<li>{escape(c)}</li>" for c in out["caveats"]]
    h.append("</ul></div></section>")

    links = [("Question browser (answers, not in git)", summary_dir.parent / "answers.html"),
             ("Summary data (JSON)", summary_dir / "scores.json"), ("Summary (Markdown)", summary_dir / "report.md"),
             ("Leaderboard rows (CSV)", summary_dir / "leaderboard.csv"),
             ("Leaderboard bundle", summary_dir.parent / "leaderboard" / "raw_data"),
             ("Pilot manifest", bc.BENCH_DIR / "data" / "pilot_manifest.json"),
             ("Audit log (JSON lines)", bc.AUDIT_DIR / "audit.log"), ("Step logs", bc.AUDIT_DIR / "steps")]
    for name, s in ranked:
        folder = Path(s["folder"])
        links += [(f"{name}: run manifest", folder / "manifest.json"), (f"{name}: predictions", folder / "predictions.json"),
                  (f"{name}: official results", folder / "results.json"),
                  (f"{name}: score manifest", folder / "score_manifest.json")]
    links += [(f"{spec['name']}: ingestion", file) for spec, _, _, file in ingestion]
    h.append("<section><div class='label'>Audit trail</div><h2>Files</h2><p class='sub'>Every run, retry, readiness check "
             "and score step is logged. Links are relative to this report.</p><div class='card'><table>")
    h += [f"<tr><td>{escape(n)}</td><td><a href='{escape(rel(p, summary_dir))}'>{escape(rel(p, bc.BENCH_DIR))}</a></td></tr>"
          for n, p in links if p.exists()]
    h.append("</table></div></section>")
    h.append(download_script(summary_dir))
    h.append(f"<footer>4Minds · {title} · generated by make_report.py from "
             f"{escape(rel(summary_dir / 'scores.json', bc.BENCH_DIR))}</footer></div></body></html>")
    return "\n".join(h)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True, help="run folder, for example runs/<YYYY-MM-DD>_<name>")
    args = parser.parse_args()
    run_dir = Path(args.run).resolve()
    summary_dir = run_dir / "summary"
    out = json.loads((summary_dir / "scores.json").read_text())
    config = json.loads((run_dir / "config.json").read_text())["config"]
    answers = answers_page.write(out, config, run_dir)
    print(f"wrote {answers}")
    target = summary_dir / "report.html"
    target.write_text(build(out, config, summary_dir))
    run_readme.write(run_dir)
    bc.audit("report_html", path=str(target), sha256=bc.sha256(target))
    print(f"wrote {target}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Write runs/<run>/summary/report.html from summary/scores.json, in the 4Minds web style.

    ./bench 4minds-rag report_v1 eval make_report.py --run runs/2026-10-11_erag-pilot_judge-gpt-4o-mini

Run aggregate.py first. The systems (names, colors, descriptions, ingestion files) come from the comparison file copy
in runs/<run>/config.json; the metric texts come from the scorer config copy in the same file.
Links to the audit files are relative to the summary folder.
"""
import argparse
import json
from html import escape
from pathlib import Path

import answers_page
import bench_common as bc
import export_page
import run_readme
from report_html import (DOWNLOAD_BUTTON, bar, download_bar, download_script, head, header, pct, rel, tabs,
                         title_with_info)


def ingestion_rows(specs):
    """(spec, info, seconds, cost, file) per system with an ingestion entry; a value is None if it is not known."""
    rows = []
    for spec in specs:
        info = spec.get("ingestion")
        if not info:
            continue
        file = (bc.BENCH_DIR / info["file"]).resolve() if info.get("file") else None
        data = json.loads(file.read_text()) if file and file.exists() else {}
        seconds = info["seconds_value"] if "seconds_value" in info else data.get(info.get("seconds"))
        cost = info["cost_value"] if "cost_value" in info else data.get(info.get("cost"))
        rows.append((spec, info, seconds, cost, file))
    return rows


def duration(seconds):
    if seconds is None:
        return "n/a"
    return f"{seconds / 3600:.1f} h" if seconds >= 3600 else f"{seconds / 60:.0f} min"


def build(out, config, summary_dir, export=None):
    """The report page. With export (the export file name), only the page body for export_page.py:
    no links to local files, and the question browser is the second tab of the same file."""
    systems = out["systems"]
    specs = {spec["name"]: spec for spec in config["systems"]}
    color = lambda name: specs[name]["color"]
    dot = lambda name: f"<span class='dot' style='background:{color(name)}'></span>{escape(name)}"
    metrics = {m["name"]: m for m in out["metrics"]}
    judge = out["scorer"]["judge"].get("backend") or out["scorer"]["judge"].get("model")
    label = out.get("label") or ""
    manifest = json.loads(bc.profile.PILOT_MANIFEST.read_text())
    title = f"4Minds RAG{(' · ' + escape(label)) if label else ''}"

    h = head(f"{title} · 4Minds")
    h.append(header(f"Generated {escape(out['created'])}<br>Scorer {escape(out['scorer']['name'])}, judge "
                    f"{escape(judge)}"))
    answers = summary_dir.parent / "answers.html"
    if not export:
        h.append(tabs("report", "#", rel(answers, summary_dir), DOWNLOAD_BUTTON) if answers.exists() else download_bar())
    body_start = len(h)
    h.append("<div class='label'>Benchmark report</div>")
    h.append(f"<h1>{title}</h1>")
    h.append(f"<p class='lead'>How correct and complete are the answers of each system, and did it find the right documents? "
             f"{len(config['systems'])} systems with the same model (GPT-OSS-120B) answered the same {manifest['pilot_questions']} "
             f"EnterpriseRAG-Bench questions from the same {manifest['slice_documents']:,} company documents. Here, the saved "
             f"answers are scored again with RAGAS and DeepEval metrics (judge: {escape(judge)}) and with document precision, "
             "recall and F1.</p>")
    h.append("<span class='pill'>Saved answers, not answered again</span><span class='pill'>Same judge for all systems</span>"
             f"<span class='pill'>Judge: {escape(judge)}</span>")
    if label:
        h.append(f"<span class='pill warn'>{escape(label)}: small sample and a corpus slice. Do not use for conclusions.</span>")
    export_file = summary_dir.parent / "export" / export_page.file_name(summary_dir.parent)
    if not export and export_file.exists():
        h.append(f"<br><a class='pill' style='{export_page.BUTTON_STYLE}' href='{escape(rel(export_file, summary_dir))}' download='{escape(export_file.name)}'>"
                 "Export for sharing (one HTML file)</a>")

    h.append("<section><div class='label'>Headline</div><h2>Main metrics</h2>"
             "<p class='sub'>Scores from 0 to 100, higher is better. Bars show the mean over the questions; the white whisker is "
             "the 95% bootstrap confidence interval. Move the pointer over the “i” for what each metric measures.</p>"
             "<div class='grid'>")
    for name in out["headline_metrics"]:
        m = metrics[name]
        ranked = sorted(systems.items(), key=lambda kv: -(kv[1]["metrics"][name]["mean"] or 0))
        h.append(f"<div class='card'><h3>{title_with_info(m['label'], [m['note']])}</h3>")
        h += [bar(n, specs[n]["short"], s["metrics"][name] if s["metrics"][name]["n"] else None, color(n)) for n, s in ranked]
        h += [bar(n, "not scored (see below)", None, color(n)) for n in out.get("not_scored", {})]
        h.append("</div>")
    h.append("</div></section>")

    h.append("<section><div class='label'>All metrics</div><h2>All metric outputs</h2>"
             "<p class='sub'>Every number that the scorers give, as 0–100. Factual Correctness gives claim precision, recall and "
             "F1 (judge); document retrieval gives document precision, recall and F1 (no judge). Summarization score = "
             "min(alignment, coverage). n = scored questions.</p><div class='card'><table><tr><th>Metric</th>"
             + "".join(f"<th>{dot(n)}</th>" for n in systems) + "</tr>")
    for name, m in metrics.items():
        cells = "".join(f"<td>{pct(s['metrics'][name]['mean'])} <small>n={s['metrics'][name]['n']}</small></td>"
                        for s in systems.values())
        h.append(f"<tr><td>{escape(m['label'])}</td>{cells}</tr>")
    h.append("</table></div></section>")

    types = sorted({t for s in systems.values() for t in s["by_type"]})
    counts = manifest["pilot_question_types"]
    h.append("<section><div class='label'>By question type</div><h2>Main metrics per question type</h2>"
             f"<p class='sub'>Each type has only {min(counts.values())} to {max(counts.values())} questions in this pilot, so one "
             "question changes a score by many points.</p>")
    for name in out["headline_metrics"]:
        h.append(f"<div class='card'><h3>{escape(metrics[name]['label'])}</h3><table><tr><th>System</th>"
                 + "".join(f"<th>{escape(t.replace('_', ' '))}</th>" for t in types) + "</tr>")
        for n, s in systems.items():
            cells = "".join(f"<td>{pct(s['by_type'][t][name]['mean'], 0)} <small>n={s['by_type'][t][name]['n']}</small></td>"
                            if name in s["by_type"].get(t, {}) else "<td>–</td>" for t in types)
            h.append(f"<tr><td>{dot(n)}</td>{cells}</tr>")
        h.append("</table></div>")
    h.append("</section>")

    ingestion = ingestion_rows(config["systems"])
    if ingestion:
        h.append("<section><div class='label'>Ingestion</div><h2>Time and cost to load the corpus</h2>"
                 f"<p class='sub'>Each system loaded the same {manifest['slice_documents']:,} documents once, before it answered "
                 "(EnterpriseRAG-Bench run; a readiness check gated each run). Time: from the start of the upload or index "
                 "build until the system was ready. Cost: an estimate from the token counts and list prices, not an invoice. "
                 "The systems ran on different machines and with different parallel requests, so compare the times only "
                 "roughly.</p><div class='card'><table><tr><th>System</th><th>Time</th><th>Est. cost (USD)</th>"
                 "<th>The cost pays for</th><th>Ran on</th></tr>")
        for spec, info, seconds, cost, _ in ingestion:
            h.append(f"<tr><td>{dot(spec['name'])}</td><td>{duration(seconds)}</td>"
                     f"<td>{'n/a' if cost is None else f'{cost:.2f}'}</td><td>{escape(info.get('cost_covers', ''))}</td>"
                     f"<td>{escape(info.get('ran_on', ''))}</td></tr>")
        h.append("</table>")
        notes = [f"<li><strong style='font-weight:500'>{escape(spec['name'])}</strong>: {escape(info['note'])}</li>"
                 for spec, info, *_ in ingestion if info.get("note")]
        if notes:
            h.append("<ul class='caveats'>" + "".join(notes) + "</ul>")
        h.append("</div></section>")

    h.append("<section><div class='label'>Scoring</div><h2>Judge use and cost</h2>"
             "<p class='sub'>From the score files. An item is one answer and one metric. “Not JSON” counts judge replies that "
             "were not valid JSON after the code-fence fix; the metric then tries again or records an error. Cost is from "
             "the token counts and the list prices of the judge backend.</p><div class='card'><table><tr><th>System</th>"
             "<th>Answers</th><th>Items</th><th>Not scored</th><th>Judge calls</th><th>Not JSON</th><th>Fences removed</th>"
             "<th>Truncated</th><th>Judge cost (USD)</th></tr>")
    for n, s in systems.items():
        u = s["judge"]["usage"]
        h.append(f"<tr><td>{dot(n)}</td><td>{s['answers']}</td><td>{s['items']}</td><td>{s['not_scored']}</td>"
                 f"<td>{u.get('calls', 'n/a')}</td><td>{u.get('not_json_replies', 'n/a')}</td>"
                 f"<td>{u.get('fences_removed', 'n/a')}</td><td>{u.get('truncated_replies', 'n/a')}</td>"
                 f"<td>{s['judge']['cost_usd']:.3f}</td></tr>")
    h.append("</table></div></section>")

    missing = [(n, s) for n, s in systems.items() if s["missing_answers"] or s["not_scored_items"]]
    if missing or out.get("not_scored"):
        h.append("<section><div class='label'>Not scored</div><h2>Systems and items without a result</h2>"
                 "<div class='card'><ul class='caveats'>")
        h += [f"<li><strong style='font-weight:500'>{escape(n)}</strong>: {escape(str(r))}</li>"
              for n, r in out.get("not_scored", {}).items()]
        for n, s in missing:
            if s["missing_answers"]:
                h.append(f"<li><strong style='font-weight:500'>{escape(n)}</strong>: no answer for "
                         f"{escape(', '.join(s['missing_answers']))}, so that question is not in its means.</li>")
            if s["not_scored_items"]:
                h.append(f"<li><strong style='font-weight:500'>{escape(n)}</strong>: the judge did not score "
                         + escape(", ".join(f"{x['id']} {x['metric']}" for x in s["not_scored_items"])) + ".</li>")
        h.append("</ul></div></section>")

    for file in sorted(summary_dir.parent.glob("tests/*/agreement.json")):
        a = json.loads(file.read_text())
        h.append("<section><div class='label'>Judge agreement</div>"
                 f"<h2>{escape(a['judge_a'])} against {escape(a['judge_b'])}</h2>"
                 "<p class='sub'>The same answers, scored by two judges (compare_judges.py). Pearson and Spearman: per-item "
                 "correlation over all (system, question) pairs that both judges scored (1 = the same order). Same value: "
                 "share of items with the same score. System rank: Spearman correlation of the five system means (1 = the "
                 f"same ranking). From <code>{escape(rel(file, bc.BENCH_DIR))}</code>.</p><div class='card'><table><tr>"
                 "<th>Metric</th><th>Items</th><th>Mean A</th><th>Mean B</th><th>Pearson</th><th>Spearman</th>"
                 "<th>Same value</th><th>System rank</th></tr>")
        f = lambda v, d=2: "n/a" if v is None else f"{v:.{d}f}"
        for m in a["metrics"].values():
            h.append(f"<tr><td>{escape(m['label'])}</td><td>{m['items']}</td><td>{pct(m['mean_a'])}</td>"
                     f"<td>{pct(m['mean_b'])}</td><td>{f(m['pearson'])}</td><td>{f(m['spearman'])}</td>"
                     f"<td>{pct(m['same_value_share'], 0)}%</td><td>{f(m['system_rank_spearman'])}</td></tr>")
        h.append("</table><p class='note'>Document retrieval uses no judge, so it is the same in both runs (a check of "
                 "the join).</p></div></section>")

    scorer = config.get("scorer", {})
    h.append("<section><div class='label'>Method</div><h2>How the benchmark ran</h2><div class='grid'>")
    h.append("<div class='card'><h3>Protocol</h3><ul class='caveats'>"
             f"<li>Answers: the saved answers of <code>{escape(str(out.get('derived_from') or ''))}</code>, linked, not made again "
             f"(EnterpriseRAG-Bench commit <code>{escape(out['source_upstream_commit'][:12])}</code>).</li>"
             f"<li>Questions: the {manifest['pilot_questions']}-question pilot, stratified by question type, seed {manifest['seed']}. "
             "References: the gold answer, the gold facts and the gold document IDs of each question.</li>"
             f"<li>Scorer: <code>pipeline/score_extra.py</code> with <code>{escape(scorer.get('source', ''))}</code> "
             f"(sha256 <code>{escape(scorer.get('sha256', '')[:12])}</code>); judge <code>{escape(judge)}</code>, "
             f"{escape(json.dumps(out['scorer']['judge'].get('args', {})))}.</li>"
             "<li>Summarization assessment questions are made once per question and are the same for every system.</li>"
             f"<li>Packages: " + escape(", ".join(f"{k} {v}" for k, v in next(iter(systems.values()))["versions"].items()))
             + ".</li></ul></div>")
    h.append("<div class='card'><h3>Systems</h3><ul class='caveats'>")
    h += [f"<li>{dot(spec['name'])}: {escape(spec['description'])}.</li>" for spec in config["systems"]]
    h.append("</ul></div></div></section>")

    h.append("<section><div class='label'>Read before you share</div><h2>Notes and caveats</h2><div class='card'>"
             "<ul class='caveats'>")
    h += [f"<li>{escape(c)}</li>" for c in out["caveats"]]
    h.append("</ul></div></section>")

    links = [("Question browser (answers, not in git)", summary_dir.parent / "answers.html"),
             ("Summary data (JSON)", summary_dir / "scores.json"), ("Summary (Markdown)", summary_dir / "report.md"),
             ("Config copy (comparison and scorer)", summary_dir.parent / "config.json"),
             ("Shared assessment questions", bc.SHARED / "extra" / out["scorer"]["name"] / "shared.json"),
             ("Audit log (JSON lines)", bc.AUDIT_DIR / "audit.log"), ("Step logs", bc.AUDIT_DIR / "steps")]
    for n, s in systems.items():
        folder = Path(s["folder"])
        links += [(f"{n}: predictions (link)", folder / "predictions.json"),
                  (f"{n}: scores", folder / f"{out['scorer']['name']}.json")]
    links += [(f"{spec['name']}: ingestion", file) for spec, _, _, _, file in ingestion if file]
    if export:
        h.append("<section><div class='label'>Audit trail</div><h2>Files</h2><p class='sub'>Every score and summary step is "
                 f"logged. These files are in the benchmark hub, folder <code>benchmarks/{escape(bc.BENCHMARK)}/</code>; they "
                 "are not in this exported file.</p><div class='card'><table>")
        h += [f"<tr><td>{escape(n)}</td><td><code>{escape(rel(p, bc.BENCH_DIR))}</code></td></tr>"
              for n, p in links if p.exists() and p.name != "answers.html"]
        h.append("</table></div></section>")
        return h[body_start:]
    h.append("<section><div class='label'>Audit trail</div><h2>Files</h2><p class='sub'>Every score and summary step is "
             "logged. Links are relative to this report.</p><div class='card'><table>")
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
    record = json.loads((run_dir / "config.json").read_text())
    config = {**record["config"], "scorer": {k: v for k, v in record.get("scorer", {}).items() if k != "config"}}
    exported = export_page.write(out, record["config"], run_dir, build(out, config, summary_dir, export=True))
    print(f"wrote {exported}")
    answers = answers_page.write(out, record["config"], run_dir)
    print(f"wrote {answers}")
    target = summary_dir / "report.html"
    target.write_text(build(out, config, summary_dir))
    run_readme.write(run_dir)
    bc.audit("report_html", path=str(target), sha256=bc.sha256(target))
    print(f"wrote {target}")


if __name__ == "__main__":
    main()

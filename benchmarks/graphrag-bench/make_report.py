#!/usr/bin/env python3
"""Write <results>/summary/report.html from summary/scores.json, in the 4Minds web style.

  ./bench graphrag-bench report_pilot eval make_report.py --results results/pilot
  ./bench graphrag-bench report eval make_report.py --results results

The page is one file: inline CSS and logo, fonts from Typekit/Google Fonts (system fallback
when offline). Links to the audit files are relative to the summary folder.
"""
import argparse
import json
import os
from html import escape
from pathlib import Path

import bench_common as bc

LOGO = Path("/Users/victorbezak/Documents/4minds-main/4minds-platform/frontend-backend/frontend/public/assets/fullLogoWhite.svg")
SYSTEM_COLORS = {"4minds_constellations": "#543fed", "4minds_symi": "#a78bfa", "gemini": "#80aeff",
                 "rag_engine": "#5eead4", "lightrag": "#fbbf24"}

CSS = """
:root { --bg:#18181c; --card:#1c1c21; --accent:#543fed; --blue:#80aeff; --violet:#a78bfa;
  --text:#fff; --muted:rgba(255,255,255,0.5); --border:rgba(255,255,255,0.08); }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text);
  font-family:'neue-haas-grotesk-display','Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  font-size:16px; line-height:1.5; -webkit-font-smoothing:antialiased; }
.wrap { max-width:1120px; margin:0 auto; padding:40px 24px 80px; }
header { display:flex; align-items:center; justify-content:space-between; padding-bottom:32px;
  border-bottom:1px solid var(--border); margin-bottom:48px; }
header .meta { color:var(--muted); font-size:14px; text-align:right; }
h1,h2,h3 { font-weight:400; margin:0; letter-spacing:-0.01em; }
h1 { font-size:48px; line-height:1.1; margin-bottom:16px; }
h2 { font-size:32px; margin-bottom:8px; }
h3 { font-size:20px; margin-bottom:16px; }
.label { color:var(--violet); text-transform:uppercase; letter-spacing:0.12em; font-size:12px; margin-bottom:12px; }
.lead { color:var(--muted); font-size:18px; max-width:760px; }
.pill { display:inline-block; padding:4px 12px; border-radius:999px; border:1px solid var(--border);
  font-size:13px; color:var(--muted); margin:16px 8px 0 0; }
.pill.warn { color:#fbbf24; border-color:rgba(251,191,36,0.4); }
section { margin-top:64px; }
.sub { color:var(--muted); margin-bottom:24px; max-width:820px; }
.card { background:var(--card); border:1px solid var(--border); border-radius:20px; padding:28px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:20px; }
.bar-row { display:grid; grid-template-columns:220px 1fr 130px; align-items:center; gap:16px; padding:10px 0;
  border-bottom:1px solid var(--border); }
.bar-row:last-child { border-bottom:none; }
.bar-name { font-size:15px; }
.bar-name small { display:block; color:var(--muted); font-size:12px; }
.track { position:relative; height:22px; background:rgba(255,255,255,0.04); border-radius:6px; }
.fill { position:absolute; top:0; bottom:0; left:0; border-radius:6px; opacity:0.9; }
.ci { position:absolute; top:50%; height:2px; background:rgba(255,255,255,0.85); transform:translateY(-50%); }
.ci::before,.ci::after { content:''; position:absolute; top:-5px; width:2px; height:12px; background:rgba(255,255,255,0.85); }
.ci::before { left:0; } .ci::after { right:0; }
.zero { position:absolute; top:-4px; bottom:-4px; left:50%; width:1px; background:rgba(255,255,255,0.35); }
.val { text-align:right; font-variant-numeric:tabular-nums; }
.val small { display:block; color:var(--muted); font-size:12px; }
table { width:100%; border-collapse:collapse; font-size:14px; }
th { text-align:left; font-weight:400; color:var(--muted); padding:12px 14px; border-bottom:1px solid var(--border); }
td { padding:14px; border-bottom:1px solid var(--border); font-variant-numeric:tabular-nums; vertical-align:top; }
tr:last-child td { border-bottom:none; }
td small { color:var(--muted); }
.dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:10px; vertical-align:middle; }
ul.caveats { margin:0; padding-left:20px; color:rgba(255,255,255,0.8); }
ul.caveats li { margin-bottom:10px; }
a { color:var(--blue); text-decoration:none; } a:hover { text-decoration:underline; }
.legend { display:flex; flex-wrap:wrap; gap:16px; color:var(--muted); font-size:13px; margin-bottom:12px; }
.note { color:var(--muted); font-size:13px; margin:14px 0 0; }
.pos { color:#86efac; } .neg { color:#fca5a5; } .neutral { color:var(--muted); }
footer { margin-top:80px; padding-top:24px; border-top:1px solid var(--border); color:var(--muted); font-size:13px; }
@media (max-width:720px) { .bar-row { grid-template-columns:1fr; } h1 { font-size:34px; } }
"""


def pct(x, digits=1):
    return "n/a" if x is None else f"{x * 100:.{digits}f}"


def bar(name, sub, r, color, scale_max=1.0):
    if not r:
        return (f'<div class="bar-row"><div class="bar-name">{escape(name)}<small>{escape(sub)}</small></div>'
                f'<div class="track"></div><div class="val">n/a</div></div>')
    w = lambda v: max(0.0, min(100.0, v / scale_max * 100))
    return (f'<div class="bar-row"><div class="bar-name">{escape(name)}<small>{escape(sub)}</small></div>'
            f'<div class="track"><div class="fill" style="width:{w(r["mean"]):.2f}%;background:{color}"></div>'
            f'<div class="ci" style="left:{w(r["ci_low"]):.2f}%;width:{w(r["ci_high"]) - w(r["ci_low"]):.2f}%"></div></div>'
            f'<div class="val">{pct(r["mean"])}<small>95% CI {pct(r["ci_low"])}–{pct(r["ci_high"])} · n={r["n"]}</small></div></div>')


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


def rel(path, base):
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return str(path)


def build(out, timing, summary_dir):
    systems = out["systems"]
    names = {s["key"]: s["name"] for s in systems}
    color = lambda k: SYSTEM_COLORS.get(k, "#80aeff")
    label = out.get("label") or ""
    snapshots = ", ".join(out["benchmark"]["judge_snapshot"]) or out["benchmark"]["judge"]
    commit = ", ".join(c[:7] for c in out["benchmark"]["commit"]) or bc.UPSTREAM_COMMIT[:7]
    n_questions = max((s["operations"].get("questions") or 0) for s in systems) if systems else 0
    ranked = sorted(systems, key=lambda s: -((out["overall"][s["key"]]["answer_correctness"] or {}).get("mean") or 0))

    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
         f"<title>GraphRAG-Bench Medical{(' · ' + escape(label)) if label else ''} · 4Minds</title>",
         "<link rel='stylesheet' href='https://use.typekit.net/ipe4ndc.css'>",
         "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500&display=swap'>",
         f"<style>{CSS}</style></head><body><div class='wrap'>"]
    logo = LOGO.read_text() if LOGO.exists() else "<strong>4Minds</strong>"
    h.append(f"<header><div>{logo}</div><div class='meta'>Generated {escape(out['generated'])}<br>"
             f"GraphRAG-Bench commit {escape(commit)}</div></header>")

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
            h.append(f"<div class='card'><h3>{escape(qt)} · {escape(out['metric_names'][metric])}</h3>")
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
                h.append("<p class='note'>The official verdict prompt does not ask for JSON; gpt-4o-mini often "
                         "answers in prose, and those answers score NaN. See the caveats.</p>")
            elif metric == "faithfulness_jsonfix":
                h.append("<p class='note'>Not part of the official protocol: the same code and judge with one "
                         "sentence that asks for JSON output.</p>")
            h.append("</div>")
    h.append("</div></section>")

    if out.get("paired"):
        h.append("<section><div class='label'>Detail</div><h2>Paired differences per type and metric</h2>"
                 "<p class='sub'>4Minds (Constellations) minus the other system, in points. Green: 4Minds higher with 95% confidence. "
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

    h.append("<section><div class='label'>Operations</div><h2>Reliability, latency and cost</h2>"
             "<p class='sub'>From the run manifests. Cost is the estimated model cost for answering (list prices), not the index "
             "build; 4Minds is a subscription, so no per-question cost is shown.</p><div class='card'><table>"
             "<tr><th>System</th><th>Answered</th><th>Failed</th><th>“I don't know”</th><th>Latency median / p90 (s)</th>"
             "<th>Est. cost (USD)</th><th>Run</th></tr>")
    for s in systems:
        o, lat = s["operations"], s["operations"].get("latency") or {}
        cost = o.get("estimated_cost_usd")
        h.append(f"<tr><td><span class='dot' style='background:{color(s['key'])}'></span>{escape(s['name'])}</td>"
                 f"<td>{o.get('answered')}/{o.get('questions')}</td><td>{o.get('failed')}</td><td>{o.get('dont_know')}</td>"
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
    parser.add_argument("--results", default=str(bc.RESULTS))
    args = parser.parse_args()
    root = Path(args.results).resolve()
    summary_dir = root / "summary"
    out = json.loads((summary_dir / "scores.json").read_text())
    timing_file = root / "timing.json"
    timing = json.loads(timing_file.read_text()) if timing_file.exists() else None
    target = summary_dir / "report.html"
    target.write_text(build(out, timing, summary_dir))
    bc.audit("report_html", path=str(target), sha256=bc.sha256(target))
    print(f"wrote {target}")


if __name__ == "__main__":
    main()

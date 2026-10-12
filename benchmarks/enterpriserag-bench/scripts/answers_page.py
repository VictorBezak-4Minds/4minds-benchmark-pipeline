"""runs/<run>/answers.html: each pilot question with its gold data and the answer and official result of each system.

make_report.py calls write(). The page has the answers, so it is outside summary/ (git does not
track answers; see .gitignore). The systems are in the order of the comparison file. Each retrieved
context item shows only its first CONTEXT_CHARS characters.
"""
import json
from html import escape
from pathlib import Path

import bench_common as bc
from report_html import head, header, rel, tabs

CONTEXT_CHARS = 300

PAGE_CSS = """
.wrap { max-width:1400px; }
.controls { display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin:24px 0; position:sticky; top:0; z-index:5;
  background:var(--bg); padding:12px 0; border-bottom:1px solid var(--border); }
.controls input, .controls select, .controls button { background:var(--card); color:var(--text); border:1px solid var(--border);
  border-radius:10px; padding:8px 12px; font:inherit; font-size:14px; }
.controls input { min-width:280px; } .controls button { cursor:pointer; } .controls button:hover { border-color:var(--violet); }
.controls .count { color:var(--muted); font-size:13px; }
details.q { background:var(--card); border:1px solid var(--border); border-radius:16px; margin-bottom:12px; }
details.q > summary { list-style:none; cursor:pointer; padding:16px 20px; display:grid;
  grid-template-columns:90px 1fr auto; gap:16px; align-items:center; }
details.q > summary::-webkit-details-marker { display:none; }
details.q[open] > summary { border-bottom:1px solid var(--border); }
.qid { color:var(--muted); font-size:13px; font-variant-numeric:tabular-nums; }
.qid small { display:block; color:var(--violet); font-size:11px; text-transform:uppercase; letter-spacing:0.06em; }
.qtext { font-size:15px; }
.mini { display:flex; gap:6px; } .mini span { width:34px; text-align:center; border-radius:6px; font-size:12px; padding:3px 0;
  font-variant-numeric:tabular-nums; color:#111; position:relative; }
.mini span:hover::after { content:attr(data-tip); position:absolute; bottom:calc(100% + 6px); left:50%; transform:translateX(-50%);
  white-space:nowrap; background:#000; color:#fff; border:1px solid var(--border); border-radius:6px; padding:4px 8px;
  font-size:12px; pointer-events:none; z-index:10; }
.body { padding:20px; }
.gold { border:1px solid rgba(167,139,250,0.35); background:rgba(84,63,237,0.08); border-radius:14px; padding:16px 18px; margin-bottom:20px; }
.gold h4 { margin:0 0 8px; font-weight:400; font-size:13px; color:var(--muted); text-transform:uppercase; letter-spacing:0.08em; }
.gold ul { margin:6px 0 0; padding-left:20px; } .gold li { margin-bottom:4px; }
.systems { display:grid; grid-template-columns:repeat(auto-fit,minmax(380px,1fr)); gap:16px; }
.sys { border:1px solid var(--border); border-radius:14px; padding:16px 18px; min-width:0; }
.sys .name { font-size:16px; margin-bottom:10px; }
.chips { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:12px; }
.chip { font-size:12px; border-radius:8px; padding:3px 8px; color:#111; font-variant-numeric:tabular-nums; }
.chip.ns { background:rgba(255,255,255,0.12); color:var(--muted); }
.answer { white-space:pre-wrap; overflow-wrap:anywhere; font-size:14px; line-height:1.55; color:rgba(255,255,255,0.9);
  max-height:420px; overflow:auto; padding:12px; background:rgba(0,0,0,0.2); border-radius:10px; }
.answer.none { color:var(--muted); font-style:italic; }
.meta { color:var(--muted); font-size:13px; margin-top:10px; }
.docs { font-size:12px; color:var(--muted); margin-top:8px; overflow-wrap:anywhere; }
.docs .hit { color:#86efac; }
details.ctx { margin-top:10px; font-size:13px; } details.ctx summary { cursor:pointer; color:var(--blue); }
details.ctx ol { padding-left:20px; color:rgba(255,255,255,0.75); } details.ctx li { margin-bottom:8px; white-space:pre-wrap; overflow-wrap:anywhere; }
.hidden { display:none; }
"""

SCRIPT = """
<script>
(function(){
  var qs=[].slice.call(document.querySelectorAll('details.q')), search=document.getElementById('search'),
      type=document.getElementById('type'), count=document.getElementById('count');
  function apply(){
    var t=search.value.toLowerCase(), ty=type.value, n=0;
    qs.forEach(function(q){
      var ok=(!ty||q.dataset.type===ty)&&(!t||q.textContent.toLowerCase().indexOf(t)>=0);
      q.classList.toggle('hidden',!ok); if(ok)n++;
    });
    count.textContent=n+' of '+qs.length+' questions';
  }
  search.addEventListener('input',apply); type.addEventListener('change',apply);
  document.getElementById('open').onclick=function(){qs.forEach(function(q){if(!q.classList.contains('hidden'))q.open=true;});};
  document.getElementById('close').onclick=function(){qs.forEach(function(q){q.open=false;});};
  apply();
})();
</script>
"""


def color(value):
    """Red (0) to green (100)."""
    hue = 0 if value is None else round(1.2 * max(0.0, min(100.0, value)))
    return f"hsl({hue},70%,62%)"


def score(result):
    """The leaderboard score of one question: the completeness when the judge says that the answer is correct, else 0."""
    return None if result is None else (result["completeness_pct"] if result["answer_correct"] else 0.0)


def chips(result, has_gold_docs):
    if result is None:
        return "<span class='chip ns'>not scored</span>"
    h = [f"<span class='chip' style='background:{color(score(result))}'>Score {score(result):.0f}</span>",
         f"<span class='chip' style='background:{color(100 if result['answer_correct'] else 0)}'>"
         f"{'Correct' if result['answer_correct'] else 'Not correct'}</span>",
         f"<span class='chip' style='background:{color(result['completeness_pct'])}'>"
         f"Completeness {result['completeness_pct']:.0f}</span>"]
    if has_gold_docs:
        h += [f"<span class='chip' style='background:{color(result['document_recall_pct'])}'>"
              f"Doc recall {result['document_recall_pct']:.0f}</span>",
              f"<span class='chip ns'>Invalid extra docs {result['invalid_extra_docs']}</span>"]
    if result.get("corrected"):
        h.append("<span class='chip ns' title='3 judges agreed that a retrieved document that is not gold has the answer; "
                 "it became gold for this system (official default)'>Corrected gold</span>")
    return "".join(h)


def system_card(spec, prediction, result, gold_docs, has_gold_docs):
    h = [f"<div class='sys'><div class='name'><span class='dot' style='background:{spec['color']}'></span>"
         f"{escape(spec['name'])}</div><div class='chips'>{chips(result, has_gold_docs)}</div>"]
    if prediction is None or not prediction.get("generated_answer"):
        h.append("<div class='answer none'>No answer (the official scorer skipped this question).</div></div>")
        return "".join(h)
    h.append(f"<div class='answer'>{escape(prediction['generated_answer'])}</div>")
    if result and result.get("correctness_reasoning"):
        h.append(f"<div class='meta'>Judge: {escape(result['correctness_reasoning'])}</div>")
    docs = prediction.get("document_ids") or []
    if docs:
        h.append(f"<div class='docs'>Documents given ({len(docs)}; gold in green): "
                 + ", ".join(f"<span class='hit'>{escape(d)}</span>" if d in gold_docs else escape(d) for d in docs)
                 + "</div>")
    contexts = prediction.get("context") or []
    if contexts:
        total = sum(len(c) for c in contexts)
        h.append(f"<details class='ctx'><summary>Retrieved context: {len(contexts)} items, {total:,} characters "
                 f"(first {CONTEXT_CHARS} characters of each)</summary><ol>"
                 + "".join(f"<li>{escape(c[:CONTEXT_CHARS])}{'…' if len(c) > CONTEXT_CHARS else ''}</li>" for c in contexts)
                 + "</ol></details>")
    h.append("</div>")
    return "".join(h)


def updated_gold(folder):
    """question id -> gold document IDs after the official correction step, for this system."""
    file = folder / "questions_updated.jsonl"
    if not file.exists():
        return {}
    rows = (json.loads(line) for line in file.read_text().splitlines() if line.strip())
    return {r["question_id"]: set(r.get("expected_doc_ids") or []) for r in rows}


def build(out, config, run_dir):
    questions = json.loads((bc.BENCH_DIR / "data" / "pilot_questions.json").read_text())
    systems = []
    for spec in config["systems"]:
        if spec["name"] not in out["systems"]:
            continue
        folder = Path(out["systems"][spec["name"]]["folder"])
        predictions = {p["question_id"]: p for p in json.loads((folder / "predictions.json").read_text())}
        results = {r["question_id"]: r for r in json.loads((folder / "results.json").read_text())["questions"]}
        systems.append((spec, predictions, results, updated_gold(folder)))

    h = head("EnterpriseRAG-Bench · questions and answers · 4Minds")
    h[-1] = h[-1].replace("</style>", PAGE_CSS + "</style>")
    h.append(header(f"Official scorer, judge {escape(out['judge']['judge'])}"))
    h.append(tabs("answers", rel(run_dir / "summary" / "report.html", run_dir), "#"))
    h.append("<div class='label'>Diagnosis</div><h1>Questions and answers</h1>"
             f"<p class='lead'>Each of the {len(questions)} pilot questions with its gold answer, gold facts and gold "
             "documents, and the answer of each system with its official result (0–100; red is low, green is high). "
             "Score is the leaderboard score of the question: the completeness when the judge says that the answer is "
             "correct, else 0. The small boxes on the right of each question are the Score of each system, in the order "
             "of the legend. Click a question to open it.</p>")
    h.append("<div class='legend'>" + "".join(f"<span><span class='dot' style='background:{spec['color']}'></span>"
                                              f"{escape(spec['name'])}</span>" for spec, *_ in systems) + "</div>")
    types = sorted({q["question_type"] for q in questions})
    h.append("<div class='controls'><input id='search' type='search' placeholder='Search questions, answers, facts'>"
             "<select id='type'><option value=''>All question types</option>"
             + "".join(f"<option value='{escape(t)}'>{escape(t.replace('_', ' '))}</option>" for t in types)
             + "</select><button id='open'>Open all</button><button id='close'>Close all</button>"
             "<span class='count' id='count'></span></div>")

    for q in questions:
        qid, gold_docs = q["question_id"], set(q["expected_doc_ids"])
        mini = "".join(
            f"<span style='background:{color(score(results.get(qid)))}' data-tip='{escape(spec['name'])}'>"
            + (f"{score(results[qid]):.0f}" if qid in results else "–") + "</span>"
            for spec, _, results, _ in systems)
        h.append(f"<details class='q' data-type='{escape(q['question_type'])}'><summary>"
                 f"<div class='qid'>{escape(qid)}<small>{escape(q['question_type'].replace('_', ' '))}</small></div>"
                 f"<div class='qtext'>{escape(q['question'])}</div><div class='mini'>{mini}</div></summary><div class='body'>")
        h.append(f"<div class='gold'><h4>Gold answer</h4><div>{escape(q['gold_answer'])}</div>"
                 f"<h4 style='margin-top:14px'>Gold facts ({len(q['answer_facts'])})</h4><ul>"
                 + "".join(f"<li>{escape(f)}</li>" for f in q["answer_facts"]) + "</ul>"
                 + (f"<h4 style='margin-top:14px'>Gold documents</h4><div class='docs'>{escape(', '.join(q['expected_doc_ids']))}</div>"
                    if q["expected_doc_ids"] else "<div class='meta'>No gold documents (document metrics do not apply).</div>")
                 + "</div><div class='systems'>")
        for spec, predictions, results, updated in systems:
            h.append(system_card(spec, predictions.get(qid), results.get(qid), updated.get(qid, gold_docs), bool(gold_docs)))
        h.append("</div></div></details>")

    h.append(SCRIPT)
    h.append(f"<footer>4Minds · EnterpriseRAG-Bench · generated by make_report.py (answers_page.py) from "
             f"{escape(rel(run_dir / 'summary' / 'scores.json', bc.BENCH_DIR))}. This page has the answers, so git does "
             "not track it.</footer></div></body></html>")
    return "\n".join(h)


def write(out, config, run_dir):
    target = Path(run_dir) / "answers.html"
    target.write_text(build(out, config, Path(run_dir)))
    return target

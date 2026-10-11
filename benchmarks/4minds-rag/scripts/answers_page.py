"""runs/<run>/answers.html: each question with its gold data and the answer and scores of each system.

make_report.py calls write(). The page has the answers, so it is outside summary/ (git does not
track answers; see .gitignore). Each retrieved context item shows only its first CONTEXT_CHARS
characters, because the full contexts are about 10 MB per run.
"""
import json
from html import escape
from pathlib import Path

import bench_common as bc
from report_html import head, header, rel

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
  font-variant-numeric:tabular-nums; color:#111; }
.body { padding:20px; }
.gold { border:1px solid rgba(167,139,250,0.35); background:rgba(84,63,237,0.08); border-radius:14px; padding:16px 18px; margin-bottom:20px; }
.gold h4, .sys h4 { margin:0 0 8px; font-weight:400; font-size:13px; color:var(--muted); text-transform:uppercase; letter-spacing:0.08em; }
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
    """Red (0) to green (1), the same scale for every metric (all are higher-is-better)."""
    hue = 0 if value is None else round(120 * max(0.0, min(1.0, value)))
    return f"hsl({hue},70%,62%)"


def chip(label, value):
    if value is None:
        return f"<span class='chip ns' title='not scored'>{escape(label)} n/s</span>"
    return f"<span class='chip' style='background:{color(value)}'>{escape(label)} {value * 100:.0f}</span>"


def details(partial):
    """(question id, metric key) -> details of the scored record (the last one without an error)."""
    out = {}
    if partial.exists():
        for line in partial.read_text().splitlines()[1:]:
            record = json.loads(line)
            if "metric" in record and not record.get("error"):
                out[(record["id"], record["metric"])] = record.get("details") or {}
    return out


CHIPS = [("Accuracy", "ragas_answer_accuracy"), ("FC P", "ragas_factual_correctness_precision"),
         ("FC R", "ragas_factual_correctness_recall"), ("FC F1", "ragas_factual_correctness_f1"),
         ("Summ.", "deepeval_summarization"), ("Halluc.", "deepeval_hallucination"),
         ("Doc P", "retrieval_documents_precision"), ("Doc R", "retrieval_documents_recall"),
         ("Doc F1", "retrieval_documents_f1")]


def system_card(spec, prediction, scores, info, gold_docs):
    h = [f"<div class='sys'><div class='name'><span class='dot' style='background:{spec['color']}'></span>"
         f"{escape(spec['name'])}</div><div class='chips'>"]
    if prediction is not None:
        h += [chip(label, scores[name]) for label, name in CHIPS if scores[name] != "skip"]
    h.append("</div>")
    if prediction is None:
        h.append("<div class='answer none'>No answer (the question failed in the source run).</div></div>")
        return "".join(h)
    h.append(f"<div class='answer'>{escape(prediction['generated_answer'])}</div>")
    notes = []
    fc = info.get("ragas_factual_correctness")
    if fc:
        notes.append(f"Claims: {fc['tp']} supported, {fc['fp']} not supported, {fc['fn']} gold claims missing")
    hal = info.get("deepeval_hallucination")
    if hal:
        notes.append(f"Hallucination: {hal['contradicted']} of {hal['contexts']} gold facts with verdict 'no'")
    if notes:
        h.append("<div class='meta'>" + " · ".join(escape(n) for n in notes) + "</div>")
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


def build(out, config, run_dir, export=False):
    """The page; with export, only the page body (with its script) for export_page.py."""
    import export_page
    questions = json.loads(Path(bc.profile.QUESTION_FILES["all"]).read_text())
    specs = {spec["name"]: spec for spec in config["systems"]}
    name = out["scorer"]["name"]
    judge = out["scorer"]["judge"].get("backend") or out["scorer"]["judge"].get("model")
    systems = []
    for system, s in out["systems"].items():
        folder = Path(s["folder"])
        data = json.loads((folder / f"{name}.json").read_text())
        predictions = {p["question_id"]: p for p in json.loads((folder / "predictions.json").read_text())}
        systems.append((specs[system], predictions, data["scores"], details(folder / f"{name}.partial.jsonl")))

    h = head(f"4Minds RAG · questions and answers · {escape(name)}")
    h[-1] = h[-1].replace("</style>", PAGE_CSS + "</style>")
    export_file = run_dir / "export" / export_page.file_name(run_dir)
    h.append(header(f"Scorer {escape(name)}, judge {escape(judge)}<br>"
                    f"<a href='{escape(rel(run_dir / 'summary' / 'report.html', run_dir))}'>Back to the report</a>"
                    + (f" · <a href='{escape(rel(export_file, run_dir))}' download='{escape(export_file.name)}'>Export for "
                       "sharing</a>" if export_file.exists() else "")))
    body_start = len(h)
    h.append("<div class='label'>Diagnosis</div><h1>Questions and answers</h1>"
             f"<p class='lead'>Each of the {len(questions)} questions with its gold answer, gold facts and gold documents, "
             "and the answer of each system with its scores (0–100; red is low, green is high; n/s = not scored). The "
             "small boxes on the right of each question are the Answer Accuracy of each system, in the order of the "
             "legend. Click a question to open it.</p>")
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
            f"<span style='background:{color(sc.get('ragas_answer_accuracy', {}).get(qid))}' "
            f"title='{escape(spec['name'])}: Answer Accuracy'>"
            + (f"{sc['ragas_answer_accuracy'][qid] * 100:.0f}" if sc.get("ragas_answer_accuracy", {}).get(qid) is not None
               else "–") + "</span>"
            for spec, _, sc, _ in systems)
        h.append(f"<details class='q' data-type='{escape(q['question_type'])}'><summary>"
                 f"<div class='qid'>{escape(qid)}<small>{escape(q['question_type'].replace('_', ' '))}</small></div>"
                 f"<div class='qtext'>{escape(q['question'])}</div><div class='mini'>{mini}</div></summary><div class='body'>")
        h.append(f"<div class='gold'><h4>Gold answer</h4><div>{escape(q['gold_answer'])}</div>"
                 f"<h4 style='margin-top:14px'>Gold facts ({len(q['answer_facts'])})</h4><ul>"
                 + "".join(f"<li>{escape(f)}</li>" for f in q["answer_facts"]) + "</ul>"
                 + (f"<h4 style='margin-top:14px'>Gold documents</h4><div class='docs'>{escape(', '.join(q['expected_doc_ids']))}</div>"
                    if q["expected_doc_ids"] else "<div class='meta'>No gold documents (document metrics do not apply).</div>")
                 + "</div><div class='systems'>")
        for spec, predictions, scores, info in systems:
            per_q = {}
            for _, n in CHIPS:
                if qid in scores.get(n, {}):
                    per_q[n] = scores[n][qid]
                elif n.startswith("retrieval_documents") and not gold_docs:
                    per_q[n] = "skip"
                else:
                    per_q[n] = None
            h.append(system_card(spec, predictions.get(qid), per_q,
                                 {m: d for (i, m), d in info.items() if i == qid}, gold_docs))
        h.append("</div></div></details>")

    h.append(SCRIPT)
    if export:
        return h[body_start:]
    h.append(f"<footer>4Minds · 4Minds RAG · generated by make_report.py (answers_page.py) from "
             f"{escape(rel(run_dir / 'summary' / 'scores.json', bc.BENCH_DIR))}. This page has the answers, so git does "
             "not track it.</footer></div></body></html>")
    return "\n".join(h)


def write(out, config, run_dir):
    target = Path(run_dir) / "answers.html"
    target.write_text(build(out, config, Path(run_dir)))
    return target

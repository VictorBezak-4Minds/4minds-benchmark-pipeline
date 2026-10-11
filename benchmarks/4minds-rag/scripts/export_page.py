"""runs/<run>/export/4minds-rag_<run>.html: the report and the question browser in one file to share.

make_report.py calls write(). The file has the CSS, the logo, the data and the scripts inline and
no links to local files, so it opens anywhere. Only the fonts come from Typekit and Google Fonts;
without the internet the page uses the system font. Two tabs (#report and #answers) show the two
pages. "Download this file" saves the file again from the browser, in its first state.
The file has the answers, so it is outside summary/ (git does not track answers).
"""
import json
from html import escape
from pathlib import Path

import answers_page
from report_html import head, header

BUTTON_STYLE = "color:#fff;border-color:var(--violet)"

EXPORT_CSS = """
.tabs { display:flex; flex-wrap:wrap; gap:8px; margin:-16px 0 40px; }
.tabs a, .tabs button { padding:8px 16px; border-radius:999px; border:1px solid var(--border); color:var(--muted);
  font:inherit; font-size:14px; background:none; cursor:pointer; }
.tabs a.active { color:#fff; border-color:var(--violet); background:rgba(84,63,237,0.18); text-decoration:none; }
.tabs button { margin-left:auto; color:#fff; border-color:var(--violet); }
.tabs button:hover, .tabs a:hover { text-decoration:none; border-color:var(--violet); }
"""

SCRIPT = """
<script>
(function(){
  var report=document.getElementById('tab-report'), answers=document.getElementById('tab-answers');
  function show(){
    var a=location.hash==='#answers';
    report.hidden=a; answers.hidden=!a;
    document.getElementById('to-report').classList.toggle('active',!a);
    document.getElementById('to-answers').classList.toggle('active',a);
  }
  window.addEventListener('hashchange',function(){show();window.scrollTo(0,0);});
  show();
  document.getElementById('download').onclick=function(){
    var copy=document.documentElement.cloneNode(true);
    copy.querySelector('#tab-report').hidden=false; copy.querySelector('#tab-answers').hidden=true;
    [].forEach.call(copy.querySelectorAll('details'),function(d){d.open=false;});
    [].forEach.call(copy.querySelectorAll('details.q'),function(d){d.classList.remove('hidden');});
    var blob=new Blob(['<!doctype html>\\n'+copy.outerHTML],{type:'text/html'}), url=URL.createObjectURL(blob),
        link=document.createElement('a');
    link.href=url; link.download=FILE_NAME; document.body.appendChild(link); link.click();
    setTimeout(function(){URL.revokeObjectURL(url); link.remove();},0);
  };
})();
</script>
"""


def file_name(run_dir):
    return f"4minds-rag_{Path(run_dir).name}.html"


def build(out, config, run_dir, report_body):
    judge = out["scorer"]["judge"].get("backend") or out["scorer"]["judge"].get("model")
    name = file_name(run_dir)
    h = head(f"4Minds RAG · {escape(Path(run_dir).name)} · 4Minds")
    h[-1] = h[-1].replace("</style>", answers_page.PAGE_CSS + EXPORT_CSS + "</style>")
    h.append(header(f"Generated {escape(out['created'])}<br>Scorer {escape(out['scorer']['name'])}, judge {escape(judge)}"))
    h.append("<nav class='tabs'><a id='to-report' href='#report'>Report</a>"
             "<a id='to-answers' href='#answers'>Questions and answers</a>"
             "<button id='download' type='button'>Download this file</button></nav>")
    h.append("<div id='tab-report'>" + "\n".join(report_body) + "</div>")
    h.append("<div id='tab-answers' hidden>" + "\n".join(answers_page.build(out, config, Path(run_dir), export=True))
             + "</div>")
    h.append(SCRIPT.replace("FILE_NAME", json.dumps(name)))
    h.append(f"<footer>4Minds · 4Minds RAG · run {escape(Path(run_dir).name)} · exported by make_report.py. One file: "
             "send it as it is. It has the questions, the gold data and the answers of every system.</footer>"
             "</div></body></html>")
    return "\n".join(h)


def write(out, config, run_dir, report_body):
    target = Path(run_dir) / "export" / file_name(run_dir)
    target.parent.mkdir(exist_ok=True)
    target.write_text(build(out, config, run_dir, report_body))
    return target

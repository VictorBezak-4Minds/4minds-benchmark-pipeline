"""Shared parts of the benchmark HTML reports, in the 4Minds web style.

Each benchmark keeps its own make_report.py with its text, metrics and sections. The page is
one file: inline CSS and logo, fonts from Typekit/Google Fonts (system fallback when offline).
"""
import json
import os
from html import escape
from pathlib import Path

LOGO = Path("/Users/victorbezak/Documents/4minds-main/4minds-platform/frontend-backend/frontend/public/assets/fullLogoWhite.svg")
SYSTEM_COLORS = {"4minds_constellations": "#543fed", "4minds_symi": "#a78bfa", "gemini": "#80aeff",
                 "rag_engine": "#5eead4", "lightrag": "#fbbf24"}
# Basic bundle (scatter with error bars). The hash is of the file from cdn.plot.ly, which is
# identical to plotly-basic.min.js in the npm package plotly.js-basic-dist-min@4.1.2.
PLOTLY_SCRIPT = ("<script src='https://cdn.plot.ly/plotly-basic-4.1.2.min.js' "
                 "integrity='sha384-CQVnjjRLr7qiE0NRUOMECQiOsJiFOrqPu+WrTttl7hUk5w+7FaiJA+y3SVfjpksc' "
                 "crossorigin='anonymous'></script>")

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
.grid .card { min-width:0; }
.grid .bar-row { grid-template-columns:minmax(0,1fr) 120px; row-gap:6px; }
.grid .bar-name { grid-column:1 / -1; }
.card h3 { position:relative; }
.info { display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px; margin-left:8px;
  border-radius:50%; border:1px solid rgba(255,255,255,0.35); color:var(--muted); font-size:11px; line-height:1;
  vertical-align:3px; cursor:help; }
.info:hover, .info:focus { color:#fff; border-color:var(--violet); outline:none; }
.info .tip { visibility:hidden; opacity:0; position:absolute; z-index:10; top:calc(100% + 10px); left:0; right:0;
  padding:14px 16px; background:#26262d; border:1px solid rgba(255,255,255,0.14); border-radius:12px;
  box-shadow:0 12px 32px rgba(0,0,0,0.5); color:rgba(255,255,255,0.85); font-size:13px; line-height:1.5;
  letter-spacing:0; white-space:normal; transition:opacity .12s; pointer-events:none; }
.info .tip span { display:block; margin-bottom:8px; } .info .tip span:last-child { margin-bottom:0; }
.info .tip .src { color:var(--muted); font-size:12px; }
.info .tip .h { margin-bottom:4px; color:var(--muted); font-size:11px; letter-spacing:0.08em; text-transform:uppercase; }
.info .tip .h:not(:first-child) { margin-top:14px; }
.info:hover .tip, .info:focus .tip { visibility:visible; opacity:1; }
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
.tabs { display:flex; flex-wrap:wrap; gap:8px; margin:-16px 0 40px; }
.tabs a, .tabs button { padding:8px 16px; border-radius:999px; border:1px solid var(--border); color:var(--muted);
  font:inherit; font-size:14px; background:none; cursor:pointer; }
.tabs a.active { color:#fff; border-color:var(--violet); background:rgba(84,63,237,0.18); text-decoration:none; }
.tabs button { margin-left:auto; color:#fff; border-color:var(--violet); }
.tabs button:hover, .tabs a:hover { text-decoration:none; border-color:var(--violet); }
footer { margin-top:80px; padding-top:24px; border-top:1px solid var(--border); color:var(--muted); font-size:13px; }
@media (max-width:720px) { .bar-row { grid-template-columns:1fr; } h1 { font-size:34px; } }
"""


def head(title):
    return [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
            f"<title>{title}</title>",
            "<link rel='stylesheet' href='https://use.typekit.net/ipe4ndc.css'>",
            "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500&display=swap'>",
            f"<style>{CSS}</style></head><body><div class='wrap'>"]


def header(meta):
    logo = LOGO.read_text() if LOGO.exists() else "<strong>4Minds</strong>"
    return f"<header><div>{logo}</div><div class='meta'>{meta}</div></header>"


def tabs(active, report_href, answers_href, extra=""):
    """The pill bar under the header that switches between the report and the question browser."""
    items = [("report", "Report", report_href), ("answers", "Questions and answers", answers_href)]
    links = "".join(f"<a id='to-{key}' class='{'active' if key == active else ''}' href='{escape(href)}'>{label}</a>"
                    for key, label, href in items)
    return f"<nav class='tabs'>{links}{extra}</nav>"


DOWNLOAD_BUTTON = "<button id='download' type='button'>Download this file</button>"

# Saves the page again from the browser, in its first state. Relative links become absolute, so the
# saved copy still opens the hub files on this machine. Charts are emptied, so they draw again on open.
DOWNLOAD_SCRIPT = """<script>
(function(){
  document.getElementById('download').onclick=function(){
    var copy=document.documentElement.cloneNode(true);
    [].forEach.call(copy.querySelectorAll('details'),function(d){d.open=false;});
    [].forEach.call(copy.querySelectorAll('.js-plotly-plot'),function(d){d.className='';d.removeAttribute('style');d.innerHTML='';});
    [].forEach.call(copy.querySelectorAll('[id$="-fallback"]'),function(d){d.style.display='';});
    [].forEach.call(copy.querySelectorAll('a[href]'),function(a){
      var v=a.getAttribute('href'); if(v.charAt(0)!=='#')a.setAttribute('href',new URL(v,location.href).href);
    });
    var blob=new Blob(['<!doctype html>\\n'+copy.outerHTML],{type:'text/html'}), url=URL.createObjectURL(blob),
        link=document.createElement('a');
    link.href=url; link.download=FILE_NAME; document.body.appendChild(link); link.click();
    setTimeout(function(){URL.revokeObjectURL(url); link.remove();},0);
  };
})();
</script>"""


def download_bar():
    """The pill bar with only the download button, for a report without a question browser."""
    return f"<nav class='tabs'>{DOWNLOAD_BUTTON}</nav>"


def download_script(summary_dir):
    """The script of DOWNLOAD_BUTTON for runs/<run>/summary/report.html. Put it before the footer.

    The saved file is <benchmark>_<run>_report.html.
    """
    run_dir = Path(summary_dir).resolve().parent
    return DOWNLOAD_SCRIPT.replace("FILE_NAME", json.dumps(f"{run_dir.parent.parent.name}_{run_dir.name}_report.html"))


def info(paragraphs, source=None):
    """An "i" icon that shows the paragraphs on hover or keyboard focus. Put it in a .card h3.

    Each item is a paragraph string or a (heading, [paragraphs]) block.
    """
    body = ""
    for p in paragraphs:
        if isinstance(p, tuple):
            heading, items = p
            body += f"<span class='h'>{escape(heading)}</span>" + "".join(f"<span>{escape(i)}</span>" for i in items)
        else:
            body += f"<span>{escape(p)}</span>"
    if source:
        body += f"<span class='src'>{escape(source)}</span>"
    return f"<span class='info' tabindex='0' aria-label='About this metric'>i<span class='tip' role='tooltip'>{body}</span></span>"


def title_with_info(title, paragraphs, source=None):
    """Escaped title text with the info icon kept on the same line as the last word."""
    first, _, last = title.rpartition(" ")
    return (f"{escape(first)} " if first else "") + f"<span style='white-space:nowrap'>{escape(last)}{info(paragraphs, source)}</span>"


def pct(x, digits=1):
    return "n/a" if x is None else f"{x * 100:.{digits}f}"


def bar(name, sub, r, color, scale_max=1.0):
    """One horizontal bar; r has mean, ci_low, ci_high and n (or is None)."""
    if not r:
        return (f'<div class="bar-row"><div class="bar-name">{escape(name)}<small>{escape(sub)}</small></div>'
                f'<div class="track"></div><div class="val">n/a</div></div>')
    w = lambda v: max(0.0, min(100.0, v / scale_max * 100))
    return (f'<div class="bar-row"><div class="bar-name">{escape(name)}<small>{escape(sub)}</small></div>'
            f'<div class="track"><div class="fill" style="width:{w(r["mean"]):.2f}%;background:{color}"></div>'
            f'<div class="ci" style="left:{w(r["ci_low"]):.2f}%;width:{w(r["ci_high"]) - w(r["ci_low"]):.2f}%"></div></div>'
            f'<div class="val">{pct(r["mean"])}<small>95% CI {pct(r["ci_low"])}–{pct(r["ci_high"])} · n={r["n"]}</small></div></div>')


def quality_latency(div_id, points, quality_title, latency_title="Median latency per question (s)"):
    """Plotly scatter, one point per system: quality (x, higher is better), median latency (y, lower is better).

    points: dicts with key, name, quality, quality_low, quality_high (0-1 scale), latency, latency_p90,
    hover (extra text lines) and optional color (default SYSTEM_COLORS[key]). The CI and the p90 are only
    in the hover text.
    """
    traces = []
    for p in points:
        if p.get("quality") is None or p.get("latency") is None:
            continue
        hover = [f"<b>{escape(p['name'])}</b>",
                 f"{quality_title}: {pct(p['quality'])} (95% CI {pct(p['quality_low'])}–{pct(p['quality_high'])})",
                 f"Latency: median {p['latency']} s, p90 {p.get('latency_p90', 'n/a')} s"] + [escape(line) for line in p.get("hover", [])]
        color = p.get("color") or SYSTEM_COLORS.get(p["key"], "#80aeff")
        traces.append({"type": "scatter", "mode": "markers", "name": p["name"],
                       "x": [p["quality"] * 100], "y": [p["latency"]], "text": ["<br>".join(hover)],
                       "hovertemplate": "%{text}<extra></extra>", "marker": {"size": 16, "color": color}})
    axis = {"gridcolor": "rgba(255,255,255,0.08)", "zeroline": False, "linecolor": "rgba(255,255,255,0.2)"}
    layout = {
        "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)", "height": 420,
        "font": {"family": "neue-haas-grotesk-display, Inter, -apple-system, sans-serif", "color": "rgba(255,255,255,0.8)", "size": 13},
        "margin": {"l": 64, "r": 24, "t": 36, "b": 96},
        "xaxis": {**axis, "title": {"text": f"{quality_title} (0–100)"}},
        "yaxis": {**axis, "title": {"text": latency_title}, "rangemode": "tozero"},
        "legend": {"orientation": "h", "y": -0.24, "x": 0},
        "hoverlabel": {"bgcolor": "#1c1c21", "bordercolor": "rgba(255,255,255,0.2)", "font": {"color": "#fff"}},
        "annotations": [{"xref": "paper", "yref": "paper", "x": 1, "y": 1.02, "showarrow": False, "xanchor": "right",
                         "yanchor": "bottom", "text": "Better: down and to the right",
                         "font": {"size": 12, "color": "rgba(255,255,255,0.5)"}}],
    }
    data = json.dumps({"traces": traces, "layout": layout}).replace("</", "<\\/")
    return (f"<div id='{div_id}'></div><p class='note' id='{div_id}-fallback'>The chart needs plotly.js from cdn.plot.ly "
            f"(an internet connection). The same numbers are in the tables of this report.</p>{PLOTLY_SCRIPT}"
            f"<script>(function(){{var d={data};if(!window.Plotly)return;"
            f"document.getElementById('{div_id}-fallback').style.display='none';"
            f"Plotly.newPlot('{div_id}',d.traces,d.layout,{{displayModeBar:false,responsive:true}});}})();</script>")


def rel(path, base):
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return str(path)

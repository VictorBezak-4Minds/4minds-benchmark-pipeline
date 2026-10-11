#!/usr/bin/env python3
"""Write runs/<run>/README.md and the run index runs/README.md.

A run README joins run.json (written by a person: title, purpose, status, notes) with what the
run folder shows: the config copy (config.json), the systems and their manifests, the caveats of
summary/scores.json, the asset folders (extra/, tests/, _superseded_*) and the audit steps that
used the folder, also under its earlier names (audit/moves/*.json).

    ./bench <benchmark> describe_<run> eval run_readme.py --run runs/<run> \\
        [--title "..."] [--purpose "..."] [--status "..."]

aggregate.py calls write() after each summary. --title, --purpose and --status update run.json.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

import bench_common as bc


def read_json(path):
    return json.loads(path.read_text()) if path.exists() else None


def bench_relative(path):
    try:
        return str(Path(path).resolve().relative_to(bc.BENCH_DIR))
    except ValueError:
        return str(path)


def earlier_names(run_dir):
    """Every path (relative to the benchmark folder) that the run folder or its contents had before."""
    pairs = []
    for record in sorted((bc.AUDIT_DIR / "moves").glob("*.json")):
        data = json.loads(record.read_text())
        root = Path(data["root"])
        pairs += [(bench_relative(root / old) if root.is_absolute() else old,
                   bench_relative(root / new) if root.is_absolute() else new) for old, new in data["moves"].items()]
    names, current = set(), {bench_relative(run_dir)}
    while current:
        found = set()
        for name in current:
            for old, new in pairs:
                if new == name or new.startswith(name + "/"):
                    found.add(old)
                elif name.startswith(new + "/"):
                    found.add(old + name[len(new):])
        current = found - names
        names |= found
    return {bench_relative(run_dir)} | names


def steps(run_dir):
    """(time, step, exit code, command) for each audit step whose command names the run folder."""
    log = bc.AUDIT_DIR / "audit.log"
    if not log.exists():
        return []
    patterns = [re.compile(r"(?<![\w./-])" + re.escape(n) + r"(?=[/\s]|$)") for n in sorted(earlier_names(run_dir))]
    starts, ends = {}, {}
    for line in log.read_text().splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("event") == "step_start" and any(p.search(record.get("command", "")) for p in patterns):
            starts[record.get("log")] = record
        elif record.get("event") == "step_end":
            ends[record.get("log")] = record.get("exit_code")
    out = []
    for key, record in starts.items():
        command = record["command"].replace(str(bc.BENCH_DIR) + "/", "").replace(str(bc.HUB) + "/", "")
        command = command.split(" ", 1)[1] if command.split(" ", 1)[0].endswith("python") else command
        out.append((record["time"], record["step"], ends.get(key, "no end record"), command))
    return sorted(out)


def systems(run_dir):
    """One row per <system>/<subset>/ folder. A runner writes manifest.json at the end, so a stopped
    run has none; then the answers are counted from runs.jsonl and the questions are unknown."""
    rows = []
    for config_file in sorted(run_dir.glob("*/*/run_config.json")):
        folder, system_dir = config_file.parent, config_file.parent.parent
        if system_dir.name.startswith("_") or system_dir.name in ("extra", "tests", "summary"):
            continue
        manifest = read_json(folder / "manifest.json") or {}
        summary = manifest.get("summary", {})
        if not manifest and (folder / "runs.jsonl").exists():
            log = bc.load_log(folder / "runs.jsonl")
            summary = {"answered": sum(r.get("status") == "ok" for r in log.values()), "questions": "?",
                       "failed": sum(r.get("status") != "ok" for r in log.values())}
        rows.append({"folder": f"{system_dir.name}/{folder.name}", "answered": summary.get("answered"),
                     "questions": summary.get("questions"), "failed": summary.get("failed"),
                     "cost": summary.get("estimated_cost_usd"), "started": manifest.get("started", ""),
                     "finished": manifest.get("finished", "not finished"),
                     "scored": (folder / "score_manifest.json").exists()
                               or any(p.with_name(p.name.replace(".partial.jsonl", ".json")).exists()
                                      for p in folder.glob("*.partial.jsonl"))})
    return rows


def assets(run_dir):
    out = []
    for folder in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        if folder.name in ("extra", "tests"):
            out += [f"{folder.name}/{child.name}/" for child in sorted(folder.iterdir()) if child.is_dir()]
        elif folder.name.startswith("_"):
            out.append(f"{folder.name}/")
    return out


def copy_config(run_dir, config_file):
    """Keep the config that made the summary in the run, so a later edit of configs/ cannot change its meaning."""
    raw = Path(config_file).read_bytes()
    record = {"source": bench_relative(config_file), "sha256": hashlib.sha256(raw).hexdigest(), "config": json.loads(raw)}
    (Path(run_dir) / "config.json").write_text(json.dumps(record, indent=2) + "\n")


def write(run_dir, title=None, purpose=None, status=None):
    run_dir = Path(run_dir).resolve()
    info_file = run_dir / "run.json"
    info = read_json(info_file) or {}
    info.update({k: v for k, v in (("title", title), ("purpose", purpose), ("status", status)) if v})
    info.setdefault("title", run_dir.name)
    info_file.write_text(json.dumps(info, indent=2) + "\n")

    config, summary = read_json(run_dir / "config.json"), read_json(run_dir / "summary" / "scores.json")
    lines = [f"# {info['title']}", "", "Generated by `pipeline/run_readme.py` from this folder and the audit log; "
             "edit `run.json`, not this file.", "", "| | |", "|---|---|", f"| Folder | `{bench_relative(run_dir)}/` |",
             f"| Status | {info.get('status', 'not set')} |"]
    if info.get("purpose"):
        lines.append(f"| Purpose | {info['purpose']} |")
    if info.get("derived_from"):
        source = os.path.relpath(bc.BENCH_DIR / info["derived_from"] / "README.md", run_dir)
        lines.append(f"| Answers from | [`{info['derived_from']}/`]({source}) (symlinks: "
                     f"{', '.join(info.get('linked_files', []))}) |")
        lines.append(f"| Change | {info.get('change', '')} |")
    judge = (summary or {}).get("benchmark", {})
    if isinstance(judge, dict) and judge.get("judge"):
        costs = [c for s in summary.get("systems", []) for c in (s.get("scoring", {}).get("judge_cost_usd"),
                                                                  s.get("faithfulness_jsonfix_judge_cost_usd"))
                 if c is not None]
        lines.append(f"| Judge | `{judge['judge']}` ({judge.get('judge_backend', 'openai-gpt-4o-mini')}; "
                     f"{', '.join(judge.get('judge_snapshot', []))})"
                     + (f"; measured judge cost {sum(costs):.2f} USD" if costs else "; judge cost not measured") + " |")
    if config:
        lines.append(f"| Config | `{config['source']}` (copy in `config.json`, sha256 `{config['sha256'][:12]}`): "
                     f"{config['config'].get('description', '')} |")
    if (run_dir / "summary" / "report.html").exists():
        lines.append("| Report | [summary/report.html](summary/report.html) (tables: [summary/report.md](summary/report.md)) |")
    if summary and summary.get("generated"):
        lines.append(f"| Summary made | {summary['generated']} |")
    lines += [""] + [f"{note}" for note in info.get("notes", [])]

    rows = systems(run_dir)
    if rows:
        lines += ["", "## Systems", "", "| Folder | Answered | Failed | Scored | Estimated cost (USD) | Started | Finished |",
                  "|---|---|---|---|---|---|---|"]
        lines += [f"| `{r['folder']}/` | {r['answered']}/{r['questions']} | {r['failed']} | {'yes' if r['scored'] else 'no'} "
                  f"| {r['cost'] if r['cost'] is not None else ''} | {r['started']} | {r['finished']} |" for r in rows]
    caveats = (summary or {}).get("caveats") or []
    if caveats:
        lines += ["", "## Deviations from the official protocol and caveats", ""] + [f"- {c}" for c in caveats]
    extra = assets(run_dir)
    if extra:
        lines += ["", "## Assets made from this run", ""] + [f"- `{a}`" for a in extra]
    history = steps(run_dir)
    if history:
        lines += ["", "## Steps (from audit/audit.log; earlier folder names included)", "",
                  "| Time (UTC) | Step | Exit | Command |", "|---|---|---|---|"]
        lines += [f"| {t} | {s} | {e} | `{c.replace('|', '/')}` |" for t, s, e, c in history]
    (run_dir / "README.md").write_text("\n".join(lines) + "\n")
    write_index()
    return run_dir / "README.md"


def write_index():
    lines = ["# Runs", "", "Generated by `pipeline/run_readme.py`. One line per run; open a run's README.md for details.", "",
             "| Run | Title | Status | Report |", "|---|---|---|---|"]
    for run_dir in sorted(p for p in bc.RUNS.iterdir() if p.is_dir()) if bc.RUNS.exists() else []:
        info = read_json(run_dir / "run.json") or {}
        report = f"[report]({run_dir.name}/summary/report.html)" if (run_dir / "summary" / "report.html").exists() else ""
        lines.append(f"| [`{run_dir.name}/`]({run_dir.name}/README.md) | {info.get('title', '')} | "
                     f"{info.get('status', '')} | {report} |")
    bc.RUNS.mkdir(exist_ok=True)
    (bc.RUNS / "README.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True, help="run folder, for example runs/<YYYY-MM-DD>_<name>")
    parser.add_argument("--title")
    parser.add_argument("--purpose")
    parser.add_argument("--status")
    args = parser.parse_args()
    print("wrote", write(args.run, args.title, args.purpose, args.status))


if __name__ == "__main__":
    main()

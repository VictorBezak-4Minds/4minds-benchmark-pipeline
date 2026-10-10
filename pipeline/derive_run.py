#!/usr/bin/env python3
"""Start a run that reuses the answers of another run, for a change after answering (another
judge or scorer). Only that change differs, because the answers are the same files.

Each <system>/<subset>/ folder of the source run that has predictions.json gets relative
symlinks to the source's answer files (ANSWER_FILES). The scores are written new in the
derived run; the source run is not changed. run.json records the source and the change.

    ./bench graphrag-bench derive_gptoss_full_haiku eval pipeline/derive_run.py \\
        --from runs/2026-10-10_gptoss-full --to runs/2026-10-10_gptoss-full_judge-haiku \\
        --change "Judge: Claude Haiku 5.5 instead of gpt-4o-mini" --title "..." [--systems a b]

Safe to run again with the same --from and --change: a link that already points to the same
file is kept. Another existing file, source or change stops the script.
"""
import argparse
import json
import os
from pathlib import Path

import bench_common as bc
import run_readme

ANSWER_FILES = ("predictions.json", "manifest.json", "run_config.json", "runs.jsonl", "raw.jsonl")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="source", required=True, help="source run, for example runs/2026-10-10_gptoss-full")
    parser.add_argument("--to", dest="target", required=True, help="new run folder, runs/<YYYY-MM-DD>_<name>")
    parser.add_argument("--change", required=True, help="the one change against the source run")
    parser.add_argument("--title", required=True)
    parser.add_argument("--purpose")
    parser.add_argument("--status", default="Answers linked; not scored yet.")
    parser.add_argument("--systems", nargs="*", help="system folders to link (default: all with predictions.json)")
    args = parser.parse_args()

    source, target = Path(args.source).resolve(), Path(args.target).resolve()
    if source.parent != bc.RUNS.resolve() or target.parent != bc.RUNS.resolve():
        raise SystemExit(f"--from and --to must be folders in {bc.RUNS}")
    folders = [p.parent for p in sorted(source.glob("*/*/predictions.json"))
               if not p.parent.parent.name.startswith("_") and p.parent.parent.name not in ("extra", "tests", "summary")]
    if args.systems:
        unknown = set(args.systems) - {f.parent.name for f in folders}
        if unknown:
            raise SystemExit(f"No answers for {sorted(unknown)} in {source}")
        folders = [f for f in folders if f.parent.name in args.systems]

    info_file = target / "run.json"
    info = json.loads(info_file.read_text()) if info_file.exists() else {}
    for key, value in (("derived_from", run_readme.bench_relative(source)), ("change", args.change)):
        if info.get(key) not in (None, value):
            raise SystemExit(f"{target} has {key} {info[key]!r}, not {value!r}. Use another --to.")

    plan = []
    for folder in folders:
        out = target / folder.parent.name / folder.name
        for name in ANSWER_FILES:
            if not (folder / name).exists():
                continue
            link, real = out / name, (folder / name).resolve()
            if link.is_symlink() and link.resolve() == real:
                continue
            if link.exists() or link.is_symlink():
                raise SystemExit(f"{link} exists and is not a link to {real}. Use another --to.")
            plan.append((link, real))
    for link, real in plan:
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(os.path.relpath(real, link.parent))

    info.update({"derived_from": run_readme.bench_relative(source), "change": args.change,
                 "linked_files": list(ANSWER_FILES)})
    target.mkdir(parents=True, exist_ok=True)
    info_file.write_text(json.dumps(info, indent=2) + "\n")
    run_readme.write(target, args.title, args.purpose, args.status if not info.get("status") else None)
    bc.audit("derive_run", source=str(source), target=str(target), change=args.change,
             systems=[f.parent.name for f in folders], links_made=len(plan))
    print(f"{target}: {len(plan)} links for {[f.parent.name for f in folders]}")


if __name__ == "__main__":
    main()

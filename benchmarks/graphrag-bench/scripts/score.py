#!/usr/bin/env python3
"""Score one system's predictions with the official GraphRAG-Bench generation_eval.py.

The official script runs unchanged from the pinned repo commit, with the embedding model
BAAI/bge-large-en-v1.5 and --detailed_output so that per-question scores are kept for confidence
intervals. The judge is an LLM backend (pipeline/llm_backends.json, --judge); the default
openai-gpt-4o-mini is the official judge. A backend's "judge_drop_params" are removed from each
judge request, its "judge_extra_body" is added, a backend with "judge_strip_code_fence" has the
JSON taken out of a code-fenced reply (pipeline/judge_hooks.py), and the judge tokens are counted. This wrapper records
the audit data: the repo commit and `git status`, pip freeze, the judge snapshot and settings,
the judge tokens and cost, the console log and the time. A folder is scored by one judge only.

  ./bench graphrag-bench score_pilot_gemini eval score.py --system-dir runs/2026-10-09_gemini-pilot/gemini/medical
Output in the same folder: generation_scores.json, score_console.log, score_manifest.json

Resumable (full runs): --shard-size 50 --parallel 8 splits the predictions into shards of at
most 50 (round robin, so each shard has a mix of question types) and scores 8 shards at a time.
The split is fixed in score_shards/plan.json. A shard is complete when its done.json says exit
code 0 and no failed sample. A rerun scores only the shards that are not complete, then merges
all shards. If predictions.json changes, the plan no longer matches and the script stops: move
score_shards/ to _superseded_score_shards_<time>/ first.
"""
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import bench_common as bc
import judge_hooks
import llm_backends

DEFAULT_JUDGE = "openai-gpt-4o-mini"
EMBEDDING = "BAAI/bge-large-en-v1.5"


def merge_shards(shard_files, out_file):
    """Join the per-question results of the shards; averages as in generation_eval.py (mean of non-NaN)."""
    merged = {}
    for path in shard_files:
        if not path.exists():
            continue
        for question_type, block in json.loads(path.read_text()).items():
            merged.setdefault(question_type, {"average_scores": {}, "detailed": []})["detailed"] += block.get("detailed") or []
    for block in merged.values():
        values = {}
        for item in block["detailed"]:
            for metric, score in (item.get("metrics") or {}).items():
                if isinstance(score, (int, float)) and not math.isnan(score):
                    values.setdefault(metric, []).append(score)
        block["average_scores"] = {m: sum(v) / len(v) for m, v in values.items()}
    out_file.write_text(json.dumps(merged, indent=2))


def text_sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def shard_plan(items, predictions_sha, shard_root, shard_size):
    """Write the shard plan the first time; later runs must find the same predictions and size."""
    plan_file = shard_root / "plan.json"
    if plan_file.exists():
        plan = json.loads(plan_file.read_text())
        if plan["predictions_sha256"] != predictions_sha or plan["shard_size"] != shard_size:
            sys.exit(f"{plan_file} was made for other predictions or another --shard-size. Move "
                     f"{shard_root.name}/ to _superseded_{shard_root.name}_<time>/ and run again.")
        return plan
    count = math.ceil(len(items) / shard_size)
    shards = []
    for i in range(count):
        part = items[i::count]
        folder = shard_root / f"shard_{i:03d}"
        folder.mkdir(parents=True, exist_ok=True)
        text = json.dumps(part, indent=1)
        (folder / "predictions.json").write_text(text)
        shards.append({"name": folder.name, "ids": [p["id"] for p in part], "predictions_sha256": text_sha256(text)})
    plan = {"created": bc.now(), "predictions_sha256": predictions_sha, "shard_size": shard_size, "shards": shards}
    plan_file.write_text(json.dumps(plan, indent=1))
    return plan


def shard_complete(folder, shard, judge):
    done = folder / "done.json"
    if not done.exists() or not (folder / "generation_scores.json").exists():
        return False
    marker = json.loads(done.read_text())
    return (marker.get("exit_code") == 0 and marker.get("failed_samples") == 0
            and marker.get("predictions_sha256") == shard["predictions_sha256"]
            and marker.get("judge", DEFAULT_JUDGE) == judge.name
            and marker.get("judge_strip_code_fence", False) == judge.judge_strip_code_fence)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--system-dir", required=True, help="folder with predictions.json")
    parser.add_argument("--num-samples", type=int, help="test only: score the first N per type into score_test/")
    parser.add_argument("--shards", type=int, default=1,
                        help="split the predictions into N files scored in parallel, then merge (scores unchanged)")
    parser.add_argument("--shard-size", type=int,
                        help="resumable: shards of at most N predictions, fixed in score_shards/plan.json")
    parser.add_argument("--parallel", type=int, default=8, help="with --shard-size: shards scored at the same time")
    parser.add_argument("--judge", default=DEFAULT_JUDGE,
                        help=f"LLM backend for the judge (default {DEFAULT_JUDGE}, the official judge)")
    args = parser.parse_args()
    if args.shard_size and (args.num_samples or args.shards != 1):
        sys.exit("--shard-size cannot be used with --num-samples or --shards.")
    system_dir = Path(args.system_dir).resolve()
    predictions = system_dir / "predictions.json"
    if not predictions.exists():
        sys.exit(f"Missing {predictions}")
    bc.acquire_lock(system_dir / ".score.lock")
    out_dir = system_dir / "score_test" if args.num_samples else system_dir
    out_dir.mkdir(exist_ok=True)
    out_file, log_file = out_dir / "generation_scores.json", out_dir / "score_console.log"
    earlier = json.loads((out_dir / "score_manifest.json").read_text()) if (out_dir / "score_manifest.json").exists() else {}
    if earlier and earlier.get("judge_backend", DEFAULT_JUDGE) != args.judge:
        sys.exit(f"{out_dir} was scored with judge {earlier.get('judge_backend', DEFAULT_JUDGE)}. Use a new run folder "
                 f"for judge {args.judge} (pipeline/derive_run.py).")
    if earlier and earlier.get("judge_strip_code_fence", False) != llm_backends.Backend(args.judge).judge_strip_code_fence:
        sys.exit(f"{out_dir} was scored with another judge_strip_code_fence setting. Move the score files to "
                 f"_superseded_<time>/ first.")

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=bc.UPSTREAM_REPO, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=bc.UPSTREAM_REPO, capture_output=True, text=True).stdout
    status = "\n".join(line for line in status.splitlines()
                       if "__pycache__" not in line and not line.endswith(".DS_Store"))
    if commit != bc.UPSTREAM_COMMIT or status.strip():
        sys.exit(f"Benchmark repo is not clean at {bc.UPSTREAM_COMMIT}: HEAD={commit} status={status!r}")
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True).stdout

    judge = llm_backends.Backend(args.judge)
    check = judge_hooks.preflight(judge)
    snapshot = check["snapshot"]
    items = json.loads(predictions.read_text())
    shard_root = out_dir / "score_shards"
    plan, skipped = None, []
    if args.shard_size:
        plan = shard_plan(items, bc.sha256(predictions), shard_root, args.shard_size)
        all_jobs = [(shard_root / s["name"] / "predictions.json", shard_root / s["name"] / "generation_scores.json",
                     shard_root / s["name"] / "score_console.log") for s in plan["shards"]]
        jobs = [j for j, s in zip(all_jobs, plan["shards"]) if not shard_complete(j[0].parent, s, judge)]
        skipped = [s["name"] for j, s in zip(all_jobs, plan["shards"]) if j not in jobs]
        shards, parallel = len(all_jobs), max(1, args.parallel)
    else:
        shards = max(1, min(args.shards, len(items)))
        if shards == 1:
            jobs = [(predictions, out_file, log_file)]
        else:
            jobs = []
            for i in range(shards):
                folder = shard_root / f"shard_{i:02d}"
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "predictions.json").write_text(json.dumps(items[i::shards], indent=1))
                jobs.append((folder / "predictions.json", folder / "generation_scores.json", folder / "score_console.log"))
        all_jobs, parallel = jobs, len(jobs)

    def command_for(data_file, output_file):
        command = [sys.executable, "-X", "faulthandler", str(Path(__file__).resolve().parent / "score_launcher.py"), "--mode", "API",
                   "--model", judge.model, "--base_url", judge.base_url, "--embedding_model", EMBEDDING, "--data_file", str(data_file),
                   "--output_file", str(output_file), "--detailed_output"]
        return command + (["--num_samples", str(args.num_samples)] if args.num_samples else [])

    bc.audit("score_start", system_dir=str(system_dir), predictions=len(items), judge=judge.name, judge_snapshot=snapshot,
             judge_settings_sent=check["settings_sent"], judge_rate_limits=check["rate_limits"],
             shards=shards, to_score=len(jobs), skipped_complete=len(skipped), parallel=parallel)
    print(f"scoring {len(items)} predictions in {system_dir} with {judge.name} ({snapshot}), {shards} shard(s)"
          + (f"; {len(skipped)} already complete, {len(jobs)} to score, {parallel} at a time" if plan else ""))
    started, t0 = bc.now(), time.monotonic()
    stamp = started.replace(":", "").replace("-", "")[:15]
    judge_env = {"LLM_API_KEY": judge.api_key(), "JUDGE_DROP_PARAMS": ",".join(judge.judge_drop_params),
                 "JUDGE_STRIP_CODE_FENCE": "1" if judge.judge_strip_code_fence else "0",
                 "JUDGE_EXTRA_BODY": json.dumps(judge.judge_extra_body)}
    pending, running, codes = list(jobs), [], {}
    while pending or running:
        while pending and len(running) < parallel:
            job = pending.pop(0)
            log = job[2].open("w")
            running.append((job, log, subprocess.Popen(command_for(job[0], job[1]), cwd=bc.UPSTREAM_REPO,
                                                       env={**os.environ, **judge_env, "JUDGE_USAGE_FILE":
                                                            str(job[1].parent / f"judge_usage_{stamp}.json")},
                                                       stdout=log, stderr=subprocess.STDOUT, text=True)))
        time.sleep(1)
        for entry in [r for r in running if r[2].poll() is not None]:
            job, log, process = entry
            running.remove(entry)
            log.close()
            codes[job] = process.returncode
            if plan:
                shard = next(s for s in plan["shards"] if s["name"] == job[0].parent.name)
                failed = job[2].read_text().count("❌ Sample failed")
                (job[0].parent / "done.json").write_text(json.dumps(
                    {"finished": bc.now(), "exit_code": process.returncode, "failed_samples": failed,
                     "predictions_sha256": shard["predictions_sha256"], "judge": judge.name,
                     "judge_strip_code_fence": judge.judge_strip_code_fence}))
                print(f"  {shard['name']}: exit {process.returncode}, failed samples {failed}")
    incomplete = ([s["name"] for s in plan["shards"] if not shard_complete(shard_root / s["name"], s, judge)]
                  if plan else [])
    code = next((c for c in codes.values() if c != 0), 0) or (1 if incomplete else 0)
    wall = round(time.monotonic() - t0, 1)

    sharded = bool(plan) or shards > 1
    if sharded:
        merge_shards([j[1] for j in all_jobs], out_file)
        log_file.write_text("".join(
            f"===== {j[0].parent.name} (exit {codes.get(j, 'not run in this invocation')}) =====\n"
            f"{j[2].read_text() if j[2].exists() else ''}" for j in all_jobs))
    print("".join(line for line in log_file.read_text().splitlines(True)
                  if line.startswith(("Results for", "  ", "❌", "Evaluation complete")))[-3000:])

    scored, failed_samples = {}, 0
    if out_file.exists():
        result = json.loads(out_file.read_text())
        scored = {qt: len(v.get("detailed") or []) for qt, v in result.items()}
    failed_samples = log_file.read_text().count("❌ Sample failed")
    usage_files = sorted(out_dir.glob("judge_usage_*.json")) + (sorted(shard_root.glob("*/judge_usage_*.json")) if plan else [])
    usage = judge_hooks.read_usage(usage_files)
    manifest = {"started": started, "finished": bc.now(), "wall_clock_s": wall, "exit_code": code,
                "shards": shards, "shard_exit_codes": {j[0].parent.name if sharded else "all": c
                                                       for j, c in codes.items()},
                "shard_size": args.shard_size, "parallel": parallel, "skipped_complete_shards": skipped,
                "incomplete_shards": incomplete,
                "command": command_for(predictions, out_file)[1:], "benchmark_repo": str(bc.UPSTREAM_REPO),
                "benchmark_commit": commit,
                "benchmark_repo_clean": not status.strip(), "judge": judge.model, "judge_snapshot": snapshot,
                "judge_backend": judge.name, "judge_base_url": judge.base_url,
                "judge_dropped_params": judge.judge_drop_params,
                "judge_strip_code_fence": judge.judge_strip_code_fence, "judge_extra_body": judge.judge_extra_body,
                "judge_usage": usage,
                "judge_cost_usd": judge.cost(usage), "judge_usage_files": len(usage_files),
                "embedding_model": EMBEDDING, "predictions": len(items),
                "predictions_sha256": bc.sha256(predictions), "scored_per_type": scored,
                "failed_samples": failed_samples, "python": sys.version.split()[0], "pip_freeze": freeze.splitlines()}
    (out_dir / "score_manifest.json").write_text(json.dumps(manifest, indent=2))
    bc.audit("score_end", system_dir=str(system_dir), exit_code=code, wall_clock_s=wall, scored=scored,
             failed_samples=failed_samples)
    print(f"done in {wall} s, exit {code}, scored {scored}, failed samples {failed_samples}")
    sys.exit(code)


if __name__ == "__main__":
    main()

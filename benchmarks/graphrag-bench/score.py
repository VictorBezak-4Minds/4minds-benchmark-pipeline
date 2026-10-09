#!/usr/bin/env python3
"""Score one system's predictions with the official GraphRAG-Bench generation_eval.py.

The official script runs unchanged from the pinned repo commit, with the default judge
(gpt-4o-mini) and embedding model (BAAI/bge-large-en-v1.5), and --detailed_output so that
per-question scores are kept for confidence intervals. This wrapper records the audit data:
the repo commit and `git status`, pip freeze, the judge snapshot, the console log and the time.

  ./bench graphrag-bench score_pilot_gemini eval score.py --system-dir results/pilot/gemini/medical
Output in the same folder: generation_scores.json, score_console.log, score_manifest.json
"""
import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

import bench_common as bc

JUDGE = "gpt-4o-mini"
EMBEDDING = "BAAI/bge-large-en-v1.5"


def judge_snapshot(api_key):
    """One tiny request: the response `model` field names the exact snapshot that serves gpt-4o-mini."""
    response = requests.post("https://api.openai.com/v1/chat/completions", timeout=60,
                             headers={"Authorization": f"Bearer {api_key}"},
                             json={"model": JUDGE, "messages": [{"role": "user", "content": "Say OK."}],
                                   "max_tokens": 2, "temperature": 0})
    response.raise_for_status()
    return response.json().get("model")


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


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--system-dir", required=True, help="folder with predictions.json")
    parser.add_argument("--num-samples", type=int, help="test only: score the first N per type into score_test/")
    parser.add_argument("--shards", type=int, default=1,
                        help="split the predictions into N files scored in parallel, then merge (scores unchanged)")
    args = parser.parse_args()
    system_dir = Path(args.system_dir).resolve()
    predictions = system_dir / "predictions.json"
    if not predictions.exists():
        sys.exit(f"Missing {predictions}")
    bc.acquire_lock(system_dir / ".score.lock")
    out_dir = system_dir / "score_test" if args.num_samples else system_dir
    out_dir.mkdir(exist_ok=True)
    out_file, log_file = out_dir / "generation_scores.json", out_dir / "score_console.log"

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=bc.UPSTREAM_REPO, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=bc.UPSTREAM_REPO, capture_output=True, text=True).stdout
    status = "\n".join(line for line in status.splitlines()
                       if "__pycache__" not in line and not line.endswith(".DS_Store"))
    if commit != bc.UPSTREAM_COMMIT or status.strip():
        sys.exit(f"Benchmark repo is not clean at {bc.UPSTREAM_COMMIT}: HEAD={commit} status={status!r}")
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True).stdout

    api_key = bc.load_key("openai")
    snapshot = judge_snapshot(api_key)
    items = json.loads(predictions.read_text())
    shards = max(1, min(args.shards, len(items)))
    if shards == 1:
        jobs = [(predictions, out_file, log_file)]
    else:
        shard_root = out_dir / "score_shards"
        jobs = []
        for i in range(shards):
            folder = shard_root / f"shard_{i:02d}"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "predictions.json").write_text(json.dumps(items[i::shards], indent=1))
            jobs.append((folder / "predictions.json", folder / "generation_scores.json", folder / "score_console.log"))

    def command_for(data_file, output_file):
        command = [sys.executable, "-X", "faulthandler", str(bc.BENCH_DIR / "score_launcher.py"), "--mode", "API",
                   "--model", JUDGE, "--embedding_model", EMBEDDING, "--data_file", str(data_file),
                   "--output_file", str(output_file), "--detailed_output"]
        return command + (["--num_samples", str(args.num_samples)] if args.num_samples else [])

    bc.audit("score_start", system_dir=str(system_dir), predictions=len(items), judge=JUDGE, judge_snapshot=snapshot,
             shards=shards)
    print(f"scoring {len(items)} predictions in {system_dir} with {JUDGE} ({snapshot}), {shards} shard(s)")
    started, t0 = bc.now(), time.monotonic()
    processes = []
    for data_file, output_file, shard_log in jobs:
        log = shard_log.open("w")
        processes.append((subprocess.Popen(command_for(data_file, output_file), cwd=bc.UPSTREAM_REPO,
                                           env={**os.environ, "LLM_API_KEY": api_key},
                                           stdout=log, stderr=subprocess.STDOUT, text=True), log))
    codes = []
    for process, log in processes:
        codes.append(process.wait())
        log.close()
    code = next((c for c in codes if c != 0), 0)
    wall = round(time.monotonic() - t0, 1)

    if shards > 1:
        merge_shards([j[1] for j in jobs], out_file)
        log_file.write_text("".join(f"===== shard {i:02d} (exit {codes[i]}) =====\n{j[2].read_text()}"
                                    for i, j in enumerate(jobs)))
    print("".join(line for line in log_file.read_text().splitlines(True)
                  if line.startswith(("Results for", "  ", "❌", "Evaluation complete")))[-3000:])

    scored, failed_samples = {}, 0
    if out_file.exists():
        result = json.loads(out_file.read_text())
        scored = {qt: len(v.get("detailed") or []) for qt, v in result.items()}
    failed_samples = log_file.read_text().count("❌ Sample failed")
    manifest = {"started": started, "finished": bc.now(), "wall_clock_s": wall, "exit_code": code,
                "shards": shards, "shard_exit_codes": codes,
                "command": command_for(predictions, out_file)[1:], "benchmark_repo": str(bc.UPSTREAM_REPO),
                "benchmark_commit": commit,
                "benchmark_repo_clean": not status.strip(), "judge": JUDGE, "judge_snapshot": snapshot,
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

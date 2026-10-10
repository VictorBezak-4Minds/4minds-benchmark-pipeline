#!/usr/bin/env python3
"""Supplementary faithfulness score for Creative Generation, with one prompt fix.

At commit fdbab59 the verdict prompt of Evaluation/metrics/faithfulness.py does not ask for
JSON. gpt-4o-mini then answers in Markdown prose, the JSON parser finds no verdicts and the
official score is NaN (see audit/diagnostics/faithfulness_nan.json). This script
runs the official compute_faithfulness_score with the official judge settings, the same
10,000-character context limit and the same predictions, and adds one sentence to the end
of the verdict prompt that asks for the format of the prompt's own examples.

The official generation_scores.json is not changed. Output: <system-dir>/faithfulness_json_fix.json

    ./bench graphrag-bench faithfulness_pilot_gemini eval score_faithfulness.py --system-dir runs/2026-10-09_gemini-pilot/gemini/medical

Resumable: each score goes to faithfulness_json_fix.partial.jsonl when it is ready, and a rerun
scores only the answers that are not in it. An answer whose call raised an error is not saved,
so it is tried again; a NaN from the official parser is a result and is saved. If
predictions.json changes, the script stops: move the partial file away first.
"""
import argparse
import asyncio
import difflib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import bench_common as bc

sys.path.insert(0, str(bc.UPSTREAM_REPO))
from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic import SecretStr  # noqa: E402
from Evaluation.metrics import faithfulness as F  # noqa: E402

JUDGE = "gpt-4o-mini"
PROMPT_SUFFIX = ('\nReturn only a JSON list of objects with the keys "statement", "reason" and "verdict", '
                 "in the same format as the example outputs.\nOutput:\n")
OFFICIAL_PROMPT = F.FAITHFULNESS_EVALUATION_PROMPT


def write_patch():
    path = bc.AUDIT_DIR / "patches" / "faithfulness-fdbab59-json-format.diff"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(difflib.unified_diff(
        OFFICIAL_PROMPT.splitlines(True), (OFFICIAL_PROMPT + PROMPT_SUFFIX).splitlines(True),
        "a/Evaluation/metrics/faithfulness.py:FAITHFULNESS_EVALUATION_PROMPT",
        "b/Evaluation/metrics/faithfulness.py:FAITHFULNESS_EVALUATION_PROMPT")))
    return path


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--system-dir", required=True, help="folder with predictions.json")
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    system_dir = Path(args.system_dir).resolve()
    predictions = system_dir / "predictions.json"
    items = [i for i in json.loads(predictions.read_text()) if i["question_type"] == "Creative Generation"]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=bc.UPSTREAM_REPO, capture_output=True,
                            text=True).stdout.strip()
    if commit != bc.UPSTREAM_COMMIT:
        sys.exit(f"Benchmark repo is at {commit}, not {bc.UPSTREAM_COMMIT}")
    patch = write_patch()
    F.FAITHFULNESS_EVALUATION_PROMPT = OFFICIAL_PROMPT + PROMPT_SUFFIX

    llm = ChatOpenAI(model=JUDGE, api_key=SecretStr(bc.load_key("openai")), temperature=0.0, max_retries=3,
                     timeout=30, model_kwargs={"top_p": 1, "seed": 42, "presence_penalty": 0, "frequency_penalty": 0})
    semaphore = asyncio.Semaphore(args.concurrency)

    predictions_sha = bc.sha256(predictions)
    partial = system_dir / "faithfulness_json_fix.partial.jsonl"
    scores = {}
    if partial.exists():
        lines = [json.loads(line) for line in partial.read_text().splitlines() if line.strip()]
        if not lines or lines[0].get("predictions_sha256") != predictions_sha:
            sys.exit(f"{partial} was made for other predictions. Move it to _superseded_{partial.name} and run again.")
        scores = {r["id"]: r["value"] for r in lines[1:]}
    else:
        partial.write_text(json.dumps({"predictions_sha256": predictions_sha, "prompt_suffix": PROMPT_SUFFIX}) + "\n")
    todo = [i for i in items if i["id"] not in scores]
    errors, done = {}, 0

    async def one(item):
        nonlocal done
        async with semaphore:
            try:
                value = await F.compute_faithfulness_score(item["question"], item["generated_answer"],
                                                           item["context"], llm)
            except Exception as e:
                print(f"  {item['id']} failed: {type(e).__name__}: {e}"[:300])
                errors[item["id"]] = f"{type(e).__name__}: {e}"[:300]
                return
        scores[item["id"]] = None if math.isnan(value) else value
        with partial.open("a") as f:
            f.write(json.dumps({"id": item["id"], "value": scores[item["id"]]}) + "\n")
        done += 1
        if done % 20 == 0 or done == len(todo):
            print(f"  {done}/{len(todo)}")

    bc.audit("faithfulness_fix_start", system_dir=str(system_dir), items=len(items), already_scored=len(scores),
             patch=str(patch))
    print(f"faithfulness (JSON-format fix) for {len(items)} Creative Generation answers in {system_dir}; "
          f"{len(scores)} already scored, {len(todo)} to score")
    started, t0 = bc.now(), time.monotonic()
    await asyncio.gather(*(one(i) for i in todo))
    values = [v for v in scores.values() if v is not None]
    result = {
        "started": started, "finished": bc.now(), "wall_clock_s": round(time.monotonic() - t0, 1),
        "judge": JUDGE, "benchmark_commit": commit, "predictions_sha256": bc.sha256(predictions),
        "prompt_suffix": PROMPT_SUFFIX, "patch": str(patch), "concurrency": args.concurrency,
        "items": len(items), "scored": len(values), "nan": len(items) - len(values),
        "mean": sum(values) / len(values) if values else None, "scores": scores,
        "errors_not_scored": errors, "partial_file": str(partial),
    }
    (system_dir / "faithfulness_json_fix.json").write_text(json.dumps(result, indent=2))
    bc.audit("faithfulness_fix_end", system_dir=str(system_dir), scored=len(values), nan=result["nan"],
             errors=len(errors), mean=result["mean"], wall_clock_s=result["wall_clock_s"])
    print(f"done: scored {len(values)}/{len(items)}, NaN {result['nan']}, errors {len(errors)} (rerun to retry), "
          f"mean {result['mean']}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

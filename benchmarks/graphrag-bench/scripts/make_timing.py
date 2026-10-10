#!/usr/bin/env python3
"""Estimate the full Medical run (2,062 questions) from the pilot. Writes <pilot>/timing.json.

    ./bench graphrag-bench timing_pilot eval make_timing.py --matrix configs/comparisons/gemini.json --run runs/2026-10-09_gemini-pilot

The matrix file gives each system's planned workers, --timeout and index note (or the index
manifest to read the build time from), and "parallel_paths": the paths run at the same time;
a path is a list of lanes that run at the same time, and the systems in a lane run one after
another.

Answering: for each question type, (number of full-run questions) x (mean latency of the
successful call for that type), plus the pilot retry rate x (planned timeout + backoff),
/ workers, times 1.2 for the slow tail.
Scoring: generation_eval.py scores 3 samples at a time, one question type after another.
The pilot gives the time for one such round per system; score.py --shards S divides each
type into S parallel parts. The supplementary faithfulness pass runs at the same time.
"""
import argparse
import json
import math
import statistics
from collections import Counter
from pathlib import Path

import bench_common as bc
from aggregate import load_matrix

BACKOFF_S = 15.0
OVERHEAD, MODEL_LOAD_S, SCORER_CONCURRENCY = 1.2, 15.0, 3
TYPES = ["Fact Retrieval", "Complex Reasoning", "Contextual Summarize", "Creative Generation"]


def rounds(counts, shards):
    return sum(math.ceil(math.ceil(n / shards) / SCORER_CONCURRENCY) for n in counts.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--matrix", required=True, help="matrix file, for example configs/comparisons/gptoss.json")
    parser.add_argument("--run", "--results", dest="results", required=True, help="run folder, for example runs/<YYYY-MM-DD>_<name>")
    parser.add_argument("--shards", type=int, default=8, help="score.py --shards for the full run")
    args = parser.parse_args()
    matrix = load_matrix(args.matrix)
    root = Path(args.results)

    full = Counter(q["question_type"] for q in json.loads(bc.QUESTION_FILES["medical"].read_text())
                   if q["source"].lower().startswith("medical"))
    plan, index_note = {}, {}
    for s in matrix["systems"]:
        plan[s["key"]] = (s["workers"], s["timeout_s"], s.get("timing_note", ""))
        if s.get("index_manifest"):
            index_manifest = bc.BENCH_DIR / s["index_manifest"]
            index_note[s["key"]] = (f"{json.loads(index_manifest.read_text())['index_wall_clock_s'] / 60:.0f} min, reused"
                                    if index_manifest.exists() else "not finished")
        else:
            index_note[s["key"]] = s.get("index_note", "")

    systems, answer_h, score_h = {}, {}, {}
    for key, (workers, timeout, note) in plan.items():
        folder = root / key / "medical"
        runs = folder / "runs.jsonl"
        if not runs.exists():
            continue
        records = [r for r in bc.load_log(runs).values() if r["status"] == "ok"]
        by_type = {}
        for r in records:
            by_type.setdefault(r["prediction"]["question_type"], []).append(r["latency_s"] or r["elapsed_s"])
        overall = statistics.fmean(r["latency_s"] or r["elapsed_s"] for r in records)
        retry_rate = sum((r["attempts"] or 1) - 1 for r in records) / len(records)
        seconds = sum(n * statistics.fmean(by_type.get(t) or [overall]) for t, n in full.items())
        seconds += sum(full.values()) * retry_rate * (timeout + BACKOFF_S)
        answer_h[key] = seconds / workers * OVERHEAD / 3600

        manifest = json.loads((folder / "manifest.json").read_text())
        summary = manifest["summary"]
        cost = summary.get("estimated_cost_usd")
        pilot = Counter(r["prediction"]["question_type"] for r in records)
        score_manifest = folder / "score_manifest.json"
        if score_manifest.exists():
            wall = json.loads(score_manifest.read_text())["wall_clock_s"]
            per_round = max(1.0, (wall - MODEL_LOAD_S) / rounds(pilot, 1))
            score_h[key] = (MODEL_LOAD_S + rounds(full, args.shards) * per_round) / 3600
        systems[key] = {
            "index_build": index_note[key], "workers": workers, "note": note,
            "pilot_answered": len(records), "mean_latency_s": round(overall, 2),
            "mean_latency_s_by_type": {t: round(statistics.fmean(v), 2) for t, v in by_type.items()},
            "retries_per_question": round(retry_rate, 2), "timeout_s": timeout,
            "est_full_answer_h": round(answer_h[key], 2),
            "est_full_cost_usd": round(cost / len(records) * sum(full.values()), 2) if cost is not None else None,
            "pilot_score_wall_s": wall if score_manifest.exists() else None,
            "est_full_score_h": round(score_h[key], 2) if key in score_h else None,
        }

    def path_hours(keys):
        """Systems on one path answer one after another; each is scored as soon as it finishes."""
        clock, end = 0.0, 0.0
        for key in keys:
            clock += answer_h.get(key, 0)
            end = max(end, clock + score_h.get(key, 0))
        return end

    paths = {name: max(path_hours(lane) for lane in lanes) for name, lanes in matrix["parallel_paths"].items()}
    slowest = max(paths, key=paths.get)
    missing = [k for k in plan if k not in systems]
    total = (f"All paths run at the same time. Slowest path: {slowest}, about {paths[slowest]:.1f} h "
             f"(answering plus scoring with {args.shards} shards per system). "
             + (f"Not in the pilot yet: {', '.join(missing)}. " if missing else "")
             + "The estimate does not include OpenAI rate-limit waits for the judge.")
    out = {
        "generated": bc.now(), "full_counts": dict(full), "overhead_factor": OVERHEAD, "score_shards": args.shards,
        "method": (f"From the 10-question pilot. Answering: per question type, full count x mean latency of the "
                   f"successful call, plus pilot retries per question x (planned timeout + {BACKOFF_S:.0f} s), / "
                   f"workers x {OVERHEAD}. Scoring: pilot time per judge round x rounds for 2,062 answers in "
                   f"{args.shards} parallel shards. Costs scale the pilot cost to 2,062 questions."),
        "systems": systems, "paths_h": {k: round(v, 2) for k, v in paths.items()}, "total": total,
    }
    (root / "timing.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

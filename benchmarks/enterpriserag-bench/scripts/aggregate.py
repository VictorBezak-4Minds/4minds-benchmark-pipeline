#!/usr/bin/env python3
"""Aggregate the scored EnterpriseRAG-Bench systems of one run: leaderboard bundle and summary.

    ./bench enterpriserag-bench aggregate erag aggregate.py --matrix configs/comparisons/gptoss_pilot.json \\
        --run runs/2026-10-10_gptoss-pilot [--label PILOT]

For each system of the comparison file with score_manifest.json in runs/<run>/<folder>/all:
1. The leaderboard bundle, runs/<run>/leaderboard/raw_data/: the files that the leaderboard Space
   reads (answers_<key>.jsonl, results_<key>.json, questions_updated_<key>.jsonl, systems.yaml
   and the official questions.jsonl). The folder holds only copies and is made again each time.
2. The Space's own transform_raw_data.py (leaderboard_upstream/, pinned), unchanged; only its three
   path constants point to the bundle -> runs/<run>/leaderboard/final_display_data/leaderboard.csv
   and data_viewer.jsonl. leaderboard.csv is copied to summary/. The script stops if a
   leaderboard overall score is not the official combined_correctness_completeness_score.
3. summary/scores.json and summary/report.md: the official metrics, the metrics by question
   type, a bootstrap 95% CI of the per-question overall score, the overall score with a missing
   answer counted as 0, the corrected questions, document counts, the judge cost and the run
   operations. It stops if a system was scored by another judge than the comparison's judge.
"""
import argparse
import contextlib
import csv
import importlib.util
import json
import random
import shutil
import statistics
from pathlib import Path

import yaml

import bench_common as bc
import run_readme

METRICS = [("overall_score", "Overall"), ("average_correctness_pct", "Correctness"),
           ("average_completeness_pct", "Completeness"), ("average_recall_pct", "Recall"),
           ("average_invalid_extra_docs", "Invalid extra docs")]


def bootstrap(values, resamples, seed):
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(resamples))
    return means[int(0.025 * resamples)], means[int(0.975 * resamples) - 1]


def system_summary(spec, system_dir, comparison):
    score = json.loads((system_dir / "score_manifest.json").read_text())
    if score["judge_models"] != comparison["judge"]:
        raise SystemExit(f"{system_dir} was scored by {score['judge_models']}, not {comparison['judge']}.")
    results = json.loads((system_dir / "results.json").read_text())
    manifest = json.loads((system_dir / "manifest.json").read_text())
    predictions = json.loads((system_dir / "predictions.json").read_text())
    rows = results["questions"]
    overall = [r["completeness_pct"] if r["answer_correct"] else 0.0 for r in rows]
    boot = comparison["bootstrap"]
    low, high = bootstrap(overall, boot["resamples"], boot["seed"])
    stats = results["aggregate_stats"]
    summary = manifest["summary"]
    docs = [len(p.get("document_ids") or []) for p in predictions]
    return {
        "key": spec["key"], "folder": str(system_dir.resolve()), "run_started": manifest.get("started"),
        "official": {**stats, "overall_score": stats["combined_correctness_completeness_score"]},
        "overall_ci95": [round(low, 2), round(high, 2)],
        "overall_missing_as_zero": round(sum(overall) / summary["questions"], 2),
        "scored_questions": len(rows), "run_questions": summary["questions"],
        "not_scored": summary["failed_keys"] + score["missing_scores"],
        "by_type": results["question_type_stats"],
        "corrected": sorted(r["question_id"] for r in rows if r.get("corrected")),
        "failed_judge_questions": score.get("failed_questions") or {},
        "documents_per_answer": {"mean": round(statistics.fmean(docs), 2) if docs else 0, "max": max(docs, default=0),
                                 "answers_without_documents": sum(d == 0 for d in docs)},
        "judge": {"models": score["judge_models"], "cost_usd": score["judge_cost_usd"], "usage": score["judge_usage"]},
        "operations": {"questions": summary["questions"], "answered": summary["answered"], "failed": summary["failed"],
                       "no_context": summary["no_context"], "dont_know": summary["dont_know"],
                       "workers": manifest.get("workers"), "latency": summary["latency"],
                       "estimated_cost_usd": summary.get("estimated_cost_usd"), "tokens": summary["tokens"]},
    }


def write_bundle(run_dir, comparison, scored):
    raw = run_dir / "leaderboard" / "raw_data"
    if raw.parent.exists():
        shutil.rmtree(raw.parent)
    raw.mkdir(parents=True)
    shutil.copy2(bc.profile.OFFICIAL_QUESTIONS, raw / "questions.jsonl")
    systems = {}
    for spec in comparison["systems"]:
        if spec["key"] not in scored:
            continue
        system_dir = Path(scored[spec["key"]]["folder"])
        shutil.copy2(system_dir / "answers.jsonl", raw / f"answers_{spec['key']}.jsonl")
        shutil.copy2(system_dir / "results.json", raw / f"results_{spec['key']}.json")
        shutil.copy2(system_dir / "questions_updated.jsonl", raw / f"questions_updated_{spec['key']}.jsonl")
        systems[spec["key"]] = {"display_name": spec["leaderboard_name"], "tags": spec.get("tags", [])}
    (raw / "systems.yaml").write_text(yaml.safe_dump(systems, sort_keys=False, allow_unicode=True))
    return raw


def run_transform(raw):
    script = bc.BENCH_DIR / "leaderboard_upstream" / "transform_raw_data.py"
    spec = importlib.util.spec_from_file_location("erb_transform_raw_data", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RAW_DIR, module.OUT_DIR, module.SYSTEMS_YAML = raw, raw.parent / "final_display_data", raw / "systems.yaml"
    log = raw.parent / "transform_raw_data.log"
    with log.open("w") as f, contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
        module.main()
    warnings = sum("WARNING" in line for line in log.read_text().splitlines())
    print(f"transform_raw_data.py: {warnings} warnings (questions outside the pilot have no result), log {log}")
    with (module.OUT_DIR / "leaderboard.csv").open() as f:
        return list(csv.DictReader(f)), module.OUT_DIR / "leaderboard.csv", bc.sha256(script)


def fmt(x, digits=1):
    return "n/a" if x is None else f"{x:.{digits}f}"


def report(label, comparison, systems, leaderboard, not_scored):
    lines = [f"# EnterpriseRAG-Bench {label}: metrics-based evaluation", "",
             f"Official `metrics_based_eval.py`, default settings (citation stripping, document correction), judge "
             f"{comparison['judge']['judge']}. Overall = mean of completeness when the answer is correct, else 0 "
             f"(the leaderboard column). 95% CI: {comparison['bootstrap']['resamples']} bootstrap resamples, "
             f"seed {comparison['bootstrap']['seed']}.", "",
             "| System | Overall (95% CI) | Overall, missing = 0 | Correctness | Completeness | Recall | "
             "Invalid extra docs | Corrected | Scored | Judge cost |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, s in sorted(systems.items(), key=lambda kv: -kv[1]["official"]["overall_score"]):
        o = s["official"]
        lines.append(f"| {name} | {fmt(o['overall_score'], 2)} ({fmt(s['overall_ci95'][0])}–{fmt(s['overall_ci95'][1])}) | "
                     f"{fmt(s['overall_missing_as_zero'], 2)} | {fmt(o['average_correctness_pct'])} | "
                     f"{fmt(o['average_completeness_pct'])} | {fmt(o['average_recall_pct'])} | "
                     f"{fmt(o['average_invalid_extra_docs'], 2)} | {len(s['corrected'])} | "
                     f"{s['scored_questions']}/{s['run_questions']} | ${s['judge']['cost_usd']:.2f} |")
    lines += ["", "## Leaderboard rows (transform_raw_data.py)", "",
              "| model | overall_score | correctness | completeness | recall | invalid_extra_docs | tags |",
              "|---|---|---|---|---|---|---|"]
    lines += [f"| {r['model']} | {r['overall_score']} | {r['correctness']} | {r['completeness']} | {r['recall']} | "
              f"{r['invalid_extra_docs']} | {r['tags']} |" for r in leaderboard]
    types = sorted({t for s in systems.values() for t in s["by_type"]})
    lines += ["", "## Overall by question type", "", "| System | " + " | ".join(types) + " |",
              "|---|" + "---|" * len(types)]
    for name, s in systems.items():
        cells = [f"{fmt(s['by_type'][t]['combined_correctness_completeness_score'])} (n={s['by_type'][t]['count']})"
                 if t in s["by_type"] else "–" for t in types]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += ["", "## Operations", "", "| System | Answered | Failed | No context | Docs per answer | "
              "Median latency | Answer cost |", "|---|---|---|---|---|---|---|"]
    for name, s in systems.items():
        o = s["operations"]
        cost = o.get("estimated_cost_usd")
        lines.append(f"| {name} | {o['answered']}/{o['questions']} | {o['failed']} | {o['no_context']} | "
                     f"{s['documents_per_answer']['mean']} | {(o['latency'] or {}).get('median_s')} s | "
                     f"{'n/a' if cost is None else f'${cost:.3f}'} |")
    missing = {n: s["not_scored"] for n, s in systems.items() if s["not_scored"]}
    if missing or not_scored:
        lines += ["", "## Not scored", ""]
        lines += [f"- {n}: questions {', '.join(q)} (not in the official averages)" for n, q in missing.items()]
        lines += [f"- {n}: {reason}" for n, reason in not_scored.items()]
    caveats = comparison["caveats"] + [c for spec in comparison["systems"] for c in spec.get("caveats", [])]
    lines += ["", "## Caveats", ""] + [f"- {c}" for c in caveats] + [""]
    return "\n".join(lines), caveats


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--matrix", required=True, help="comparison file in configs/comparisons/")
    parser.add_argument("--run", required=True, help="run folder, for example runs/<YYYY-MM-DD>_<name>")
    parser.add_argument("--label", default="PILOT")
    args = parser.parse_args()
    run_dir = Path(args.run).resolve()
    matrix = Path(args.matrix).resolve()
    comparison = json.loads(matrix.read_text())
    blocked_file = run_dir / "blocked.json"
    blocked = json.loads(blocked_file.read_text()) if blocked_file.exists() else {}
    systems, scored, not_scored = {}, {}, {}
    for spec in comparison["systems"]:
        system_dir = run_dir / spec["folder"] / "all"
        if (system_dir / "score_manifest.json").exists():
            s = system_summary(spec, system_dir, comparison)
            systems[spec["name"]], scored[spec["key"]] = s, s
        else:
            not_scored[spec["name"]] = blocked.get(spec["key"], "no score_manifest.json")
            print(f"  not scored: {system_dir}")

    raw = write_bundle(run_dir, comparison, scored)
    leaderboard, csv_path, transform_sha = run_transform(raw)
    by_display = {spec["leaderboard_name"]: spec["key"] for spec in comparison["systems"]}
    for row in leaderboard:
        expected = scored[by_display[row["model"]]]["official"]["overall_score"]
        if abs(float(row["overall_score"]) - expected) > 0.01:
            raise SystemExit(f"Leaderboard overall {row['overall_score']} for {row['model']} is not the official {expected}.")

    out = run_dir / "summary"
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(csv_path, out / "leaderboard.csv")
    text, caveats = report(args.label, comparison, systems, leaderboard, not_scored)
    scores = {"created": bc.now(), "label": args.label, "benchmark": bc.BENCHMARK, "comparison": comparison["name"],
              "upstream_commit": bc.UPSTREAM_COMMIT, "leaderboard_commit": bc.profile.LEADERBOARD_COMMIT,
              "transform_raw_data_sha256": transform_sha, "judge": comparison["judge"],
              "bootstrap": comparison["bootstrap"], "systems": systems, "not_scored": not_scored,
              "leaderboard": leaderboard, "caveats": caveats,
              "inputs": {"questions_sha256": bc.sha256(bc.profile.OFFICIAL_QUESTIONS),
                         "pilot_questions_sha256": bc.sha256(bc.BENCH_DIR / "data" / "pilot_questions.json"),
                         "corpus_sha256": bc.sha256(bc.CORPUS_FILE)}}
    (out / "scores.json").write_text(json.dumps(scores, indent=2))
    (out / "report.md").write_text(text)
    (run_dir / "config.json").write_text(json.dumps({"source": str(matrix.relative_to(bc.BENCH_DIR)),
                                                     "sha256": bc.sha256(matrix), "config": comparison}, indent=2))
    run_readme.write(run_dir)
    bc.audit("aggregate", run=str(run_dir), systems=sorted(scored), not_scored=sorted(not_scored),
             overall={k: s["official"]["overall_score"] for k, s in scored.items()})
    print(text)


if __name__ == "__main__":
    main()

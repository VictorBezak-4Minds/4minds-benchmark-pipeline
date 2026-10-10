#!/usr/bin/env python3
"""Combine the generation_eval.py results of all systems into one summary.

  ./bench graphrag-bench aggregate_pilot eval aggregate.py --matrix configs/comparisons/gemini.json \\
      --run runs/2026-10-09_gemini-pilot --label PILOT
  ./bench graphrag-bench aggregate_gptoss eval aggregate.py --matrix configs/comparisons/gptoss.json --run runs/2026-10-10_gptoss-full

The matrix file (configs/comparisons/*.json) lists the systems of one comparison: result folder (key),
display name, description, color, the reference system for the paired comparison, the
timing plan (make_timing.py) and the caveats. A caveat is a text, {"common": id} for a
benchmark-wide caveat in COMMON_CAVEATS, or {"system": key} for the caveats of that system
(left out when the system has no results). Optional "sensitivity" checks give answer
correctness and the paired differences again without a set of questions, for all systems;
each check has a name, a description and an "exclude" rule from SENSITIVITY_RULES.

Writes runs/<run>/summary/: scores.json, scores.csv, paired.csv and report.md; and runs/<run>/config.json
(a copy of the matrix file) and runs/<run>/README.md (pipeline/run_readme.py).
- Per system, question type and metric: mean, n and a 95% bootstrap confidence interval.
- Paired comparison of the reference system with each other system on the same
  questions: mean difference and a 95% paired-bootstrap confidence interval.
- Operating data from each run manifest: failures, "I don't know", tokens, cost, latency.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

import bench_common as bc
import run_readme
from retrievers import COMPLETE_FINISH_REASONS

TYPES = ["Fact Retrieval", "Complex Reasoning", "Contextual Summarize", "Creative Generation"]
METRICS = {  # official metric set per question type (generation_eval.py metric_config)
    "Fact Retrieval": ["rouge_score", "answer_correctness"],
    "Complex Reasoning": ["rouge_score", "answer_correctness"],
    "Contextual Summarize": ["answer_correctness", "coverage_score"],
    "Creative Generation": ["answer_correctness", "coverage_score", "faithfulness", "faithfulness_jsonfix"],
}
FAITHFULNESS = {"faithfulness", "faithfulness_jsonfix"}
METRIC_NAMES = {"rouge_score": "ROUGE-L", "answer_correctness": "Answer correctness",
                "coverage_score": "Coverage", "faithfulness": "Faithfulness (official)",
                "faithfulness_jsonfix": "Faithfulness (JSON-format fix)"}
RESAMPLES, SEED = 2000, 7

COMMON_CAVEATS = {  # benchmark-wide; matrix files refer to them as {"common": id}
    "generation_only": "Generation scoring only (generation_eval.py). Retrieval and graph metrics are not part "
                       "of this comparison.",
    "medical_only": "Medical subset only (one corpus, Medical.txt). The Novel subset was not run.",
    "gold_answers": "Gold answers come from the official repo at commit fdbab59. The local Questions/ copy (another "
                    "dataset release) has 251 different Contextual Summarize and Creative Generation answers.",
    "faithfulness_nan": "Faithfulness (official) is NaN for most answers: at commit fdbab59 the verdict prompt does "
                        "not ask for JSON, gpt-4o-mini answers in Markdown prose and the parser finds no verdicts "
                        "(audit/diagnostics/faithfulness_nan.json). 'Faithfulness (JSON-format fix)' runs the "
                        "official code and judge settings again with one added sentence that asks for the format of "
                        "the prompt's own examples (audit/patches/faithfulness-fdbab59-json-format.diff). It "
                        "is not part of the official protocol.",
    "training_data": "The medical source text can be in the training data of the models.",
    "single_run": "Each system ran one time. LLM answers and LLM-judge scores vary between runs; use the confidence "
                  "intervals.",
    "judge_repeat": "The judge is not fully repeatable at temperature 0 with a fixed seed: scoring the same 10 pilot "
                    "answers again changed answer correctness for 4 of 10 answers (the largest change was 0.60 to "
                    "0.97; ROUGE-L did not change). Single-question scores are not reliable; the averages over many "
                    "questions are (runs/2026-10-09_gemini-pilot/tests/judge-repeat).",
}
SENSITIVITY_RULES = {  # rule -> description; the rule's "systems" give the run logs to read
    "incomplete_retrieval": "answered questions whose retrieval returned no chunks and had no normal finish reason "
                            f"({', '.join(sorted(COMPLETE_FINISH_REASONS))})",
}


def load_matrix(path):
    """Read and check a matrix file. Exits with a clear message when it is not valid."""
    path = Path(path)
    if not path.is_absolute() and not path.exists():
        path = bc.BENCH_DIR / path
    if not path.exists() and path.suffix != ".json":
        path = bc.CONFIGS / "comparisons" / f"{path.name}.json"
    matrix = json.loads(path.read_text())
    keys = [s["key"] for s in matrix["systems"]]
    problems = [f"duplicate system key {k}" for k in set(keys) if keys.count(k) > 1]
    problems += [f"system {s.get('key')} has no {f}" for s in matrix["systems"]
                 for f in ("key", "name", "description", "color") if not s.get(f)]
    if matrix.get("reference") and matrix["reference"] not in keys:
        problems.append(f"reference {matrix['reference']} is not a system")
    problems += [f"parallel path {name} has unknown system {k}" for name, lanes in matrix.get("parallel_paths", {}).items()
                 for lane in lanes for k in lane if k not in keys]
    for item in matrix.get("caveats", []):
        if isinstance(item, dict) and "common" in item and item["common"] not in COMMON_CAVEATS:
            problems.append(f"unknown common caveat {item['common']}")
        if isinstance(item, dict) and "system" in item and item["system"] not in keys:
            problems.append(f"caveat refers to unknown system {item['system']}")
    for check in matrix.get("sensitivity", []):
        rule = check.get("exclude") or {}
        problems += [f"sensitivity check has no {f}" for f in ("name", "description") if not check.get(f)]
        if rule.get("rule") not in SENSITIVITY_RULES:
            problems.append(f"sensitivity check {check.get('name')} has unknown rule {rule.get('rule')}")
        problems += [f"sensitivity check {check.get('name')} has unknown system {k}"
                     for k in rule.get("systems", []) if k not in keys]
    if problems:
        sys.exit(f"{path}: " + "; ".join(problems))
    matrix["path"] = run_readme.bench_relative(path)
    return matrix


def caveats_for(matrix, present):
    out = []
    by_key = {s["key"]: s for s in matrix["systems"]}
    for item in matrix.get("caveats", []):
        if isinstance(item, str):
            out.append(item)
        elif "common" in item:
            out.append(COMMON_CAVEATS[item["common"]])
        elif item["system"] in present:
            out += by_key[item["system"]].get("caveats", [])
    return out


def bootstrap(values, rng):
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return None
    means = values[rng.integers(0, len(values), (RESAMPLES, len(values)))].mean(axis=1)
    return {"mean": float(values.mean()), "ci_low": float(np.percentile(means, 2.5)),
            "ci_high": float(np.percentile(means, 97.5)), "n": int(len(values))}


def load_scores(path):
    """Return {question_type: {id: {metric: score}}} from a --detailed_output file."""
    data = json.loads(path.read_text())
    out = {}
    for question_type, block in data.items():
        rows = {}
        for item in block.get("detailed") or []:
            rows[item["id"]] = {m: s for m, s in (item.get("metrics") or {}).items()
                                if isinstance(s, (int, float)) and not np.isnan(s)}
        out[question_type] = rows
    return out


def read_json(path):
    return json.loads(path.read_text()) if path.exists() else None


def excluded_questions(rule, root, subset):
    """Question ids that a sensitivity rule takes out, with the system that caused each one."""
    found = {}
    for key in rule["systems"]:
        log = root / key / subset / "runs.jsonl"
        if not log.exists():
            continue
        for record in bc.load_log(log).values():
            extra = record.get("extra") or {}
            if (record.get("status") == "ok" and extra.get("retrieval_chunks") == 0
                    and extra.get("retrieval_finish_reason") not in COMPLETE_FINISH_REASONS):
                found.setdefault(record["key"].split("::")[-1], []).append(key)
    return found


def sensitivity(checks, scores, reference, root, subset, rng):
    correctness = {key: {i: r["answer_correctness"] for rows in by_type.values() for i, r in rows.items()
                         if "answer_correctness" in r} for key, by_type in scores.items()}
    out = []
    for check in checks:
        excluded = excluded_questions(check["exclude"], root, subset)
        kept = {key: {i: v for i, v in values.items() if i not in excluded} for key, values in correctness.items()}
        paired = {}
        if reference in kept:
            for other in kept:
                if other != reference:
                    a, b = kept[reference], kept[other]
                    result = bootstrap([a[i] - b[i] for i in sorted(a.keys() & b.keys())], rng)
                    if result:
                        result["diff_mean"] = result.pop("mean")
                    paired[other] = result
        out.append({"name": check["name"], "description": check["description"], "rule": check["exclude"],
                    "rule_description": SENSITIVITY_RULES[check["exclude"]["rule"]],
                    "excluded": excluded, "n_excluded": len(excluded),
                    "overall": {key: bootstrap(list(values.values()), rng) for key, values in kept.items()},
                    "paired": paired})
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--matrix", required=True,
                        help="comparison config: a name in configs/comparisons/ (gptoss) or a file path")
    parser.add_argument("--run", "--results", dest="results", required=True, help="run folder, for example runs/<YYYY-MM-DD>_<name>")
    parser.add_argument("--subset", default="medical")
    parser.add_argument("--label", default="", help="for example PILOT")
    args = parser.parse_args()
    matrix = load_matrix(args.matrix)
    reference = matrix.get("reference")
    root = Path(args.results).resolve()
    rng = np.random.default_rng(SEED)

    systems, scores = [], {}
    for entry in matrix["systems"]:
        key, name, description = entry["key"], entry["name"], entry["description"]
        folder = root / key / args.subset
        score_file = folder / "generation_scores.json"
        if not score_file.exists():
            continue
        scores[key] = load_scores(score_file)
        creative = json.loads(score_file.read_text()).get("Creative Generation", {}).get("detailed") or []
        official_nan = sum(1 for item in creative
                           if isinstance((item.get("metrics") or {}).get("faithfulness"), float)
                           and np.isnan(item["metrics"]["faithfulness"]))
        fix = read_json(folder / "faithfulness_json_fix.json")
        if fix:
            rows = scores[key].setdefault("Creative Generation", {})
            for qid, value in fix["scores"].items():
                if value is not None:
                    rows.setdefault(qid, {})["faithfulness_jsonfix"] = value
        manifest = read_json(folder / "manifest.json") or {}
        score_manifest = read_json(folder / "score_manifest.json") or {}
        summary = manifest.get("summary", {})
        no_context = (summary.get("no_context") or 0) == (summary.get("answered") or 0)
        systems.append({
            "faithfulness_available": not no_context,
            "faithfulness_official_nan": official_nan, "faithfulness_items": len(creative),
            "faithfulness_jsonfix_nan": fix["nan"] if fix else None,
            "key": key, "name": name, "description": description, "color": entry["color"], "folder": str(folder),
            "run_started": manifest.get("started"), "run_finished": manifest.get("finished"),
            "settings": manifest.get("settings"), "readiness": manifest.get("readiness"),
            "deviations": manifest.get("deviations", []),
            "operations": {
                "questions": summary.get("questions"), "answered": summary.get("answered"),
                "failed": summary.get("failed"), "not_run": summary.get("not_run"),
                "dont_know": summary.get("dont_know"), "no_context": summary.get("no_context"),
                "tokens": summary.get("tokens"), "estimated_cost_usd": summary.get("estimated_cost_usd"),
                "latency": summary.get("latency"), "workers": manifest.get("workers"),
                "wall_clock_s_last_invocation": manifest.get("wall_clock_s_this_invocation"),
            },
            "scoring": {k: score_manifest.get(k) for k in ("judge", "judge_snapshot", "embedding_model",
                                                            "benchmark_commit", "wall_clock_s", "scored_per_type",
                                                            "failed_samples", "finished")},
        })

    metrics, overall = {}, {}
    for system in systems:
        key = system["key"]
        metrics[key] = {}
        all_correctness = []
        for question_type in TYPES:
            rows = scores[key].get(question_type, {})
            metrics[key][question_type] = {}
            for metric in METRICS[question_type]:
                if metric in FAITHFULNESS and not system["faithfulness_available"]:
                    metrics[key][question_type][metric] = None
                    continue
                values = [r[metric] for r in rows.values() if metric in r]
                metrics[key][question_type][metric] = bootstrap(values, rng)
            all_correctness += [r["answer_correctness"] for r in rows.values() if "answer_correctness" in r]
        overall[key] = {"answer_correctness": bootstrap(all_correctness, rng)}

    available = {s["key"]: s["faithfulness_available"] for s in systems}
    paired = {}
    if reference in scores:
        for system in systems:
            other = system["key"]
            if other == reference:
                continue
            paired[other] = {}
            for question_type in TYPES + ["All questions"]:
                types = TYPES if question_type == "All questions" else [question_type]
                metric_list = ["answer_correctness"] if question_type == "All questions" else METRICS[question_type]
                paired[other][question_type] = {}
                for metric in metric_list:
                    if metric in FAITHFULNESS and not (available[reference] and available[other]):
                        continue
                    diffs = []
                    for qt in types:
                        a, b = scores[reference].get(qt, {}), scores[other].get(qt, {})
                        diffs += [a[i][metric] - b[i][metric] for i in sorted(a.keys() & b.keys())
                                  if metric in a[i] and metric in b[i]]
                    result = bootstrap(diffs, rng)
                    if result:
                        result["diff_mean"] = result.pop("mean")
                    paired[other][question_type][metric] = result

    commits = {s["scoring"].get("benchmark_commit") for s in systems if s["scoring"].get("benchmark_commit")}
    snapshots = {s["scoring"].get("judge_snapshot") for s in systems if s["scoring"].get("judge_snapshot")}
    out = {
        "generated": bc.now(), "label": args.label, "subset": args.subset, "results_root": str(root),
        "benchmark": {"repo": "https://github.com/GraphRAG-Bench/GraphRAG-Benchmark", "commit": sorted(commits),
                      "judge": "gpt-4o-mini", "judge_snapshot": sorted(snapshots),
                      "embedding_model": "BAAI/bge-large-en-v1.5", "bootstrap_resamples": RESAMPLES},
        "matrix": {"name": matrix.get("name"), "file": matrix["path"], "sha256": bc.sha256(bc.BENCH_DIR / matrix["path"])},
        "reference_system": reference, "types": TYPES, "metric_set": METRICS, "metric_names": METRIC_NAMES,
        "systems": systems, "metrics": metrics, "overall": overall, "paired": paired,
        "caveats": caveats_for(matrix, set(scores)),
    }
    if matrix.get("sensitivity"):
        out["sensitivity"] = sensitivity(matrix["sensitivity"], scores, reference, root, args.subset, rng)
    summary_dir = root / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "scores.json").write_text(json.dumps(out, indent=2))

    with (summary_dir / "scores.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["system", "question_type", "metric", "mean", "ci_low", "ci_high", "n"])
        for system in systems:
            for question_type in TYPES:
                for metric, r in metrics[system["key"]][question_type].items():
                    if r:
                        writer.writerow([system["name"], question_type, metric, *(round(r[k], 4) for k in
                                         ("mean", "ci_low", "ci_high")), r["n"]])
            r = overall[system["key"]]["answer_correctness"]
            if r:
                writer.writerow([system["name"], "All questions", "answer_correctness",
                                 *(round(r[k], 4) for k in ("mean", "ci_low", "ci_high")), r["n"]])
    with (summary_dir / "paired.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["reference", "other", "question_type", "metric", "diff_mean", "ci_low", "ci_high", "n"])
        for other, by_type in paired.items():
            for question_type, by_metric in by_type.items():
                for metric, r in by_metric.items():
                    if r:
                        writer.writerow([reference, other, question_type, metric,
                                         *(round(r[k], 4) for k in ("diff_mean", "ci_low", "ci_high")), r["n"]])
    (summary_dir / "report.md").write_text(markdown(out))
    run_readme.copy_config(root, matrix["path"])
    run_readme.write(root)
    bc.audit("aggregate", results=str(root), systems=[s["key"] for s in systems], label=args.label,
             matrix=matrix["path"])
    print(f"wrote {summary_dir}/scores.json, scores.csv, paired.csv, report.md for {[s['key'] for s in systems]}")


def fmt(r, pct=True):
    if not r:
        return "n/a"
    scale = 100 if pct else 1
    return f"{r['mean'] * scale:.1f} [{r['ci_low'] * scale:.1f}, {r['ci_high'] * scale:.1f}]"


def markdown(out):
    names = {s["key"]: s["name"] for s in out["systems"]}
    title = "GraphRAG-Bench Medical: generation results" + (f" ({out['label']})" if out["label"] else "")
    lines = [f"# {title}", "", f"Generated {out['generated']}. Scores are 0-100 with 95% bootstrap confidence intervals.",
             "", f"Judge `{out['benchmark']['judge']}` ({', '.join(out['benchmark']['judge_snapshot'])}), "
             f"embeddings `{out['benchmark']['embedding_model']}`, GraphRAG-Bench commit "
             f"`{', '.join(c[:7] for c in out['benchmark']['commit'])}`.", "", "## Answer correctness, all questions", "",
             "| System | Answer correctness | n |", "|---|---|---|"]
    for s in out["systems"]:
        r = out["overall"][s["key"]]["answer_correctness"]
        lines.append(f"| {s['name']} | {fmt(r)} | {r['n'] if r else 0} |")
    for question_type in out["types"]:
        metric_list = out["metric_set"][question_type]
        lines += ["", f"## {question_type}", "", "| System | " + " | ".join(out["metric_names"][m] for m in metric_list) + " |",
                  "|---|" + "---|" * len(metric_list)]
        for s in out["systems"]:
            cells = []
            for m in metric_list:
                r = out["metrics"][s["key"]][question_type].get(m)
                cells.append("not available (no context)" if m in FAITHFULNESS and not s["faithfulness_available"]
                             else f"{fmt(r)} (n={r['n']})" if r else "n/a")
            lines.append(f"| {s['name']} | " + " | ".join(cells) + " |")
        if question_type == "Creative Generation":
            lines += ["", "Answers with NaN faithfulness (official / JSON-format fix): " + "; ".join(
                f"{s['name']} {s['faithfulness_official_nan']}/{s['faithfulness_items']} / "
                f"{s['faithfulness_jsonfix_nan'] if s['faithfulness_jsonfix_nan'] is not None else 'not run'}"
                for s in out["systems"] if s["faithfulness_available"]) + "."]
    if out["paired"]:
        lines += ["", f"## Paired differences: {names.get(out['reference_system'])} minus each system",
                  "", "Positive values favor 4Minds. Same questions only.", "",
                  "| Compared with | Question type | Metric | Difference | n |", "|---|---|---|---|---|"]
        for other, by_type in out["paired"].items():
            for question_type, by_metric in by_type.items():
                for metric, r in by_metric.items():
                    if r:
                        d = {"mean": r["diff_mean"], "ci_low": r["ci_low"], "ci_high": r["ci_high"]}
                        lines.append(f"| {names[other]} | {question_type} | {out['metric_names'][metric]} | "
                                     f"{fmt(d)} | {r['n']} |")
    for check in out.get("sensitivity", []):
        lines += ["", f"## Sensitivity check: {check['name']}", "", check["description"], "",
                  f"Excluded for all systems: {check['n_excluded']} {check['rule_description']}.", "",
                  "| System | Answer correctness, all questions | n | Paired difference | n |", "|---|---|---|---|---|"]
        for s in out["systems"]:
            r, p = check["overall"].get(s["key"]), check["paired"].get(s["key"])
            d = p and {"mean": p["diff_mean"], "ci_low": p["ci_low"], "ci_high": p["ci_high"]}
            lines.append(f"| {s['name']} | {fmt(r)} | {r['n'] if r else 'n/a'} | "
                         f"{fmt(d) if d else '(reference)' if s['key'] == out['reference_system'] else 'n/a'} | "
                         f"{p['n'] if p else ''} |")
    lines += ["", "## Operating data", "", "Not scored: answers that the judge could not score (not in the means).", "",
              "| System | Answered | Failed | Not scored | \"I don't know\" | Median latency (s) | "
              "Est. cost (USD) |", "|---|---|---|---|---|---|---|"]
    for s in out["systems"]:
        o = s["operations"]
        lines.append(f"| {s['name']} | {o['answered']}/{o['questions']} | {o['failed']} | "
                     f"{s['scoring'].get('failed_samples', 'n/a')} | {o['dont_know']} | "
                     f"{(o.get('latency') or {}).get('median_s', 'n/a')} | "
                     f"{o['estimated_cost_usd'] if o['estimated_cost_usd'] is not None else 'n/a'} |")
    lines += ["", "## Systems", ""] + [f"- **{s['name']}**: {s['description']}. Run {s['run_started']} to "
                                       f"{s['run_finished']}." for s in out["systems"]]
    lines += ["", "## Notes and caveats", ""] + [f"- {c}" for c in out["caveats"]] + [""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()

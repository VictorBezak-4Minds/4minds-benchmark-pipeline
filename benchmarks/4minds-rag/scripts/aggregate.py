#!/usr/bin/env python3
"""Aggregate the 4Minds RAG scores of one run: summary/scores.json and summary/report.md.

    ./bench 4minds-rag aggregate_v1 eval aggregate.py --matrix configs/comparisons/erag_pilot.json \\
        --scorer configs/scorers/v1_gpt-4o-mini.json --run runs/2026-10-11_erag-pilot_judge-gpt-4o-mini

For each system of the comparison file with <scorer name>.json in runs/<run>/<folder>/all (written
by pipeline/score_extra.py): the mean of each metric output with a bootstrap 95% CI over the
questions (the comparison's resamples and seed), the means per question type, the items that the
judge did not score, the questions without an answer, and the judge use and cost. It stops if a
system was scored with another version of the scorer config.
"""
import argparse
import json
import random
import statistics
from pathlib import Path

import bench_common as bc
import run_readme


def bootstrap(values, resamples, seed):
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(resamples))
    return means[int(0.025 * resamples)], means[int(0.975 * resamples) - 1]


def metric_outputs(scorer):
    """(name, label, metric) for each output, in config order; the names that score_extra.py writes."""
    out = []
    for m in scorer["metrics"]:
        for output in m.get("outputs", ["score"]):
            name = m["key"] if output == "score" else f"{m['key']}_{output}"
            label = m["label"] if output == "score" else f"{m['label']}: {output}"
            out.append((name, label, m))
    return out


def stats(values, boot):
    if not values:
        return {"mean": None, "ci_low": None, "ci_high": None, "n": 0}
    low, high = bootstrap(values, boot["resamples"], boot["seed"])
    return {"mean": round(statistics.fmean(values), 4), "ci_low": round(low, 4), "ci_high": round(high, 4), "n": len(values)}


def judge_usage(invocations):
    total = {}
    for record in invocations:
        for key, value in (record.get("judge_usage") or record.get("judge_tokens_ragas") or {}).items():
            total[key] = total.get(key, 0) + value
    return total


def system_summary(spec, path, scorer, outputs, boot, question_ids):
    data = json.loads(path.read_text())
    if data["config"]["sha256"] != scorer["sha256"]:
        raise SystemExit(f"{path} was scored with config sha256 {data['config']['sha256'][:12]}, "
                         f"not {scorer['sha256'][:12]} ({scorer['path']}).")
    types = data["question_types"]
    metrics, by_type = {}, {}
    for name, _, _ in outputs:
        values = {q: v for q, v in data["scores"].get(name, {}).items() if v is not None}
        metrics[name] = stats(list(values.values()), boot)
        for qid, v in values.items():
            by_type.setdefault(types[qid], {}).setdefault(name, []).append(v)
    return {
        "key": spec["key"], "folder": str(path.parent.resolve()), "answers": data["answers"],
        "missing_answers": sorted(set(question_ids) - set(types)),
        "items": data["items"], "not_scored": data["not_scored"], "not_scored_items": data["not_scored_items"],
        "metrics": metrics,
        "by_type": {t: {n: {"mean": round(statistics.fmean(v), 4), "n": len(v)} for n, v in per.items()}
                    for t, per in sorted(by_type.items())},
        "judge": {"cost_usd": data["cost_usd"], "invocations": len(data["invocations"]),
                  "usage": judge_usage(data["invocations"])},
        "versions": data["versions"], "predictions_sha256": data["predictions_sha256"], "finished": data["finished"],
    }


def fmt(x, digits=3):
    return "n/a" if x is None else f"{x:.{digits}f}"


def report(label, comparison, scorer, outputs, systems, not_scored, caveats):
    judge = scorer["judge"].get("backend") or scorer["judge"].get("model")
    headline = comparison["headline_metrics"]
    labels = {name: label_ for name, label_, _ in outputs}
    lines = [f"# 4Minds RAG {label}: {scorer['name']}", "", f"{scorer['description']}", "",
             f"Judge: `{judge}`. Scores are 0 to 1, higher is better. 95% CI: {comparison['bootstrap']['resamples']} "
             f"bootstrap resamples over the questions, seed {comparison['bootstrap']['seed']}.", "",
             "## Headline metrics", "", "| System | " + " | ".join(labels[n] for n in headline) + " |",
             "|---|" + "---|" * len(headline)]
    for name, s in systems.items():
        cells = [f"{fmt(s['metrics'][n]['mean'])} ({fmt(s['metrics'][n]['ci_low'], 2)}–{fmt(s['metrics'][n]['ci_high'], 2)})"
                 for n in headline]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += ["", "## All metric outputs", "", "| Metric | " + " | ".join(systems) + " |", "|---|" + "---|" * len(systems)]
    for n, label_, _ in outputs:
        lines.append(f"| {label_} | " + " | ".join(f"{fmt(s['metrics'][n]['mean'])} (n={s['metrics'][n]['n']})"
                                                for s in systems.values()) + " |")
    for n in headline:
        types = sorted({t for s in systems.values() for t in s["by_type"]})
        lines += ["", f"## {labels[n]} by question type", "", "| System | " + " | ".join(types) + " |",
                  "|---|" + "---|" * len(types)]
        for name, s in systems.items():
            cells = [f"{fmt(s['by_type'][t][n]['mean'], 2)} (n={s['by_type'][t][n]['n']})"
                     if n in s["by_type"].get(t, {}) else "–" for t in types]
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += ["", "## Scoring", "", "| System | Answers | Items | Not scored | Judge calls | Not JSON | Fences removed | "
              "Truncated | Judge cost |", "|---|---|---|---|---|---|---|---|---|"]
    for name, s in systems.items():
        u = s["judge"]["usage"]
        lines.append(f"| {name} | {s['answers']} | {s['items']} | {s['not_scored']} | {u.get('calls', 'n/a')} | "
                     f"{u.get('not_json_replies', 'n/a')} | {u.get('fences_removed', 'n/a')} | "
                     f"{u.get('truncated_replies', 'n/a')} | ${s['judge']['cost_usd']:.3f} |")
    missing = {n: s["missing_answers"] for n, s in systems.items() if s["missing_answers"]}
    unscored = {n: s["not_scored_items"] for n, s in systems.items() if s["not_scored_items"]}
    if missing or unscored or not_scored:
        lines += ["", "## Not scored", ""]
        lines += [f"- {n}: no answer for {', '.join(q)} (no row, not in the means)" for n, q in missing.items()]
        lines += [f"- {n}: the judge did not score {len(i)} items: "
                  + ", ".join(f"{x['id']} {x['metric']}" for x in i) for n, i in unscored.items()]
        lines += [f"- {n}: {reason}" for n, reason in not_scored.items()]
    lines += ["", "## Caveats", ""] + [f"- {c}" for c in caveats] + [""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--matrix", required=True, help="comparison file in configs/comparisons/")
    parser.add_argument("--scorer", required=True, help="scorer config in configs/scorers/ (the one that scored the run)")
    parser.add_argument("--run", required=True, help="run folder, for example runs/<YYYY-MM-DD>_<name>")
    parser.add_argument("--label", default="PILOT")
    args = parser.parse_args()
    run_dir, matrix, scorer_file = Path(args.run).resolve(), Path(args.matrix).resolve(), Path(args.scorer).resolve()
    comparison = json.loads(matrix.read_text())
    scorer = {**json.loads(scorer_file.read_text()), "path": str(scorer_file), "sha256": bc.sha256(scorer_file)}
    outputs = metric_outputs(scorer)
    question_file = bc.profile.QUESTION_FILES["all"]
    question_ids = [q["question_id"] for q in json.loads(Path(question_file).read_text())]

    systems, not_scored = {}, {}
    for spec in comparison["systems"]:
        path = run_dir / spec["folder"] / "all" / f"{scorer['name']}.json"
        if path.exists():
            systems[spec["name"]] = system_summary(spec, path, scorer, outputs, comparison["bootstrap"], question_ids)
        else:
            not_scored[spec["name"]] = f"no {path.relative_to(run_dir)}"
            print(f"  not scored: {path}")
    systems = dict(sorted(systems.items(), key=lambda kv: -(kv[1]["metrics"][comparison["headline_metrics"][0]]["mean"] or 0)))

    judge = scorer["judge"].get("backend") or scorer["judge"].get("model")
    caveats = (comparison["caveats"] + comparison.get("judge_caveats", {}).get(judge, [])
               + [c for spec in comparison["systems"] for c in spec.get("caveats", [])])
    text = report(args.label, comparison, scorer, outputs, systems, not_scored, caveats)
    info = json.loads((run_dir / "run.json").read_text()) if (run_dir / "run.json").exists() else {}
    out = run_dir / "summary"
    out.mkdir(parents=True, exist_ok=True)
    scores = {"created": bc.now(), "label": args.label, "benchmark": bc.BENCHMARK, "comparison": comparison["name"],
              "scorer": {k: scorer[k] for k in ("name", "description", "path", "sha256", "judge")},
              "metrics": [{"name": n, "label": label, "key": m["key"],
                           "note": comparison.get("metric_notes", {}).get(m["key"], m.get("note", ""))}
                          for n, label, m in outputs],
              "headline_metrics": comparison["headline_metrics"], "bootstrap": comparison["bootstrap"],
              "derived_from": info.get("derived_from"), "source_upstream_commit": bc.profile.SOURCE_UPSTREAM_COMMIT,
              "systems": systems, "not_scored": not_scored, "caveats": caveats,
              "inputs": {"questions_sha256": bc.sha256(Path(question_file)), "corpus_sha256": bc.sha256(bc.CORPUS_FILE)}}
    (out / "scores.json").write_text(json.dumps(scores, indent=2))
    (out / "report.md").write_text(text)
    run_readme.copy_config(run_dir, matrix)
    record = json.loads((run_dir / "config.json").read_text())
    record["scorer"] = {"source": str(scorer_file.relative_to(bc.BENCH_DIR)), "sha256": scorer["sha256"],
                        "config": json.loads(scorer_file.read_text())}
    (run_dir / "config.json").write_text(json.dumps(record, indent=2) + "\n")
    run_readme.write(run_dir)
    bc.audit("aggregate", run=str(run_dir), scorer=scorer["name"], systems=sorted(s["key"] for s in systems.values()),
             not_scored=sorted(not_scored),
             headline={s["key"]: {n: s["metrics"][n]["mean"] for n in comparison["headline_metrics"]} for s in systems.values()})
    print(text)


if __name__ == "__main__":
    main()

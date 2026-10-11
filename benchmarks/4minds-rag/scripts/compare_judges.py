#!/usr/bin/env python3
"""Compare two runs of the same answers that differ only in the judge: agreement per metric.

    ./bench 4minds-rag judge_agreement eval compare_judges.py \\
        --runs runs/2026-10-11_erag-pilot_judge-gpt-4o-mini runs/2026-10-11_erag-pilot_judge-haiku-nothink \\
        --out runs/2026-10-11_erag-pilot_judge-haiku-nothink/tests/judge_agreement_v1

Both runs must have summary/scores.json (aggregate.py) and the same answers (predictions sha256).
For each metric output: the mean under each judge, the per-item Pearson and Spearman correlation
over all (system, question) pairs that both judges scored, the share of items with the same value,
the mean absolute difference, and the Spearman correlation of the system means (the ranking).
Writes agreement.json and agreement.md in --out.
"""
import argparse
import json
import statistics
from pathlib import Path

import bench_common as bc


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def pearson(x, y):
    if len(x) < 3 or len(set(x)) < 2 or len(set(y)) < 2:
        return None
    return round(statistics.correlation(x, y), 3)


def load(run):
    run = Path(run).resolve()
    summary = json.loads((run / "summary" / "scores.json").read_text())
    name = summary["scorer"]["name"]
    items = {}
    for system, s in summary["systems"].items():
        data = json.loads((Path(s["folder"]) / f"{name}.json").read_text())
        items[system] = {"predictions_sha256": data["predictions_sha256"], "scores": data["scores"]}
    return run, summary, items


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", nargs=2, required=True, metavar=("RUN_A", "RUN_B"))
    parser.add_argument("--out", required=True, help="folder for agreement.json and agreement.md")
    args = parser.parse_args()
    (run_a, sum_a, items_a), (run_b, sum_b, items_b) = load(args.runs[0]), load(args.runs[1])
    judge = lambda s: s["scorer"]["judge"].get("backend") or s["scorer"]["judge"].get("model")
    systems = [s for s in sum_a["systems"] if s in sum_b["systems"]]
    for system in systems:
        if items_a[system]["predictions_sha256"] != items_b[system]["predictions_sha256"]:
            raise SystemExit(f"{system}: the two runs scored different answers.")
    names = [m["name"] for m in sum_a["metrics"] if m["name"] in {x["name"] for x in sum_b["metrics"]}]
    labels = {m["name"]: m["label"] for m in sum_a["metrics"]}

    metrics = {}
    for name in names:
        x, y = [], []
        for system in systems:
            a, b = items_a[system]["scores"].get(name, {}), items_b[system]["scores"].get(name, {})
            for qid in sorted(set(a) & set(b)):
                if a[qid] is not None and b[qid] is not None:
                    x.append(a[qid])
                    y.append(b[qid])
        means_a = [sum_a["systems"][s]["metrics"][name]["mean"] for s in systems]
        means_b = [sum_b["systems"][s]["metrics"][name]["mean"] for s in systems]
        metrics[name] = {
            "label": labels[name], "items": len(x),
            "mean_a": round(statistics.fmean(x), 4) if x else None, "mean_b": round(statistics.fmean(y), 4) if y else None,
            "pearson": pearson(x, y), "spearman": pearson(ranks(x), ranks(y)),
            "same_value_share": round(sum(abs(p - q) < 1e-9 for p, q in zip(x, y)) / len(x), 3) if x else None,
            "mean_abs_difference": round(statistics.fmean(abs(p - q) for p, q in zip(x, y)), 4) if x else None,
            "system_means": {s: [ma, mb] for s, ma, mb in zip(systems, means_a, means_b)},
            "system_rank_spearman": pearson(ranks(means_a), ranks(means_b)) if None not in means_a + means_b else None,
        }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    record = {"created": bc.now(), "run_a": str(run_a.relative_to(bc.BENCH_DIR)), "run_b": str(run_b.relative_to(bc.BENCH_DIR)),
              "judge_a": judge(sum_a), "judge_b": judge(sum_b), "scorer_a": sum_a["scorer"]["name"],
              "scorer_b": sum_b["scorer"]["name"], "systems": systems, "metrics": metrics}
    (out / "agreement.json").write_text(json.dumps(record, indent=2))
    f = lambda v, d=3: "n/a" if v is None else f"{v:.{d}f}"
    lines = [f"# Judge agreement: {record['judge_a']} (A) against {record['judge_b']} (B)", "",
             f"Runs: `{record['run_a']}` and `{record['run_b']}`; the same answers, only the judge is different. "
             "Item correlations are over all (system, question) pairs that both judges scored. "
             "System-rank Spearman uses the means of the systems.", "",
             "| Metric | Items | Mean A | Mean B | Pearson | Spearman | Same value | Mean abs. difference | System-rank Spearman |",
             "|---|---|---|---|---|---|---|---|---|"]
    for m in metrics.values():
        lines.append(f"| {m['label']} | {m['items']} | {f(m['mean_a'])} | {f(m['mean_b'])} | {f(m['pearson'])} | "
                     f"{f(m['spearman'])} | {f(m['same_value_share'])} | {f(m['mean_abs_difference'])} | "
                     f"{f(m['system_rank_spearman'])} |")
    lines += ["", "## System means (A / B)", "", "| Metric | " + " | ".join(systems) + " |", "|---|" + "---|" * len(systems)]
    for m in metrics.values():
        lines.append(f"| {m['label']} | " + " | ".join(f"{f(a)} / {f(b)}" for a, b in m["system_means"].values()) + " |")
    (out / "agreement.md").write_text("\n".join(lines) + "\n")
    bc.audit("judge_agreement", out=str(out), run_a=record["run_a"], run_b=record["run_b"],
             pearson={n: m["pearson"] for n, m in metrics.items()})
    print("\n".join(lines))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Aggregate the scored QASPER systems into summary/scores.json and summary/report.md.

    ./bench qasper aggregate_pilot eval aggregate.py --results results/pilot

For each system folder <results>/<system>/test with scores_official.json: the official
Answer F1 (overall and by answer type), a bootstrap 95% CI from per_question.jsonl, the
answer length, and run operations from manifest.json.
"""
import argparse
import json
import random
import statistics
from pathlib import Path

import bench_common as bc

NAMES = {
    "4minds_constellations": "4Minds (Constellations)",
    "4minds_symi": "4Minds (SYMI)",
    "gemini": "Gemini + File Search",
    "rag_engine": "Gemini + RAG Engine",
    "lightrag": "LightRAG + Gemini",
}
TYPES = ["extractive", "abstractive", "boolean", "none"]
RESAMPLES, SEED = 10000, 0
CAVEATS = [
    "Pilot: 25 questions. The confidence intervals are wide and overlap; do not rank systems from this table.",
    "Deviation from the paper's setting: all corpus papers are in one knowledge base, and each query names "
    "its paper (In the paper \"<title>\": <question>). The paper's model receives the question plus that one paper.",
    "The corpus is a slice: the 25 question papers plus 39 other test papers (64 of 416).",
    "Tables and figures are available only as captions (no images).",
    "The papers are from before 2021 and are probably in the training data of the models.",
    "Answer F1 is token overlap with the best-matching reference, so long answers get low scores even when "
    "they are correct. Compare the answer length column.",
    "By-type scores use the type of the best-matching reference (official rule); some questions have "
    "references of more than one type.",
    "Only Answer F1 is reported. Evidence F1 is not used (predicted_evidence is empty).",
]


def bootstrap(values):
    rng = random.Random(SEED)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(RESAMPLES))
    return means[int(0.025 * RESAMPLES)], means[int(0.975 * RESAMPLES) - 1]


def system_summary(key, system_dir):
    official = json.loads((system_dir / "scores_official.json").read_text())
    rows = [json.loads(line) for line in (system_dir / "per_question.jsonl").read_text().splitlines() if line]
    manifest = json.loads((system_dir / "manifest.json").read_text())
    f1 = [r["answer_f1"] for r in rows]
    low, high = bootstrap(f1)
    words = [r["answer_words"] for r in rows]
    summary = manifest["summary"]
    return {
        "key": key,
        "folder": str(system_dir.resolve()),
        "run_started": manifest.get("started"),
        "answer_f1": official["Answer F1"],
        "ci95": [low, high],
        "by_type": {t: {"answer_f1": official["Answer F1 by type"][t],
                        "n": sum(r["best_reference_type"] == t for r in rows)} for t in TYPES},
        "questions": len(rows),
        "missing_predictions": official["Missing predictions"],
        "answer_words_median": statistics.median(words),
        "answer_words_max": max(words),
        "answered_unanswerable": sum(r["answer"].strip().rstrip(".").lower() == "unanswerable" for r in rows),
        "operations": {"questions": summary["questions"], "answered": summary["answered"],
                       "failed": summary["failed"], "workers": manifest.get("workers"), "latency": summary["latency"],
                       "estimated_cost_usd": summary.get("estimated_cost_usd"), "tokens": summary["tokens"]},
    }


def pct(x):
    return f"{100 * x:.1f}"


def report(label, systems, not_scored):
    lines = [f"# QASPER {label}: Answer F1", "",
             f"Official evaluator `qasper_evaluator.py` (v0.3 test release), {RESAMPLES} bootstrap resamples, seed {SEED}.", "",
             "| System | Answer F1 (95% CI) | Extractive | Abstractive | Yes/No | Unanswerable | Median answer words | Median latency |",
             "|---|---|---|---|---|---|---|---|"]
    for name, s in sorted(systems.items(), key=lambda kv: -kv[1]["answer_f1"]):
        cells = [f"{pct(s['by_type'][t]['answer_f1'])} (n={s['by_type'][t]['n']})" for t in TYPES]
        latency = (s["operations"]["latency"] or {}).get("median_s")
        lines.append(f"| {name} | {pct(s['answer_f1'])} ({pct(s['ci95'][0])}–{pct(s['ci95'][1])}) | "
                     + " | ".join(cells) + f" | {s['answer_words_median']} | {latency} s |")
    if not_scored:
        lines += ["", "## Not scored", ""] + [f"- {name}: {reason}" for name, reason in not_scored.items()]
    lines += ["", "## Caveats", ""] + [f"- {c}" for c in CAVEATS] + [""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True)
    parser.add_argument("--label", default="PILOT")
    args = parser.parse_args()
    results = Path(args.results)
    blocked_file = results / "blocked.json"
    blocked = json.loads(blocked_file.read_text()) if blocked_file.exists() else {}
    systems, not_scored = {}, {}
    for key, name in NAMES.items():
        system_dir = results / key / "test"
        if (system_dir / "scores_official.json").exists():
            systems[name] = system_summary(key, system_dir)
        else:
            not_scored[name] = blocked.get(key, "no scores_official.json")
            print(f"  not scored: {system_dir}")
    out = results / "summary"
    out.mkdir(parents=True, exist_ok=True)
    scores = {"created": bc.now(), "label": args.label, "benchmark": bc.BENCHMARK,
              "gold_sha256": bc.sha256(bc.profile.GOLD_FILE), "systems": systems,
              "not_scored": not_scored, "caveats": CAVEATS}
    (out / "scores.json").write_text(json.dumps(scores, indent=2))
    (out / "report.md").write_text(report(args.label, systems, not_scored))
    bc.audit("aggregate", results=str(results), systems=sorted(systems), not_scored=sorted(not_scored))
    print((out / "report.md").read_text())


if __name__ == "__main__":
    main()

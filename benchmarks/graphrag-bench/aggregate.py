#!/usr/bin/env python3
"""Combine the generation_eval.py results of all systems into one summary.

  ./bench graphrag-bench aggregate_pilot eval aggregate.py --results results/pilot --label PILOT
  ./bench graphrag-bench aggregate eval aggregate.py --results results

Writes <results>/summary/: scores.json, scores.csv, paired.csv and report.md.
- Per system, question type and metric: mean, n and a 95% bootstrap confidence interval.
- Paired comparison of 4Minds (Constellations) with each other system on the same
  questions: mean difference and a 95% paired-bootstrap confidence interval.
- Operating data from each run manifest: failures, "I don't know", tokens, cost, latency.
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

import bench_common as bc

SYSTEMS = [  # (folder, display name, short description)
    ("4minds_constellations", "4Minds (Constellations)", "4Minds prod, Constellations RAG over the dataset graph, GPT-OSS-120B standard weights"),
    ("4minds_symi", "4Minds (SYMI)", "4Minds prod, SYMI agent engine over the same model and dataset"),
    ("gemini", "Gemini + File Search", "Gemini Developer API, gemini-3.8-flash with the File Search tool (top_k 5)"),
    ("rag_engine", "Gemini + RAG Engine", "Vertex AI, gemini-3.8-flash with the RAG Engine retrieval tool (top_k 5)"),
    ("lightrag", "LightRAG + Gemini", "LightRAG v1.2.5 (official GraphRAG-Bench runner settings), gemini-3.8-flash"),
]
REFERENCE = "4minds_constellations"
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

CAVEATS = [
    "Generation scoring only (generation_eval.py). Retrieval and graph metrics are not part of this comparison.",
    "Medical subset only (one corpus, Medical.txt). The Novel subset was not run.",
    "Gold answers come from the official repo at commit fdbab59. The local Questions/ copy (another dataset "
    "release) has 251 different Contextual Summarize and Creative Generation answers.",
    "4Minds has no per-request system prompt. The official prompt is in the model persona "
    "(behavioralGuidelines). The other systems get it as the system instruction of each request.",
    "4Minds answers with GPT-OSS-120B (standard weights, no Ghost Weights fine-tuning). The judge, gpt-4o-mini, "
    "is also an OpenAI model, so a same-family preference by the judge is possible.",
    "Gemini + File Search: `context` holds only the chunks that the answer cites. The other systems store all "
    "retrieved chunks. Only faithfulness reads `context`, and the judge reads the first 10,000 characters.",
    "LightRAG: the embedding model is BAAI/bge-large-en-v1.5 (the official code sets embedding_dim 1024), and "
    "context is stored as a one-item list. Its official string form would be split into characters by the scorer.",
    "LightRAG: API mode of the official Examples/run_lightrag.py does not run at commit fdbab59 (an "
    "UnboundLocalError and a duplicate keyword argument). Both are fixed in memory with a 4-line change; the "
    "query settings are unchanged. LightRAG 1.2.5 also needs the README context-return change. Both diffs are "
    "in results/audit/patches/.",
    "Each system uses its own default retrieval and chunking settings. top_k is 5 where the system exposes it.",
    "4Minds: the inference WebSocket has no temperature or max-token settings, so the server defaults apply "
    "(temperature 0.3, 4,096 max tokens). The 4Minds dataset also holds the platform's dataset manifest as one "
    "extra graph node (204 nodes: 203 Medical.txt chunks + manifest).",
    "4Minds (SYMI) runs through POST /api/v1/user/inference (inference_engine symi): the SYMI WebSocket path "
    "rejects API keys. For API keys this endpoint returns chunk references (all from Medical.txt) but not chunk "
    "text, so SYMI has no faithfulness score. SYMI is an agent with its own instructions; the persona prompt "
    "may not apply to it in the same way as on Constellations.",
    "Gemini + RAG Engine: the corpus is in europe-west4 (RAG Engine defaults: Spanner mode, RagManagedDb, "
    "Basic tier, default chunking and embeddings). us-central1 is allowlist-only for new projects, and its "
    "Serverless mode failed with a Google capacity error. The model is served from the global endpoint.",
    "Faithfulness (official) is NaN for most answers: at commit fdbab59 the verdict prompt does not ask for JSON, "
    "gpt-4o-mini answers in Markdown prose and the parser finds no verdicts (results/audit/diagnostics/"
    "faithfulness_nan.json). 'Faithfulness (JSON-format fix)' runs the official code and judge settings again "
    "with one added sentence that asks for the format of the prompt's own examples "
    "(results/audit/patches/faithfulness-fdbab59-json-format.diff). It is not part of the official protocol.",
    "Faithfulness reads only the first 10,000 characters of `context`. Systems that return more context "
    "(4Minds multi-step retrieval: up to 50 chunks; RAG Engine: about 20,000 characters) are judged on part of "
    "it. 4Minds chunks are stored in 4Minds' own score order (highest first) so that the judge sees the "
    "strongest chunks; RAG Engine returns its chunks in relevance order.",
    "The medical source text can be in the training data of the models.",
    "Each system ran one time. LLM answers and LLM-judge scores vary between runs; use the confidence intervals.",
    "The judge is not fully repeatable at temperature 0 with a fixed seed: scoring the same 10 pilot answers "
    "again changed answer correctness for 4 of 10 answers (the largest change was 0.60 to 0.97; ROUGE-L did not "
    "change). Single-question scores are not reliable; the averages over many questions are "
    "(results/pilot/_judge_repeat_test).",
    "Prod systems (4Minds, Gemini, Vertex AI) can change over time. The dates are in the run manifests.",
]


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


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", default=str(bc.RESULTS))
    parser.add_argument("--subset", default="medical")
    parser.add_argument("--label", default="", help="for example PILOT")
    args = parser.parse_args()
    root = Path(args.results).resolve()
    rng = np.random.default_rng(SEED)

    systems, scores = [], {}
    for key, name, description in SYSTEMS:
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
            "key": key, "name": name, "description": description, "folder": str(folder),
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
    if REFERENCE in scores:
        for system in systems:
            other = system["key"]
            if other == REFERENCE:
                continue
            paired[other] = {}
            for question_type in TYPES + ["All questions"]:
                types = TYPES if question_type == "All questions" else [question_type]
                metric_list = ["answer_correctness"] if question_type == "All questions" else METRICS[question_type]
                paired[other][question_type] = {}
                for metric in metric_list:
                    if metric in FAITHFULNESS and not (available[REFERENCE] and available[other]):
                        continue
                    diffs = []
                    for qt in types:
                        a, b = scores[REFERENCE].get(qt, {}), scores[other].get(qt, {})
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
        "reference_system": REFERENCE, "types": TYPES, "metric_set": METRICS, "metric_names": METRIC_NAMES,
        "systems": systems, "metrics": metrics, "overall": overall, "paired": paired, "caveats": CAVEATS,
    }
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
                        writer.writerow([REFERENCE, other, question_type, metric,
                                         *(round(r[k], 4) for k in ("diff_mean", "ci_low", "ci_high")), r["n"]])
    (summary_dir / "report.md").write_text(markdown(out))
    bc.audit("aggregate", results=str(root), systems=[s["key"] for s in systems], label=args.label)
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
    lines += ["", "## Operating data", "", "| System | Answered | Failed | \"I don't know\" | Median latency (s) | "
              "Est. cost (USD) |", "|---|---|---|---|---|---|"]
    for s in out["systems"]:
        o = s["operations"]
        lines.append(f"| {s['name']} | {o['answered']}/{o['questions']} | {o['failed']} | {o['dont_know']} | "
                     f"{(o.get('latency') or {}).get('median_s', 'n/a')} | "
                     f"{o['estimated_cost_usd'] if o['estimated_cost_usd'] is not None else 'n/a'} |")
    lines += ["", "## Systems", ""] + [f"- **{s['name']}**: {s['description']}. Run {s['run_started']} to "
                                       f"{s['run_finished']}." for s in out["systems"]]
    lines += ["", "## Notes and caveats", ""] + [f"- {c}" for c in out["caveats"]] + [""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()

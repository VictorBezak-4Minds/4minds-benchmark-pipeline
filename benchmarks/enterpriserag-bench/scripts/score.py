#!/usr/bin/env python3
"""Score one system with the official EnterpriseRAG-Bench metrics-based evaluation.

    ./bench enterpriserag-bench score_<system> erag score.py --system-dir runs/<run>/<system>/all

1. Converts predictions.json to the official answers file (answers.jsonl: question_id, answer,
   document_ids), the input format of metrics_based_eval.py and of the leaderboard Space.
2. Runs upstream src/scripts/answer_evaluation/metrics_based_eval.main() unchanged, in this
   process, with its default settings (citation stripping on, document correction on) and the
   official questions.jsonl. Outputs in --system-dir: results.json, questions_updated.jsonl.
3. Writes score_manifest.json: judge models, tokens and cost per model, the questions with a
   silent judge failure, the official aggregate stats and the leaderboard overall score.

The judge is the upstream client (OpenAI Responses API). Its models come from the backend
entries --judge and --cheap-judge in pipeline/llm_backends.json (defaults: the official
gpt-5.4 and gpt-5-mini). The key is read with bench_common.load_key() and given to the
upstream module in memory (no environment variable). In-memory wrappers only count: tokens per
model, and the silent failures of upstream (a correctness judgment that returns None scores
"not correct"; a fact check that raises makes completeness 0; a document evaluation that returns
unusable output keeps the original gold set; a citation-strip failure keeps the answer).

The official code writes results.json after each question, so a stopped run continues with
the same command (--resume is always on). A folder scored with other judge models stops.
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import bench_common as bc
import llm_backends

UPSTREAM = bc.UPSTREAM_REPO
lock = threading.Lock()
USAGE = {}
# failure kind -> the texts that identify the question (question text, fact statement or answer)
FAILED_TEXTS = {"correctness_none": set(), "fact_check_raised": set(), "doc_eval_unusable": set(),
                "citation_strip_raised": set()}


def check_upstream():
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=UPSTREAM, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=UPSTREAM, capture_output=True, text=True).stdout
    dirty = [line for line in status.splitlines() if "__pycache__" not in line and not line.endswith(".DS_Store")]
    if commit != bc.UPSTREAM_COMMIT or dirty:
        sys.exit(f"Benchmark repo is not clean at {bc.UPSTREAM_COMMIT}: HEAD={commit} status={dirty[:5]!r}")
    return commit


def count_usage(event):
    response = getattr(event, "response", None)
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    model = getattr(response, "model", "unknown")
    cached = getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0
    reasoning = getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0
    with lock:
        u = USAGE.setdefault(model, {"calls": 0, "input_tokens": 0, "cached_input_tokens": 0,
                                     "output_tokens": 0, "reasoning_tokens": 0, "not_completed": 0})
        u["calls"] += 1
        u["input_tokens"] += usage.input_tokens or 0
        u["cached_input_tokens"] += cached
        u["output_tokens"] += usage.output_tokens or 0
        u["reasoning_tokens"] += reasoning
        u["not_completed"] += event.type != "response.completed"


def install_hooks(mbe):
    from openai.resources.responses import Responses
    original_create = Responses.create

    def create(self, *args, **kwargs):
        stream = original_create(self, *args, **kwargs)
        if not kwargs.get("stream"):
            return stream

        def events():
            for event in stream:
                if event.type in ("response.completed", "response.incomplete", "response.failed"):
                    count_usage(event)
                yield event
        return events()

    Responses.create = create

    def recording(name, kind, text_of, failed):
        original = getattr(mbe, name)

        def wrapper(*args, **kwargs):
            try:
                result = original(*args, **kwargs)
            except Exception:
                if kind.endswith("_raised"):
                    with lock:
                        FAILED_TEXTS[kind].add(text_of(args, kwargs))
                raise
            if failed(result):
                with lock:
                    FAILED_TEXTS[kind].add(text_of(args, kwargs))
            return result

        setattr(mbe, name, wrapper)

    def arg(position, name):
        return lambda args, kwargs: kwargs[name] if name in kwargs else args[position]

    recording("evaluate_answer_correctness", "correctness_none", arg(0, "question"), lambda r: r[0] is None)
    recording("validate_single_fact", "fact_check_raised", arg(1, "statement"), lambda r: False)
    recording("strip_answer_citations", "citation_strip_raised", arg(0, "answer"), lambda r: False)
    recording("evaluate_documents_with_consensus", "doc_eval_unusable", arg(0, "question"), lambda r: r[0] is None)


def failed_question_ids(predictions, updated_file):
    """Map the recorded failure texts to question IDs: {question_id: [failure kinds]}."""
    answered = {p["question_id"]: p for p in predictions}
    by_question, by_fact, by_answer = {}, {}, {}
    rows = [json.loads(line) for line in bc.profile.OFFICIAL_QUESTIONS.read_text().splitlines() if line.strip()]
    if updated_file.exists():
        rows += [json.loads(line) for line in updated_file.read_text().splitlines() if line.strip()]
    for row in rows:
        if row["question_id"] in answered:
            by_question.setdefault(row["question"], set()).add(row["question_id"])
            for fact in row.get("answer_facts") or []:
                by_fact.setdefault(fact, set()).add(row["question_id"])
    for qid, p in answered.items():
        by_answer.setdefault(p["generated_answer"], set()).add(qid)
    lookup = {"correctness_none": by_question, "doc_eval_unusable": by_question,
              "fact_check_raised": by_fact, "citation_strip_raised": by_answer}
    failed = {}
    for kind, texts in FAILED_TEXTS.items():
        for text in texts:
            for qid in lookup[kind].get(text) or {f"unmapped: {text[:80]}"}:
                failed.setdefault(qid, set()).add(kind)
    return {qid: sorted(kinds) for qid, kinds in failed.items()}


def cost(usage, judges):
    total = 0.0
    by_model = {}
    for model, u in usage.items():
        backend = next((b for b in judges if model == b.model or model.startswith(b.model + "-")), None)
        if backend is None:
            by_model[model] = None
            continue
        p = backend.prices
        uncached = u["input_tokens"] - u["cached_input_tokens"]
        c = (uncached * p.get("input", 0) + u["cached_input_tokens"] * p.get("cached_input", p.get("input", 0))
             + u["output_tokens"] * p.get("output", 0)) / 1e6
        by_model[model] = round(c, 4)
        total += c
    return round(total, 4), by_model


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--system-dir", required=True, help="the folder with predictions.json")
    parser.add_argument("--judge", default="openai-gpt-5.4", choices=llm_backends.names())
    parser.add_argument("--cheap-judge", default="openai-gpt-5-mini", choices=llm_backends.names())
    parser.add_argument("--parallelism", type=int, default=8, help="parallel questions (official option)")
    parser.add_argument("--question-id", help="score one question again (official option)")
    parser.add_argument("--allow-incomplete", action="store_true",
                        help="score although the run has failed or not-run questions (they are not in the official "
                             "averages; the report must list them)")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    system_dir = Path(args.system_dir).resolve()
    judge, cheap = llm_backends.Backend(args.judge), llm_backends.Backend(args.cheap_judge)
    commit = check_upstream()

    run_manifest = json.loads((system_dir / "manifest.json").read_text())
    summary = run_manifest["summary"]
    if (summary["failed"] or summary["not_run"]) and not args.allow_incomplete:
        sys.exit(f"{system_dir}: {summary['failed']} failed and {summary['not_run']} not-run questions. The official "
                 "scorer counts only the answered questions. Complete the run first (or --allow-incomplete for a test).")

    manifest_path = system_dir / "score_manifest.json"
    earlier = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    judge_models = {"judge": judge.model, "cheap_judge": cheap.model}
    if earlier and earlier["judge_models"] != judge_models:
        sys.exit(f"{system_dir} was scored with {earlier['judge_models']}. Use a new run folder "
                 "(pipeline/derive_run.py) to score with other judges.")

    predictions = json.loads((system_dir / "predictions.json").read_text())
    answers_file = system_dir / "answers.jsonl"
    with answers_file.open("w") as f:
        for p in predictions:
            f.write(json.dumps({"question_id": p["question_id"], "answer": p["generated_answer"],
                                "document_ids": p.get("document_ids") or []}, ensure_ascii=False) + "\n")

    uuid_index = bc.SHARED / "scorer" / "uuid_index.json"
    if not uuid_index.exists():
        uuid_index.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bc.profile.UUID_INDEX, uuid_index)

    os.chdir(UPSTREAM)
    sys.path.insert(0, str(UPSTREAM))
    for name in ("BRAINTRUST_API_KEY", "BRAINTRUST_PROJECT"):
        os.environ.pop(name, None)
    import src.llm.factory as factory
    import src.llm.openai_llm as openai_llm
    factory.LLM_PROVIDER = "openai"
    openai_llm.LLM_API_KEY = bc.load_key(judge.auth["provider"])
    openai_llm.LLM_MODEL_NAME, openai_llm.CHEAP_LLM_MODEL_NAME = judge.model, cheap.model
    import src.scripts.answer_evaluation.metrics_based_eval as mbe
    install_hooks(mbe)

    results_file, updated_file = system_dir / "results.json", system_dir / "questions_updated.jsonl"
    scored_before = {q["question_id"] for q in json.loads(results_file.read_text())["questions"]} \
        if results_file.exists() else set()
    argv = ["metrics_based_eval.py", "--answers-file", str(answers_file),
            "--questions-file", str(bc.profile.OFFICIAL_QUESTIONS), "--results-file", str(results_file),
            "--updated-questions-file", str(updated_file), "--uuid-index-cache-file", str(uuid_index),
            "--parallelism", str(args.parallelism), "--resume"]
    if args.question_id:
        argv += ["--question-id", args.question_id]
    bc.audit("score_start", system_dir=str(system_dir), argv=argv[1:], judge_models=judge_models)
    sys.argv, sys.stdin = argv, io.StringIO("")
    exit_code = 0
    try:
        mbe.main()
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    if exit_code:
        sys.exit(f"metrics_based_eval exited with {exit_code}")

    results = json.loads(results_file.read_text())
    stats = results["aggregate_stats"]
    usage = {m: dict(u) for m, u in USAGE.items()}
    for m, u in ((earlier or {}).get("judge_usage") or {}).items():
        total = usage.setdefault(m, {k: 0 for k in u})
        for k, v in u.items():
            total[k] = total.get(k, 0) + v
    total_cost, cost_by_model = cost(usage, [judge, cheap])
    answered = {p["question_id"] for p in predictions}
    scored = {q["question_id"] for q in results["questions"]}
    scored_now = (scored - scored_before) | ({args.question_id} if args.question_id else set())
    failed = {q: k for q, k in ((earlier or {}).get("failed_questions") or {}).items() if q not in scored_now}
    failed.update(failed_question_ids(predictions, updated_file))
    invocations = ((earlier or {}).get("invocations") or []) + [
        {"time": bc.now(), "scored": len(scored_now), "question_id": args.question_id,
         "usage": {m: dict(u) for m, u in USAGE.items()}}]
    manifest = {
        "scored": bc.now(), "upstream_commit": commit, "scorer": "src/scripts/answer_evaluation/metrics_based_eval.py",
        "argv": argv[1:], "settings": {"citation_stripping": True, "correction": True, "parallelism": args.parallelism},
        "judge_backends": {"judge": args.judge, "cheap_judge": args.cheap_judge}, "judge_models": judge_models,
        "judge_usage": usage, "judge_cost_usd": total_cost, "judge_cost_by_model": cost_by_model,
        "failed_questions": failed, "invocations": invocations,
        "predictions_sha256": bc.sha256(system_dir / "predictions.json"),
        "answers_sha256": bc.sha256(answers_file), "questions_file": str(bc.profile.OFFICIAL_QUESTIONS),
        "questions_sha256": bc.sha256(bc.profile.OFFICIAL_QUESTIONS), "answered": len(answered),
        "scored_questions": len(scored), "missing_scores": sorted(answered - scored),
        "run_failed": summary["failed"], "run_not_run": summary["not_run"],
        "aggregate_stats": stats, "overall_score": stats["combined_correctness_completeness_score"],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    bc.audit("score", system_dir=str(system_dir), overall_score=manifest["overall_score"],
             correctness=stats["average_correctness_pct"], completeness=stats["average_completeness_pct"],
             recall=stats["average_recall_pct"], invalid_extra_docs=stats["average_invalid_extra_docs"],
             corrected=stats["num_corrected_questions"], judge_cost_usd=total_cost, failed_questions=failed)
    print(json.dumps({k: manifest[k] for k in ("overall_score", "aggregate_stats", "judge_usage", "judge_cost_usd",
                                               "failed_questions", "missing_scores")}, indent=2))
    if manifest["missing_scores"] or failed:
        print("\nWARNING: some questions are not scored, or a judge call failed silently (failed_questions; "
              "the official code then scores 0 or keeps the original gold set). Run the same command again "
              "for missing questions; score a failed question again with --question-id <id>.")
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Score one system with the official QASPER evaluator (Answer F1 only).

    ./bench qasper score_pilot_gemini eval score.py --system-dir runs/2026-10-09_pilot/gemini/test

1. Converts predictions.json to the evaluator input (predictions.jsonl, predicted_evidence
   empty: Evidence F1 is not used).
2. Runs upstream/qasper_evaluator.py unchanged against the gold subset -> scores_official.json.
3. Writes per_question.jsonl with the evaluator's own functions (imported from the same file)
   and checks that their means are the same as the official output.

It stops if the predictions do not cover exactly the gold questions: the evaluator gives 0
to a gold question without a prediction.
"""
import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import bench_common as bc

EVALUATOR_SHA256 = "781aba7cd8e524bef4f0a1b4bf3504e5b02cb1d8d5bf32a8f0a89dfa83e86bfe"


def load_evaluator():
    spec = importlib.util.spec_from_file_location("qasper_evaluator", bc.profile.OFFICIAL_EVALUATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-dir", required=True, help="the folder with predictions.json")
    args = parser.parse_args()
    system_dir = Path(args.system_dir)
    evaluator_path, gold_path = bc.profile.OFFICIAL_EVALUATOR, bc.profile.GOLD_FILE
    if bc.sha256(evaluator_path) != EVALUATOR_SHA256:
        sys.exit(f"{evaluator_path} is not the official evaluator (sha256 differs).")

    predictions = json.loads((system_dir / "predictions.json").read_text())
    gold = json.loads(gold_path.read_text())
    gold_ids = {qa["question_id"] for paper in gold.values() for qa in paper["qas"]}
    predicted_ids = {p["question_id"] for p in predictions}
    if predicted_ids != gold_ids:
        sys.exit(f"Predictions do not match the gold questions: missing {sorted(gold_ids - predicted_ids)}, "
                 f"extra {sorted(predicted_ids - gold_ids)}. Complete the run first.")

    jsonl = system_dir / "predictions.jsonl"
    with jsonl.open("w") as f:
        for p in predictions:
            f.write(json.dumps({"question_id": p["question_id"], "predicted_answer": p["generated_answer"],
                                "predicted_evidence": []}, ensure_ascii=False) + "\n")

    command = [sys.executable, str(evaluator_path), "--predictions", str(jsonl), "--gold", str(gold_path)]
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode:
        sys.exit(f"Official evaluator failed ({done.returncode}): {done.stderr[-2000:]}")
    official = json.loads(done.stdout)
    (system_dir / "scores_official.json").write_text(json.dumps(official, indent=2))

    evaluator = load_evaluator()
    references = evaluator.get_answers_and_evidence(gold, False)
    by_id = {p["question_id"]: p for p in predictions}
    rows = []
    for question_id, refs in references.items():
        answer = by_id[question_id]["generated_answer"]
        scored = [(evaluator.token_f1_score(answer, r["answer"]), r["type"]) for r in refs]
        f1, best_type = sorted(scored, key=lambda x: x[0], reverse=True)[0]
        rows.append({"question_id": question_id, "answer_f1": f1, "best_reference_type": best_type,
                     "sampled_type": by_id[question_id]["answer_type"], "answer": answer,
                     "answer_words": len(answer.split()), "references": [r["answer"] for r in refs]})
    with (system_dir / "per_question.jsonl").open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    mean = sum(r["answer_f1"] for r in rows) / len(rows)
    by_type = {}
    for r in rows:
        by_type.setdefault(r["best_reference_type"], []).append(r["answer_f1"])
    checks = [abs(mean - official["Answer F1"]) < 1e-12] + [
        abs(sum(v) / len(v) - official["Answer F1 by type"][k]) < 1e-12 for k, v in by_type.items()]
    if not all(checks) or official["Missing predictions"]:
        sys.exit(f"Per-question scores do not reproduce the official output: {mean} vs {official}")

    manifest = {"scored": bc.now(), "command": command, "evaluator_sha256": EVALUATOR_SHA256,
                "gold": str(gold_path), "gold_sha256": bc.sha256(gold_path),
                "predictions_sha256": bc.sha256(system_dir / "predictions.json"), "questions": len(rows),
                "official": official}
    (system_dir / "score_manifest.json").write_text(json.dumps(manifest, indent=2))
    bc.audit("score", system_dir=str(system_dir), answer_f1=official["Answer F1"],
             by_type=official["Answer F1 by type"], questions=len(rows))
    print(json.dumps(official, indent=2))


if __name__ == "__main__":
    main()

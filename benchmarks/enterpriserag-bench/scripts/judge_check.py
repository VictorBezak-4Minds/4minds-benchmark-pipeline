#!/usr/bin/env python3
"""Make two test system folders for a check of the official judge, before the pilot is scored.

    ./bench enterpriserag-bench judge_check erag judge_check.py [--questions 2]
    ./bench enterpriserag-bench judge_check_gold erag score.py --system-dir audit/diagnostics/judge_check/gold
    ./bench enterpriserag-bench judge_check_wrong erag score.py --system-dir audit/diagnostics/judge_check/wrong

gold:  the gold answer and the gold documents of each question. Expected: correct, completeness
       and recall near 100, no correction (the document set is the gold set).
wrong: the gold answer of another question type and no documents. Expected: not correct,
       completeness near 0, recall 0.
The first --questions pilot questions with gold documents are used.
"""
import argparse
import json

import bench_common as bc


def write(folder, predictions):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "predictions.json").write_text(json.dumps(predictions, indent=2, ensure_ascii=False))
    summary = {"questions": len(predictions), "answered": len(predictions), "failed": 0, "not_run": 0}
    (folder / "manifest.json").write_text(json.dumps({"system": f"judge_check_{folder.name}", "summary": summary},
                                                     indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--questions", type=int, default=2)
    args = parser.parse_args()
    official = {}
    for line in bc.profile.OFFICIAL_QUESTIONS.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            official[row["question_id"]] = row
    pilot = json.loads((bc.BENCH_DIR / "data" / "pilot_questions.json").read_text())
    chosen = [official[q["question_id"]] for q in pilot if official[q["question_id"]].get("expected_doc_ids")]
    chosen = chosen[:args.questions]
    others = [row for row in official.values() if row["question_type"] not in {q["question_type"] for q in chosen}]
    out = bc.AUDIT_DIR / "diagnostics" / "judge_check"
    for name in ("gold", "wrong"):
        if (out / name / "results.json").exists():
            raise SystemExit(f"{out / name} was already scored. Move it to a _superseded_ folder first.")
    write(out / "gold", [{"question_id": q["question_id"], "question_type": q["question_type"],
                          "question": q["question"], "context": [], "generated_answer": q["gold_answer"],
                          "document_ids": q["expected_doc_ids"]} for q in chosen])
    write(out / "wrong", [{"question_id": q["question_id"], "question_type": q["question_type"],
                           "question": q["question"], "context": [], "generated_answer": others[i]["gold_answer"],
                           "document_ids": []} for i, q in enumerate(chosen)])
    bc.audit("judge_check_inputs", folder=str(out), question_ids=[q["question_id"] for q in chosen])
    print(f"Wrote {out / 'gold'} and {out / 'wrong'} for {[q['question_id'] for q in chosen]}")


if __name__ == "__main__":
    main()

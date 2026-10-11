#!/usr/bin/env python3
"""Check the graphrag_local retriever on an index (also a --limit test index): search only, no answers.

    ./bench enterpriserag-bench check_graphrag graphrag check_graphrag_retriever.py \
        --graphrag-index shared/graphrag/enterpriserag-bench-pilot_first20 --questions 3

For each of the first --questions pilot questions: the documents and text units of the context,
how many gold documents are in it, the context size and the search time. The readiness check of
the runner is not called (it refuses test indexes). Costs only the question embeddings.
"""
import argparse
import json

import bench_common as bc
import retrievers


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    retrievers.add_args(parser)
    parser.add_argument("--questions-file", default="data/pilot_questions.json")
    parser.add_argument("--questions", type=int, default=3)
    args = parser.parse_args()
    retriever = retrievers.make("graphrag_local", args)
    questions = json.loads((bc.BENCH_DIR / args.questions_file).read_text())[:args.questions]
    for q in questions:
        result, error, _ = retriever.retrieve(q, 120)
        if error:
            print(q["question_id"], "ERROR", error)
            continue
        gold = set(q.get("expected_doc_ids") or [])
        print(json.dumps({"question_id": q["question_id"], "documents": len(result["document_ids"]),
                          "gold_found": len(gold & set(result["document_ids"])), "gold": len(gold),
                          **result["extra"], "context_start": result["contexts"][0][:300] if result["contexts"] else ""}))


if __name__ == "__main__":
    main()

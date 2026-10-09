#!/usr/bin/env python3
"""Write data/Questions/pilot_questions.json: a stratified random sample of medical_questions.json.

The pilot uses 5 Fact Retrieval, 2 Complex Reasoning, 2 Contextual Summarize and
1 Creative Generation question (seed 42), so every question type and metric is tested.

    ./bench graphrag-bench make_pilot eval make_pilot.py
"""
import json
import random

import bench_common as bc

COUNTS = {"Fact Retrieval": 5, "Complex Reasoning": 2, "Contextual Summarize": 2, "Creative Generation": 1}
SEED = 42

questions = json.loads(bc.QUESTION_FILES["medical"].read_text())
rng = random.Random(SEED)
sample = []
for question_type, n in COUNTS.items():
    group = [q for q in questions if q["question_type"] == question_type]
    sample += rng.sample(group, n)
order = {bc.question_key(q): i for i, q in enumerate(questions)}
sample.sort(key=lambda q: order[bc.question_key(q)])

out = bc.BENCH_DIR / "data" / "Questions" / "pilot_questions.json"
out.write_text(json.dumps(sample, indent=2, ensure_ascii=False))
for q in sample:
    print(f"{q['id']}  {q['question_type']:<22} {q['question'][:70]}")
print(f"\n{len(sample)} questions -> {out}  sha256 {bc.sha256(out)}")

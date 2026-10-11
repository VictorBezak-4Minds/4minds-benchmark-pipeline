#!/usr/bin/env python3
"""Make the EnterpriseRAG-Bench pilot: the question files and the corpus slice.

    ./bench enterpriserag-bench make_pilot eval make_pilot.py

- data/questions.json: all 500 official questions (upstream questions.jsonl, unchanged rows)
  as a JSON array, because bench_common reads JSON. The scorer reads the official .jsonl.
- data/pilot_questions.json: 50 questions, stratified by question type (QUOTA: about 10% of
  each type, at least 2), seed 42.
- data/pilot_corpus.json: the corpus slice. Every gold document of the pilot questions, plus
  random distractors from each source (slack, gmail, ...) in proportion to the source size,
  to TARGET_DOCS documents, seed 42. A document that the official extract_document_content()
  cannot read is skipped (no system could index it).
- data/pilot_manifest.json: the counts, seeds and sha256 of every input and output.
"""
import collections
import json
import random

import bench_common as bc

SEED = 42
TARGET_DOCS = 10_000
QUOTA = {"basic": 17, "semantic": 12, "intra_document_reasoning": 4, "project_related": 4, "constrained": 3,
         "conflicting_info": 2, "completeness": 2, "miscellaneous": 2, "info_not_found": 2, "high_level": 2}
DATA = bc.BENCH_DIR / "data"


def readable(dsid, path):
    try:
        bc.profile.document(dsid, path)
        return True
    except Exception:
        return False


def main():
    profile = bc.profile
    questions = [json.loads(line) for line in profile.OFFICIAL_QUESTIONS.read_text().splitlines() if line.strip()]
    index = json.loads(profile.UUID_INDEX.read_text())

    rng = random.Random(SEED)
    by_type = collections.defaultdict(list)
    for q in questions:
        by_type[q["question_type"]].append(q)
    if set(by_type) != set(QUOTA):
        raise SystemExit(f"Question types changed: {sorted(by_type)}")
    picked_ids = set()
    for kind, n in QUOTA.items():
        picked_ids |= {q["question_id"] for q in rng.sample(by_type[kind], n)}
    pilot = [q for q in questions if q["question_id"] in picked_ids]

    gold = sorted({d for q in pilot for d in q["expected_doc_ids"]})
    unreadable_gold = [d for d in gold if not readable(d, index[d])]
    if unreadable_gold:
        raise SystemExit(f"Gold documents that extract_document_content() cannot read: {unreadable_gold}")

    gold_set = set(gold)
    by_source = collections.defaultdict(list)
    for dsid, path in sorted(index.items()):
        if dsid not in gold_set:
            by_source[path.split("/")[0]].append(dsid)
    total = sum(len(v) for v in by_source.values())
    distractors_needed = TARGET_DOCS - len(gold)
    quota = {s: round(distractors_needed * len(v) / total) for s, v in by_source.items()}
    distractors, skipped = [], collections.Counter()
    for source in sorted(by_source):
        pool = by_source[source][:]
        rng.shuffle(pool)
        taken = 0
        for dsid in pool:
            if taken == quota[source]:
                break
            if readable(dsid, index[dsid]):
                distractors.append(dsid)
                taken += 1
            else:
                skipped[source] += 1

    documents = [{"dsid": d, "path": index[d], "gold": d in gold_set} for d in sorted(gold + distractors)]
    DATA.mkdir(parents=True, exist_ok=True)
    all_file, pilot_file, corpus_file = profile.QUESTION_FILES["all"], DATA / "pilot_questions.json", profile.CORPUS_FILE
    all_file.write_text(json.dumps(questions, indent=1, ensure_ascii=False))
    pilot_file.write_text(json.dumps(pilot, indent=1, ensure_ascii=False))
    corpus_file.write_text(json.dumps({"description": "EnterpriseRAG-Bench pilot corpus slice (make_pilot.py)",
                                       "documents": documents}, indent=1))

    chars = sum(len(profile.document(d["dsid"], d["path"])["text"]) for d in documents)
    manifest = {
        "created": bc.now(),
        "seed": SEED,
        "quota": QUOTA,
        "target_docs": TARGET_DOCS,
        "upstream_commit": profile.UPSTREAM_COMMIT,
        "official_questions_sha256": bc.sha256(profile.OFFICIAL_QUESTIONS),
        "uuid_index_sha256": bc.sha256(profile.UUID_INDEX),
        "corpus_documents_total": len(index),
        "pilot_questions": len(pilot),
        "pilot_question_types": collections.Counter(q["question_type"] for q in pilot),
        "pilot_questions_without_gold": sum(not q["expected_doc_ids"] for q in pilot),
        "gold_documents": len(gold),
        "distractor_documents": len(distractors),
        "slice_documents": len(documents),
        "slice_by_source": collections.Counter(d["path"].split("/")[0] for d in documents),
        "unreadable_skipped_by_source": skipped,
        "slice_chars": chars,
        "outputs": {f.name: bc.sha256(f) for f in (all_file, pilot_file, corpus_file)},
    }
    (DATA / "pilot_manifest.json").write_text(json.dumps(manifest, indent=2))
    bc.audit("make_pilot", **{k: manifest[k] for k in ("seed", "pilot_questions", "slice_documents", "slice_chars",
                                                        "outputs")})
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

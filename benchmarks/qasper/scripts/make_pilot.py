#!/usr/bin/env python3
"""Make the QASPER pilot: questions, corpus slice and gold subset from the official test file.

    ./bench qasper make_pilot eval make_pilot.py

- Questions: 25 questions from 25 different papers, stratified by the majority answer type
  of each question's references (13 extractive, 6 abstractive, 3 yes/no, 3 unanswerable,
  about the test-set proportions), seed 42. Each query names its paper (profile.query).
- Corpus slice: the papers of those questions, plus 10% of the other test papers (seed 42),
  in one text file (one "# <title>" block per paper).
- Gold subset: the official test format with only the pilot questions. The official
  evaluator gives 0 to every gold question without a prediction, so it must not see others.
"""
import collections
import json
import random

import bench_common as bc

SEED = 42
QUOTA = {"extractive": 13, "abstractive": 6, "boolean": 3, "none": 3}
DISTRACTOR_FRACTION = 0.10
DATA = bc.BENCH_DIR / "data"


def answer_type(annotation):
    """The answer type, with the same rules as get_answers_and_evidence() in the official evaluator."""
    a = annotation["answer"]
    if a["unanswerable"]:
        return "none"
    if a["extractive_spans"]:
        return "extractive"
    if a["free_form_answer"]:
        return "abstractive"
    return "boolean"


def render(paper):
    parts = [f"# {paper['title']}", "## Abstract", paper["abstract"]]
    for section in paper["full_text"]:
        if section["section_name"]:
            parts.append(f"## {section['section_name']}")
        parts += [p for p in section["paragraphs"] if p.strip()]
    captions = [f["caption"] for f in paper.get("figures_and_tables") or [] if f.get("caption")]
    if captions:
        parts += ["## Figures and tables", *captions]
    return "\n\n".join(parts)


def main():
    if bc.sha256(DATA / "qasper-test-and-evaluator-v0.3.tgz") != bc.profile.UPSTREAM_SHA256:
        raise SystemExit("The downloaded release archive does not match UPSTREAM_SHA256.")
    test = json.loads(bc.profile.OFFICIAL_TEST.read_text())

    candidates = []
    for paper_id, paper in test.items():
        for qa in paper["qas"]:
            types = [answer_type(a) for a in qa["answers"]]
            majority = collections.Counter(types).most_common(1)[0][0]
            candidates.append((paper_id, qa["question_id"], majority))
    random.Random(SEED).shuffle(candidates)
    quota, picked, used = dict(QUOTA), [], set()
    for paper_id, question_id, kind in candidates:
        if quota[kind] > 0 and paper_id not in used:
            picked.append((paper_id, question_id, kind))
            used.add(paper_id)
            quota[kind] -= 1
    if any(quota.values()):
        raise SystemExit(f"Not enough questions for the quota: {quota}")

    others = sorted(set(test) - used)
    distractors = random.Random(SEED).sample(others, round(DISTRACTOR_FRACTION * len(others)))
    corpus_papers = [p for p in test if p in used or p in set(distractors)]

    questions, gold = [], {}
    for paper_id, question_id, kind in picked:
        paper = test[paper_id]
        qa = next(q for q in paper["qas"] if q["question_id"] == question_id)
        questions.append({
            "id": question_id,
            "paper_id": paper_id,
            "title": paper["title"],
            "original_question": qa["question"],
            "question": bc.profile.query(paper["title"], qa["question"]),
            "answer_type": kind,
            "reference_types": [answer_type(a) for a in qa["answers"]],
            "source": bc.profile.SOURCE,
        })
        gold.setdefault(paper_id, {**paper, "qas": []})["qas"].append(qa)

    DATA.mkdir(parents=True, exist_ok=True)
    question_file, gold_file, corpus_file = bc.QUESTION_FILES["test"], bc.profile.GOLD_FILE, bc.CORPUS_FILE
    question_file.write_text(json.dumps(questions, indent=2, ensure_ascii=False))
    gold_file.write_text(json.dumps(gold, indent=2, ensure_ascii=False))
    corpus_file.write_text("\n\n\n".join(render(test[p]) for p in corpus_papers) + "\n")

    manifest = {
        "created": bc.now(),
        "seed": SEED,
        "quota": QUOTA,
        "distractor_fraction": DISTRACTOR_FRACTION,
        "official_test": str(bc.profile.OFFICIAL_TEST),
        "official_test_sha256": bc.sha256(bc.profile.OFFICIAL_TEST),
        "release_sha256": bc.profile.UPSTREAM_SHA256,
        "test_papers": len(test),
        "test_questions": sum(len(p["qas"]) for p in test.values()),
        "questions": [{"id": q, "paper_id": p, "answer_type": t} for p, q, t in picked],
        "question_papers": sorted(used),
        "distractor_papers": sorted(distractors),
        "corpus_papers": len(corpus_papers),
        "corpus_chars": len(corpus_file.read_text()),
        "outputs": {str(f.name): bc.sha256(f) for f in (question_file, gold_file, corpus_file)},
    }
    (DATA / "pilot_manifest.json").write_text(json.dumps(manifest, indent=2))
    bc.audit("make_pilot", **{k: manifest[k] for k in ("seed", "corpus_papers", "corpus_chars", "outputs")},
             questions=len(questions))
    print(json.dumps({k: v for k, v in manifest.items() if k not in ("questions", "question_papers",
                                                                     "distractor_papers")}, indent=2))
    print(collections.Counter(q["answer_type"] for q in questions))


if __name__ == "__main__":
    main()

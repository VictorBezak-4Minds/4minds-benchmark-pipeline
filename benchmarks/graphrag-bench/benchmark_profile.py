"""GraphRAG-Bench profile: the benchmark-specific part of the pipeline.

pipeline/bench_common.py imports this module (as `bc.profile`) when ./bench runs with
`graphrag-bench`. Every benchmark folder has one benchmark_profile.py with the same names;
see the README.md in the hub root for the contract.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
TITLE = "GraphRAG-Bench"
# Name for the resources that the setup scripts create in external systems (4Minds dataset,
# RAG Engine corpus). One benchmark corpus per resource, so retrieval cannot reach other data.
RESOURCE_NAME = "graphragbench-medical"
RESOURCE_DESCRIPTION = "GraphRAG-Bench Medical corpus (Medical.txt), benchmark only"

# The official repo at the pinned commit. Its question files are the ground truth that its
# scoring code was released with (the local data/Questions copy has 251 different medical answers).
UPSTREAM_REPO = HERE / "upstream"
UPSTREAM_URL = "https://github.com/GraphRAG-Bench/GraphRAG-Benchmark"
UPSTREAM_COMMIT = "fdbab5959b18c96532580877ffe27d112bccc0ec"

SUBSETS = ["medical", "novel"]
QUESTION_FILES = {
    "medical": UPSTREAM_REPO / "Datasets" / "Questions" / "medical_questions.json",
    "novel": UPSTREAM_REPO / "Datasets" / "Questions" / "novel_questions.json",
}
CORPUS_FILE = HERE / "data" / "Corpus" / "corpus_txt" / "Medical.txt"
# question_type values that a pipeline/score_extra.py config can select.
EXTRA_QUESTION_TYPES = ["Fact Retrieval", "Complex Reasoning", "Contextual Summarize", "Creative Generation"]
GEMINI_FILE_SEARCH_STORE = "fileSearchStores/graphragbench-9lax22b99qlk"

# Role and Goal sections of SYSTEM_PROMPT in GraphRAG-Bench Examples/run_lightrag.py.
# Every system in the comparison must use this same text.
SYSTEM_PROMPT = """---Role---
You are a helpful assistant responding to user queries.

---Goal---
Generate direct and concise answers based strictly on the provided Knowledge Base.
Respond in plain text without explanations or formatting.
Maintain conversation continuity and use the same language as the query.
If the answer is unknown, respond with "I don't know"."""


def question_key(q):
    # One id in novel_questions.json is used by two different novels.
    return f"{q['source']}::{q['id']}"


def select_questions(questions, subset, sample):
    """Keep one subset; with sample > 0, keep the first `sample` questions of each source."""
    questions = [q for q in questions if q["source"].lower().startswith(subset)]
    if not sample:
        return questions
    per_source = {}
    for q in questions:
        group = per_source.setdefault(q["source"], [])
        if len(group) < sample:
            group.append(q)
    return [q for group in per_source.values() for q in group]


def prediction(q, answer, contexts):
    """One item of predictions.json, in the format that Evaluation/generation_eval.py reads.

    The pipeline needs the keys generated_answer and context in every profile.
    """
    return {
        "id": q["id"],
        "question": q["question"],
        "source": q["source"],
        "context": contexts,
        "evidence": q["evidence"],
        "question_type": q["question_type"],
        "generated_answer": answer,
        "ground_truth": q["answer"],
    }

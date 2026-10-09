"""QASPER profile: the benchmark-specific part of the pipeline.

pipeline/bench_common.py imports this module (as `bc.profile`) when ./bench runs with
`qasper`. See the README.md in the hub root for the contract.

Only the pilot is prepared (make_pilot.py): QUESTION_FILES and CORPUS_FILE point to the
pilot question file and the corpus slice, so a full run cannot start by mistake.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
TITLE = "QASPER"
RESOURCE_NAME = "qasper-test-pilot"
RESOURCE_DESCRIPTION = "QASPER v0.3 test, pilot corpus slice (64 papers), benchmark only"

# The official test release, extracted unchanged. It is a tarball, not a git repository,
# so the archive hash identifies the version.
UPSTREAM_REPO = HERE / "upstream"
UPSTREAM_URL = "https://qasper-dataset.s3.us-west-2.amazonaws.com/qasper-test-and-evaluator-v0.3.tgz"
UPSTREAM_SHA256 = "72a52a41193e2838b8074f80ac074b94f956b84886c36a61c58a7df4171bdd72"
OFFICIAL_TEST = UPSTREAM_REPO / "qasper-test-v0.3.json"
OFFICIAL_EVALUATOR = UPSTREAM_REPO / "qasper_evaluator.py"

SUBSETS = ["test"]
QUESTION_FILES = {"test": HERE / "data" / "pilot_questions.json"}
GOLD_FILE = HERE / "data" / "pilot_gold.json"
CORPUS_FILE = HERE / "data" / "corpus_slice.txt"
SOURCE = RESOURCE_NAME
GEMINI_FILE_SEARCH_STORE = "fileSearchStores/qaspertestpilot-jva5no5yqkow"  # systems/setup_gemini.py

# Answer forms of the QASPER references (paper section 4.2): extractive spans joined with
# commas, a free-form answer, "Yes", "No" or "Unanswerable". Every system uses this text.
SYSTEM_PROMPT = """Answer the question with information from the knowledge base only.
Give only the answer, with no explanation and no formatting:
- a short phrase or sentence, or the words from the paper; separate several items with commas;
- for a yes/no question, only "Yes" or "No";
- if the paper does not answer the question, only "Unanswerable"."""


def query(title, question):
    return f'In the paper "{title}": {question}'


def question_key(q):
    return q["id"]


def select_questions(questions, subset, sample):
    return questions[:sample] if sample else questions


def prediction(q, answer, contexts):
    """One item of predictions.json; score.py converts it to the evaluator's JSONL."""
    return {
        "question_id": q["id"],
        "paper_id": q["paper_id"],
        "question": q["question"],
        "answer_type": q["answer_type"],
        "context": contexts,
        "generated_answer": answer,
    }

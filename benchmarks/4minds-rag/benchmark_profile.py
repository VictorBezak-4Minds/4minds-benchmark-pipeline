"""4Minds RAG profile: our own scorers on the saved answers of the EnterpriseRAG-Bench pilot.

pipeline/bench_common.py imports this module (as `bc.profile`) when ./bench runs with
`4minds-rag`. See the README.md in the hub root for the contract.

No system answers in this benchmark. A run links the answers of an EnterpriseRAG-Bench run
(pipeline/derive_run.py --from ../enterpriserag-bench/runs/<run>), and pipeline/score_extra.py
scores them with the configs in configs/scorers/. The questions, gold answers, gold facts, gold
documents and corpus are the EnterpriseRAG-Bench pilot files, read in place (no copies).
"""
import ast
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ERAG_DIR = HERE.parent / "enterpriserag-bench"
_spec = importlib.util.spec_from_file_location("erag_benchmark_profile", ERAG_DIR / "benchmark_profile.py")
erag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(erag)

TITLE = "4Minds RAG"
RESOURCE_NAME = erag.RESOURCE_NAME
RESOURCE_DESCRIPTION = erag.RESOURCE_DESCRIPTION
SOURCE_BENCHMARK = "enterpriserag-bench"
SOURCE_UPSTREAM_COMMIT = erag.UPSTREAM_COMMIT

SUBSETS = ["all"]
QUESTION_FILES = {"all": ERAG_DIR / "data" / "pilot_questions.json"}
PILOT_MANIFEST = ERAG_DIR / "data" / "pilot_manifest.json"
CORPUS_FILE = erag.CORPUS_FILE
# The answer prompt that the systems of the source run used.
SYSTEM_PROMPT = erag.SYSTEM_PROMPT
question_key = erag.question_key
select_questions = erag.select_questions
prediction = erag.prediction
corpus_documents = erag.corpus_documents

# question_type values that a pipeline/score_extra.py config can select.
EXTRA_QUESTION_TYPES = ["basic", "semantic", "intra_document_reasoning", "project_related", "constrained",
                        "conflicting_info", "completeness", "miscellaneous", "info_not_found", "high_level"]


def _as_list(value):
    """A list field; the official questions.jsonl keeps some lists as Python list strings ("['a', 'b']")."""
    if isinstance(value, list):
        return value
    return list(ast.literal_eval(value)) if value else []


def extra_rows(predictions, questions_file=None):
    """The pipeline/score_extra.py rows: each saved answer with its gold answer (ground_truth), its
    gold facts (evidence) and its gold document IDs. Answers to questions outside the file are left out."""
    questions = {q["question_id"]: q for q in
                 json.loads(Path(questions_file or QUESTION_FILES["all"]).read_text())}
    rows = []
    for p in predictions:
        q = questions.get(p["question_id"])
        if q is None:
            continue
        rows.append({"id": q["question_id"], "question": q["question"], "question_type": q["question_type"],
                     "generated_answer": p["generated_answer"], "ground_truth": q["gold_answer"],
                     "evidence": _as_list(q["answer_facts"]), "gold_document_ids": _as_list(q["expected_doc_ids"]),
                     "document_ids": list(p.get("document_ids") or [])})
    return rows

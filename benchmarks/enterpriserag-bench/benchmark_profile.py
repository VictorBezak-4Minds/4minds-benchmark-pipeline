"""EnterpriseRAG-Bench profile: the benchmark-specific part of the pipeline.

pipeline/bench_common.py imports this module (as `bc.profile`) when ./bench runs with
`enterpriserag-bench`. See the README.md in the hub root for the contract.

The corpus is many documents, not one file: CORPUS_FILE is a document list (dsid and path
under upstream/generated_data/sources/), and corpus_documents() gives the text of each
document as the official answer-generation code makes it ("<title>\\n\\n<content>").
Each prediction carries the IDs of the retrieved documents (`document_ids`), because the
official scorer measures document recall and invalid extra documents.
"""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TITLE = "EnterpriseRAG-Bench"
RESOURCE_NAME = "enterpriserag-bench-pilot"
RESOURCE_DESCRIPTION = "EnterpriseRAG-Bench (commit d36685e), pilot corpus slice, benchmark only"

UPSTREAM_REPO = HERE / "upstream"
UPSTREAM_URL = "https://github.com/onyx-dot-app/EnterpriseRAG-Bench"
UPSTREAM_COMMIT = "d36685e273713975ee20299bbf1ab64165575b3c"
# The leaderboard Space: only its transform_raw_data.py is used (aggregate.py).
LEADERBOARD_REPO = HERE / "leaderboard_upstream"
LEADERBOARD_URL = "https://huggingface.co/spaces/onyx-dot-app/EnterpriseRAG-Bench-Leaderboard"
LEADERBOARD_COMMIT = "85b78cb52cbcddbfe462dde6b0e68a2a29739613"

OFFICIAL_QUESTIONS = UPSTREAM_REPO / "questions.jsonl"
SOURCES_DIR = UPSTREAM_REPO / "generated_data" / "sources"
UUID_INDEX = UPSTREAM_REPO / "generated_data" / "uuid_index.json"

SUBSETS = ["all"]
# make_pilot.py writes these: all 500 official questions as a JSON array (bench_common reads
# JSON), and the document list of the pilot slice.
QUESTION_FILES = {"all": HERE / "data" / "questions.json"}
CORPUS_FILE = HERE / "data" / "pilot_corpus.json"


def _load_upstream(relative, name):
    spec = importlib.util.spec_from_file_location(name, UPSTREAM_REPO / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The official answer prompt of the vector and BM25 baselines (one user message).
ANSWER_GEN_PROMPT = _load_upstream("src/prompts/vector_search_answer_gen.py", "erb_answer_prompt").ANSWER_GEN_PROMPT
_INSTRUCTIONS = ANSWER_GEN_PROMPT.split("## Context Documents")[0].strip()
_OUTPUT_RULE = ANSWER_GEN_PROMPT.split("## Answer")[1].strip()
# For systems that take a system prompt (LightRAG) or a persona (4Minds): the same official
# instruction text, without the document and question slots.
SYSTEM_PROMPT = f"{_INSTRUCTIONS}\n\n{_OUTPUT_RULE}"
PROMPT_LAYOUT = "user: official ANSWER_GEN_PROMPT with context_documents and question (no system message)"


def messages(q, contexts):
    """The request of systems/run_rag.py: the official prompt, with the retrieved documents
    joined as the official format_context_documents() joins them (empty for no retrieval)."""
    prompt = ANSWER_GEN_PROMPT.format(context_documents="\n\n".join(contexts), question=q["question"])
    return [{"role": "user", "content": prompt}]


def question_key(q):
    return q["question_id"]


def select_questions(questions, subset, sample):
    """--sample N: the first N questions of each question type."""
    if not sample:
        return questions
    counts, out = {}, []
    for q in questions:
        counts[q["question_type"]] = counts.get(q["question_type"], 0) + 1
        if counts[q["question_type"]] <= sample:
            out.append(q)
    return out


def prediction(q, answer, contexts, document_ids=None):
    """One item of predictions.json; score.py writes the official answers.jsonl from it."""
    return {
        "question_id": q["question_id"],
        "question_type": q["question_type"],
        "question": q["question"],
        "context": contexts,
        "generated_answer": answer,
        "document_ids": list(document_ids or []),
    }


_document_content = None


def document(dsid, path):
    """One corpus document: title and content from the official extract_document_content()."""
    global _document_content
    if _document_content is None:
        _document_content = _load_upstream("src/utils/document_content.py", "erb_document_content")
    data = json.loads((SOURCES_DIR / path).read_text())
    title, content = _document_content.extract_document_content(data)
    return {"dsid": dsid, "path": path, "title": title, "content": content, "text": f"{title}\n\n{content}"}


def corpus_documents(corpus_file=None):
    """Every document of the corpus list, in list order."""
    entries = json.loads(Path(corpus_file or CORPUS_FILE).read_text())["documents"]
    return [document(e["dsid"], e["path"]) for e in entries]


def format_context_document(i, doc):
    """The official format_context_documents() layout for document i (1-based)."""
    return f"--- Document {i} (ID: {doc['dsid']}) ---\nTitle: {doc['title']}\n\n{doc['content']}"

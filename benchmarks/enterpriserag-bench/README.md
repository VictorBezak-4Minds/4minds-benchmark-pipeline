# EnterpriseRAG-Bench (metrics-based pilot)

EnterpriseRAG-Bench ([Onyx](https://github.com/onyx-dot-app/EnterpriseRAG-Bench)) has 500
questions about a synthetic company. The corpus is about 500,000 documents from 9 sources
(Slack, Gmail, Linear, Google Drive, HubSpot, Fireflies, GitHub, Jira, Confluence). Each
question has a gold answer, a list of facts and a list of gold documents. The public
[leaderboard](https://huggingface.co/spaces/onyx-dot-app/EnterpriseRAG-Bench-Leaderboard) shows
one row per system.

**Status:** pilot scored for 4 systems (50 questions, a 10,000-document corpus slice); Microsoft
GraphRAG was added on 2026-10-11 (index: 7.1 h, USD 32.22). LightRAG was removed on 2026-10-10: its
index would cost about USD 97 for the slice and about USD 4,950 for the full corpus (the `delete`
event in `audit/audit.log` has the measurements). RAGFlow is left out for now (its Docker images
are amd64 only). A full run is not approved.

## Protocol

We use only the official **metrics-based evaluation** (`upstream/src/scripts/answer_evaluation/metrics_based_eval.py`)
with its default settings, as the leaderboard does. We do not use the comparative evaluation.
Each system is scored alone.

1. **Ingest.** Each system gets the same documents (`data/pilot_corpus.json`). The text of a
   document is the official `extract_document_content()` output: `title`, a blank line, `content`.
2. **Query.** Each system answers with the official answer prompt
   (`upstream/src/prompts/vector_search_answer_gen.py`, `ANSWER_GEN_PROMPT`). The prompt has the context
   documents and the question in one user message (`benchmark_profile.messages()`). A system that
   builds its own context (4Minds) gets the same instructions as a system prompt
   (`benchmark_profile.SYSTEM_PROMPT`).
3. **Document IDs.** Each answer has the IDs of the documents that the system retrieved
   (`document_ids`). The scorer uses them for recall and for invalid extra documents.
4. **Score.** `scripts/score.py` runs `metrics_based_eval.main()` unchanged, with the official
   judge (gpt-5.4, and gpt-5-mini for the citation step). Default settings: the judge removes
   citations, then 3 judges check if the retrieved documents that are not gold also answer the
   question (correction; the corrected gold list goes to `questions_updated.jsonl`), then
   correctness (the whole answer), completeness (the facts), recall and invalid extra documents.
5. **Leaderboard bundle.** `scripts/aggregate.py` writes the files of the leaderboard Space for
   each system (`answers_<key>.jsonl`, `results_<key>.json`, `questions_updated_<key>.jsonl`,
   `systems.yaml`) and runs the Space's own `transform_raw_data.py` to make `leaderboard.csv`.

Overall score (the leaderboard column) = the mean over the questions of completeness when the
answer is correct, and 0 when it is not.

### Pilot sample (`scripts/make_pilot.py`, seed 42)

- 50 of the 500 questions, stratified by question type: basic 17, semantic 12,
  intra_document_reasoning 4, project_related 4, constrained 3, conflicting_info 2,
  completeness 2, miscellaneous 2, info_not_found 2, high_level 2. 4 questions have no gold
  documents.
- Corpus slice: the 74 gold documents of the 50 questions, plus 9,926 random other documents
  (10,000 documents, 48.9 M characters, about 12.0 M tokens). By source: Slack 5,549,
  Gmail 2,361, Linear 689, Google Drive 490, HubSpot 297, Fireflies 199, GitHub 159, Jira 133,
  Confluence 123.
- `data/questions.json` has all 500 official questions in the hub format; `data/pilot_questions.json`
  has the 50 pilot questions; `data/pilot_manifest.json` has the counts and the sha256 values.

### Systems

| Key | System | Retrieval |
|---|---|---|
| `gptoss_no_rag` | GPT-OSS-120B, no retrieval | none (world knowledge baseline) |
| `gptoss_langchain` | GPT-OSS-120B + LangChain vector RAG | a copy of the official vector baseline: 512-token chunks with 10% overlap, text-embedding-3-large, FAISS, 100 chunks, the top 10 documents in full |
| `gptoss_graphrag` | GPT-OSS-120B + Microsoft GraphRAG | GraphRAG 3.3.0, fast method, default settings (1,200-token chunks, noun-phrase graph, community reports by GPT-OSS-120B), text-embedding-3-large; the context of GraphRAG local search (community level 2) in the official prompt |
| `gptoss_ragflow` | GPT-OSS-120B + RAGFlow (setup in progress) | self-hosted RAGFlow v0.27.2, default dataset settings (General chunk method, 512 tokens), text-embedding-3-large; the retrieval of a default RAGFlow chat assistant (6 chunks, hybrid keyword + vector search with vector weight 0.3, similarity threshold 0.2, no reranker), each chunk in the official document layout of the official prompt |
| `4minds` | 4Minds (GPT-OSS-120B + Constellation) | 4Minds prod; one file per document (`<dsid>_<title>.txt`; the runner reads the dsid back from the chunk `document_title`) |

All answers come from GPT-OSS-120B on Amazon Bedrock (`pipeline/llm_backends.json`,
`bedrock-gpt-oss-120b`), except 4Minds, which uses its own GPT-OSS-120B.

## Layout

The same layout as every benchmark in the hub (see the hub README): find the run in
[runs/README.md](runs/README.md), then open the run's `README.md`.

| Folder or file | Content |
|---|---|
| `upstream/` | the official repo at `UPSTREAM_COMMIT`, never edited (about 7.6 GB with the corpus) |
| `leaderboard_upstream/` | the leaderboard Space at `LEADERBOARD_COMMIT` (only `transform_raw_data.py` is used) |
| `benchmark_profile.py` | profile for the hub pipeline: prompt, corpus documents, prediction format |
| `data/` | all questions, the pilot questions, the corpus slice, the pilot manifest |
| `shared/` | `langchain/` (FAISS index), `graphrag/` (GraphRAG index; `_first20` and `_first500` are tests), `4minds/` (setup state), the scorer's uuid index |
| `scripts/check_graphrag_retriever.py` | searches a GraphRAG index (also a test index) for a few questions, without answers |
| `scripts/make_pilot.py` | makes the pilot questions and the corpus slice |
| `scripts/score.py` | runs the official metrics-based evaluation for one system folder |
| `scripts/aggregate.py` | the leaderboard bundle, `leaderboard.csv`, `summary/scores.json`, `summary/report.md` |
| `scripts/make_report.py` | `summary/report.html` |
| `configs/comparisons/` | the systems of a comparison (see Commands) |

## Commands

```
./bench enterpriserag-bench make_pilot erag make_pilot.py
./bench enterpriserag-bench setup_langchain erag systems/setup_langchain.py
./bench enterpriserag-bench setup_graphrag graphrag systems/setup_graphrag.py [--limit 500] [--dry-run]
./bench enterpriserag-bench setup_4minds eval systems/setup_4minds.py
./bench enterpriserag-bench setup_ragflow eval systems/setup_ragflow.py --base-url http://<ragflow host>:9380 [--dry-run]
./bench enterpriserag-bench pilot_ragflow erag systems/run_rag.py --retriever ragflow \
    --llm bedrock-gpt-oss-120b --subset all --questions-file data/pilot_questions.json --out-dir runs/<run>/gptoss_ragflow
./bench enterpriserag-bench pilot_no_rag erag systems/run_rag.py --retriever none --llm bedrock-gpt-oss-120b \
    --subset all --questions-file data/pilot_questions.json --out-dir runs/<run>/gptoss_no_rag
./bench enterpriserag-bench pilot_langchain erag systems/run_rag.py --retriever langchain_vector --top-k 10 \
    --llm bedrock-gpt-oss-120b --subset all --questions-file data/pilot_questions.json --out-dir runs/<run>/gptoss_langchain
./bench enterpriserag-bench pilot_graphrag graphrag systems/run_rag.py --retriever graphrag_local \
    --llm bedrock-gpt-oss-120b --subset all --questions-file data/pilot_questions.json --out-dir runs/<run>/gptoss_graphrag
./bench enterpriserag-bench pilot_4minds eval systems/run_4minds.py --engine constellations --workers 4 \
    --subset all --questions-file data/pilot_questions.json --out-dir runs/<run>/4minds
./bench enterpriserag-bench score_<system> erag score.py --system-dir runs/<run>/<system>/all
./bench enterpriserag-bench aggregate erag aggregate.py --matrix configs/comparisons/gptoss_pilot.json --run runs/<run>
./bench enterpriserag-bench report eval make_report.py --run runs/<run>
```

The comparison file (`configs/comparisons/*.json`) has the systems: folder, leaderboard name and
tags, color, description, ingestion file and caveats. `aggregate.py` and `make_report.py` read it;
do not put system names in the scripts.

The environment `erag` is `envs/.venv-erag` (the upstream requirements and LangChain).
The environment `graphrag` is `envs/.venv-graphrag` (Python 3.11, `graphrag==3.3.0`).
Run long steps in a terminal that stays open. Do not use `./bench --bg` from an agent shell
(see the hub README).

## Caveats

- **Corpus slice.** The official runs search all 500,000 documents. The slice has 10,000, so
  retrieval is easier. Do not compare pilot scores with the leaderboard as equals.
- **Pilot size.** 50 questions. The judge is not fully repeatable. Do not rank systems from
  the pilot.
- **Correction changes the gold list.** With the default settings, a retrieved document that is
  not gold can become gold for that system (3 judges agree). Recall and invalid extra documents
  then use a gold list that is different for each system. The leaderboard uses the same default.
- **Vector baseline.** The official README says 1,024-token chunks; the code uses 512 tokens with
  10% overlap. We follow the code.
- **4Minds** uses the official instructions as a system prompt (its persona), not the official
  user-message layout, because it builds the context itself.
- **GraphRAG with GPT-OSS on Bedrock.** Bedrock's JSON mode often puts a `{` in front of the
  model's own JSON object, and some replies have raw tabs in strings. `systems/graphrag_hooks.py`
  repairs these in memory (`audit/patches/graphrag-3.3.0-gptoss-json-repair.py`). Replies that
  stay invalid lose their community report (1.2% in the 500-document test); `index_manifest.json`
  has the count (`reports_missing`).

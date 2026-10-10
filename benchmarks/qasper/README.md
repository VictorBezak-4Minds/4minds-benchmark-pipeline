# QASPER (answer-only pilot)

QASPER ([Dasigi et al., 2021](https://arxiv.org/abs/2105.03011)) has questions about NLP papers.
NLP researchers wrote the questions from the title and abstract only. Other researchers answered
them from the full text. We use the official v0.3 test release and the official evaluator.

**Status:** pilot complete for 4 of 5 systems (25 questions, 2026-10-09). RAG Engine is blocked
(see "Findings"). A full run is not approved.

## Protocol

1. **Ingest.** Each system gets the same corpus slice (`data/corpus_slice.txt`).
2. **Query.** Each system answers the 25 pilot questions with its own retrieval and the same
   system prompt (`benchmark_profile.SYSTEM_PROMPT`).
3. **Score.** The official evaluator gives Answer F1 (SQuAD token F1, the maximum over the
   references). We score the answers only. We do not score retrieval.

### Pilot sample (`make_pilot.py`, seed 42)

- 25 questions, 1 question for each paper. Stratified by the majority answer type of the question:
  13 extractive, 6 abstractive, 3 yes/no, 3 unanswerable.
- Corpus slice: the 25 papers of the questions, plus 10% of the other 391 test papers (39 papers).
  Total 64 of 416 papers, 1.57 M characters.
- Each paper is rendered as text: title, abstract, sections and paragraphs, and figure and
  table captions.
- `data/pilot_gold.json` has only the 25 pilot papers and questions. The official evaluator gives 0
  to a missing prediction, so the gold file must not contain more questions.

### Deviation from the paper

In the paper, the model gets the question and the one paper that the question is about. There
is no search in a corpus. In our setting, all 64 papers are in one knowledge base. Thus each
query names its paper:

```
In the paper "<title>": <question>
```

The original question is in the field `original_question`.

## Layout

The same layout as every benchmark in the hub (see the hub README): find the run in
[runs/README.md](runs/README.md), then open the run's `README.md`.

| Folder or file | Content |
|---|---|
| `upstream/` | the official tgz, extracted, read-only (sha256 in `benchmark_profile.UPSTREAM_SHA256`) |
| `benchmark_profile.py` | profile for the hub pipeline |
| `data/` | the pilot questions, the gold subset, the corpus slice |
| `runs/2026-10-09_pilot/` | the pilot: a folder per system (`<system>/test/`), `summary/` (report), `blocked.json` (the reason for each system that is not scored), `_superseded_rag_engine_blocked/` |
| `shared/` | `4minds/`, `gemini/`, `rag_engine/` (`setup.json`: the external resources that setup made), `lightrag/` (the index) |
| `audit/` | `audit.log`, step logs, `moves/` (maps of earlier folder names) |
| `scripts/make_pilot.py` | makes the pilot questions, the gold subset, the corpus slice and `data/pilot_manifest.json` |
| `scripts/score.py` | runs the official evaluator unchanged, writes `per_question.jsonl`, checks that the means are the same as the official values |
| `scripts/aggregate.py` | Answer F1 overall and by type, bootstrap 95% CI, answer length → `summary/`, run README |
| `scripts/make_report.py` | `summary/report.html` in the 4Minds style, from `scores.json` (shared style: `pipeline/report_html.py`) |

## Commands

```
./bench qasper make_pilot eval make_pilot.py
./bench qasper setup_4minds eval systems/setup_4minds.py
./bench qasper setup_gemini eval systems/setup_gemini.py
./bench qasper lightrag_index lightrag systems/run_lightrag.py --subset test --index-only
./bench qasper pilot_gemini eval systems/run_gemini.py --subset test \
    --questions-file data/pilot_questions.json --timeout 120 --out-dir runs/2026-10-09_pilot/gemini --workers 10
./bench qasper pilot_4minds_constellations eval systems/run_4minds.py --engine constellations --subset test \
    --questions-file data/pilot_questions.json --workers 4 --out-dir runs/2026-10-09_pilot/4minds_constellations
./bench qasper pilot_4minds_symi eval systems/run_4minds.py --engine symi --subset test \
    --questions-file data/pilot_questions.json --workers 4 --out-dir runs/2026-10-09_pilot/4minds_symi
./bench qasper pilot_lightrag lightrag systems/run_lightrag.py --subset test \
    --questions-file data/pilot_questions.json --out-dir runs/2026-10-09_pilot/lightrag --workers 4
./bench qasper score_pilot_gemini eval score.py --system-dir runs/2026-10-09_pilot/gemini/test
./bench qasper aggregate_pilot eval aggregate.py --run runs/2026-10-09_pilot
./bench qasper report_pilot eval make_report.py --run runs/2026-10-09_pilot
```

Run long steps in a terminal that stays open. Do not use `./bench --bg` from an agent shell (see
the hub README).

## Pilot results (Answer F1, 25 questions)

Report: `runs/2026-10-09_pilot/summary/report.html` (Markdown version: `report.md`).

| System | Answer F1 (95% CI) | Median answer words | Median latency | Query cost |
|---|---|---|---|---|
| Gemini + File Search | 72.6 (57.5–86.4) | 1 | 30.5 s | $2.62 |
| LightRAG + Gemini | 66.0 (49.7–81.0) | 2 | 9.4 s | $0.19 |
| 4Minds (SYMI) | 52.8 (37.1–68.7) | 7 | 9.4 s | — |
| 4Minds (Constellations) | 48.9 (32.9–65.3) | 4 | 9.7 s | — |
| Gemini + RAG Engine | blocked | | | |

The confidence intervals overlap. Do not rank the systems from 25 questions.

### Ingestion

| System | Time | Cost |
|---|---|---|
| 4Minds | about 1 s (the graph is chunk-level: 330 nodes) | — |
| Gemini File Search | 35 s | storage only |
| LightRAG | 974 s with max_async 16 (594 LLM calls; 3,496 entities, 5,459 relationships) | $3.95 |
| RAG Engine | 36 s, but queries failed | Spanner Basic, every hour |

## Findings

- **Gemini File Search is agentic.** It made a median of 5 searches per question (maximum 17),
  and used 3.28 M tool tokens for 25 questions. A full run (1,451 questions) costs about $150.
  14 answers have no citations (short answers).
- **4Minds finds the paper.** Constellations retrieved a chunk of the named paper for 25 of 25
  questions. The difference in score comes from the answer generation, not from retrieval.
  (This is a diagnostic only. It is not a metric.)
- **RAG Engine is blocked.** Vertex RAG Engine (europe-west4, Spanner Basic) returned HTTP 500
  "Failed to fetch corpus status from spanner". The corpora and the config were ACTIVE in
  the control plane. We tried 3 new corpora, also after a tier cycle (unprovisioned, then basic).
  Retrieval passed 2 of 20 tests. The partial output (4 answered, 8 failed) is in
  `runs/2026-10-09_pilot/_superseded_rag_engine_blocked`. Spanner is unprovisioned again.
  Lesson: before a run, send one real query; "ACTIVE" does not prove that queries work.
- **The prompt controls answer length.** Answer F1 is token overlap, so long answers get low
  scores. All systems now give short answers (median 1 to 7 words).

## Caveats

See `aggregate.CAVEATS` (also printed in the report): the pilot size, the deviation above, the
corpus slice, captions only for tables and figures, and papers that are probably in the
training data.

## Cloud resources

| Resource | Cost while not in use |
|---|---|
| 4Minds dataset 4039, model 3598, persona 1283 (prod) | none |
| Gemini File Search store `qaspertestpilot-jva5no5yqkow` | storage only |
| LightRAG index `shared/lightrag/workspace/qasper-test-pilot/` | none (local) |

# QASPER PILOT: Answer F1

Official evaluator `qasper_evaluator.py` (v0.3 test release), 10000 bootstrap resamples, seed 0.

| System | Answer F1 (95% CI) | Extractive | Abstractive | Yes/No | Unanswerable | Median answer words | Median latency |
|---|---|---|---|---|---|---|---|
| Gemini + File Search | 72.6 (57.5–86.4) | 70.0 (n=14) | 33.8 (n=4) | 100.0 (n=3) | 100.0 (n=4) | 1 | 30.53 s |
| LightRAG + Gemini | 66.0 (49.7–81.0) | 62.8 (n=15) | 36.0 (n=3) | 66.7 (n=3) | 100.0 (n=4) | 2 | 9.4 s |
| 4Minds (SYMI) | 52.8 (37.1–68.7) | 49.6 (n=14) | 31.0 (n=4) | 75.0 (n=4) | 66.7 (n=3) | 7 | 9.4 s |
| 4Minds (Constellations) | 48.9 (32.9–65.3) | 43.0 (n=13) | 32.6 (n=5) | 66.7 (n=3) | 75.0 (n=4) | 4 | 9.68 s |

## Not scored

- Gemini + RAG Engine: blocked. Vertex RAG Engine (europe-west4, Spanner Basic) returned HTTP 500 "Failed to fetch corpus status from spanner" on 3 new corpora, also after a tier cycle. Retrieval passed 2 of 20 tests. Partial output: results/pilot/_superseded_rag_engine_blocked.

## Caveats

- Pilot: 25 questions. The confidence intervals are wide and overlap; do not rank systems from this table.
- Deviation from the paper's setting: all corpus papers are in one knowledge base, and each query names its paper (In the paper "<title>": <question>). The paper's model receives the question plus that one paper.
- The corpus is a slice: the 25 question papers plus 39 other test papers (64 of 416).
- Tables and figures are available only as captions (no images).
- The papers are from before 2021 and are probably in the training data of the models.
- Answer F1 is token overlap with the best-matching reference, so long answers get low scores even when they are correct. Compare the answer length column.
- By-type scores use the type of the best-matching reference (official rule); some questions have references of more than one type.
- Only Answer F1 is reported. Evidence F1 is not used (predicted_evidence is empty).

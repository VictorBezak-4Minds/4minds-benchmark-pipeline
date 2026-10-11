# 4Minds RAG PILOT: v1_gpt-4o-mini

4Minds RAG v1: RAGAS Answer Accuracy and Factual Correctness, DeepEval Summarization and Hallucination against the gold answer and gold facts, and document retrieval precision, recall and F1 against the gold documents. Judge: gpt-4o-mini.

Judge: `openai-gpt-4o-mini`. Scores are 0 to 1, higher is better. 95% CI: 2000 bootstrap resamples over the questions, seed 7.

## Headline metrics

| System | Answer Accuracy (RAGAS, NVIDIA) | Factual Correctness (RAGAS): f1 | Summarization (DeepEval) | Hallucination (DeepEval; higher is better) | Document retrieval (no judge): f1 |
|---|---|---|---|---|---|
| GPT-OSS + RAGFlow | 0.460 (0.40–0.53) | 0.510 (0.42–0.60) | 0.407 (0.31–0.50) | 0.634 (0.53–0.74) | 0.377 (0.31–0.45) |
| GPT-OSS + LangChain | 0.455 (0.37–0.55) | 0.503 (0.41–0.60) | 0.405 (0.32–0.50) | 0.666 (0.55–0.78) | 0.203 (0.16–0.25) |
| 4Minds (Constellations) | 0.390 (0.32–0.47) | 0.472 (0.37–0.57) | 0.468 (0.37–0.57) | 0.655 (0.54–0.77) | 0.165 (0.12–0.21) |
| GPT-OSS + GraphRAG | 0.090 (0.04–0.15) | 0.170 (0.11–0.24) | 0.087 (0.04–0.13) | 0.284 (0.18–0.40) | 0.016 (0.00–0.04) |
| GPT-OSS, no RAG | 0.061 (0.02–0.11) | 0.082 (0.04–0.13) | 0.041 (0.01–0.09) | 0.204 (0.11–0.31) | 0.000 (0.00–0.00) |

## All metric outputs

| Metric | GPT-OSS + RAGFlow | GPT-OSS + LangChain | 4Minds (Constellations) | GPT-OSS + GraphRAG | GPT-OSS, no RAG |
|---|---|---|---|---|---|
| Answer Accuracy (RAGAS, NVIDIA) | 0.460 (n=50) | 0.455 (n=50) | 0.390 (n=50) | 0.090 (n=50) | 0.061 (n=49) |
| Factual Correctness (RAGAS): precision | 0.582 (n=50) | 0.544 (n=50) | 0.439 (n=50) | 0.223 (n=50) | 0.150 (n=49) |
| Factual Correctness (RAGAS): recall | 0.512 (n=50) | 0.527 (n=50) | 0.577 (n=50) | 0.156 (n=50) | 0.060 (n=49) |
| Factual Correctness (RAGAS): f1 | 0.510 (n=50) | 0.503 (n=50) | 0.472 (n=50) | 0.170 (n=50) | 0.082 (n=49) |
| Summarization (DeepEval) | 0.407 (n=50) | 0.405 (n=50) | 0.468 (n=50) | 0.087 (n=50) | 0.041 (n=49) |
| Summarization (DeepEval): alignment | 0.594 (n=50) | 0.594 (n=50) | 0.531 (n=50) | 0.178 (n=50) | 0.085 (n=49) |
| Summarization (DeepEval): coverage | 0.546 (n=50) | 0.559 (n=50) | 0.687 (n=50) | 0.163 (n=50) | 0.100 (n=49) |
| Hallucination (DeepEval; higher is better) | 0.634 (n=50) | 0.666 (n=50) | 0.655 (n=50) | 0.284 (n=50) | 0.204 (n=49) |
| Document retrieval (no judge): precision | 0.290 (n=46) | 0.126 (n=46) | 0.101 (n=46) | 0.018 (n=46) | 0.000 (n=45) |
| Document retrieval (no judge): recall | 0.831 (n=46) | 0.821 (n=46) | 0.715 (n=46) | 0.032 (n=46) | 0.000 (n=45) |
| Document retrieval (no judge): f1 | 0.377 (n=46) | 0.203 (n=46) | 0.165 (n=46) | 0.016 (n=46) | 0.000 (n=45) |

## Answer Accuracy (RAGAS, NVIDIA) by question type

| System | basic | completeness | conflicting_info | constrained | high_level | info_not_found | intra_document_reasoning | miscellaneous | project_related | semantic |
|---|---|---|---|---|---|---|---|---|---|---|
| GPT-OSS + RAGFlow | 0.50 (n=17) | 0.50 (n=2) | 0.50 (n=2) | 0.50 (n=3) | 0.00 (n=2) | 0.50 (n=2) | 0.56 (n=4) | 0.62 (n=2) | 0.31 (n=4) | 0.44 (n=12) |
| GPT-OSS + LangChain | 0.51 (n=17) | 0.38 (n=2) | 0.25 (n=2) | 0.67 (n=3) | 0.00 (n=2) | 0.50 (n=2) | 0.69 (n=4) | 0.62 (n=2) | 0.25 (n=4) | 0.40 (n=12) |
| 4Minds (Constellations) | 0.53 (n=17) | 0.38 (n=2) | 0.25 (n=2) | 0.50 (n=3) | 0.00 (n=2) | 0.25 (n=2) | 0.62 (n=4) | 0.25 (n=2) | 0.25 (n=4) | 0.27 (n=12) |
| GPT-OSS + GraphRAG | 0.06 (n=17) | 0.00 (n=2) | 0.00 (n=2) | 0.00 (n=3) | 0.00 (n=2) | 0.62 (n=2) | 0.00 (n=4) | 0.38 (n=2) | 0.12 (n=4) | 0.08 (n=12) |
| GPT-OSS, no RAG | 0.06 (n=17) | 0.00 (n=1) | 0.00 (n=2) | 0.00 (n=3) | 0.00 (n=2) | 0.38 (n=2) | 0.00 (n=4) | 0.00 (n=2) | 0.00 (n=4) | 0.10 (n=12) |

## Factual Correctness (RAGAS): f1 by question type

| System | basic | completeness | conflicting_info | constrained | high_level | info_not_found | intra_document_reasoning | miscellaneous | project_related | semantic |
|---|---|---|---|---|---|---|---|---|---|---|
| GPT-OSS + RAGFlow | 0.46 (n=17) | 0.56 (n=2) | 0.71 (n=2) | 0.72 (n=3) | 0.20 (n=2) | 0.34 (n=2) | 0.67 (n=4) | 0.58 (n=2) | 0.69 (n=4) | 0.45 (n=12) |
| GPT-OSS + LangChain | 0.52 (n=17) | 0.34 (n=2) | 0.34 (n=2) | 0.83 (n=3) | 0.00 (n=2) | 0.40 (n=2) | 0.67 (n=4) | 0.77 (n=2) | 0.81 (n=4) | 0.36 (n=12) |
| 4Minds (Constellations) | 0.51 (n=17) | 0.74 (n=2) | 0.34 (n=2) | 0.68 (n=3) | 0.00 (n=2) | 0.00 (n=2) | 0.70 (n=4) | 0.43 (n=2) | 0.63 (n=4) | 0.38 (n=12) |
| GPT-OSS + GraphRAG | 0.16 (n=17) | 0.00 (n=2) | 0.00 (n=2) | 0.23 (n=3) | 0.00 (n=2) | 0.56 (n=2) | 0.00 (n=4) | 0.34 (n=2) | 0.41 (n=4) | 0.13 (n=12) |
| GPT-OSS, no RAG | 0.05 (n=17) | 0.06 (n=1) | 0.12 (n=2) | 0.00 (n=3) | 0.20 (n=2) | 0.25 (n=2) | 0.00 (n=4) | 0.00 (n=2) | 0.00 (n=4) | 0.16 (n=12) |

## Summarization (DeepEval) by question type

| System | basic | completeness | conflicting_info | constrained | high_level | info_not_found | intra_document_reasoning | miscellaneous | project_related | semantic |
|---|---|---|---|---|---|---|---|---|---|---|
| GPT-OSS + RAGFlow | 0.44 (n=17) | 0.65 (n=2) | 0.30 (n=2) | 0.62 (n=3) | 0.17 (n=2) | 0.30 (n=2) | 0.42 (n=4) | 0.25 (n=2) | 0.29 (n=4) | 0.40 (n=12) |
| GPT-OSS + LangChain | 0.44 (n=17) | 0.60 (n=2) | 0.10 (n=2) | 0.46 (n=3) | 0.00 (n=2) | 0.50 (n=2) | 0.45 (n=4) | 0.40 (n=2) | 0.52 (n=4) | 0.36 (n=12) |
| 4Minds (Constellations) | 0.59 (n=17) | 0.60 (n=2) | 0.30 (n=2) | 0.70 (n=3) | 0.00 (n=2) | 0.30 (n=2) | 0.75 (n=4) | 0.25 (n=2) | 0.35 (n=4) | 0.34 (n=12) |
| GPT-OSS + GraphRAG | 0.06 (n=17) | 0.02 (n=2) | 0.00 (n=2) | 0.08 (n=3) | 0.00 (n=2) | 0.50 (n=2) | 0.00 (n=4) | 0.00 (n=2) | 0.11 (n=4) | 0.13 (n=12) |
| GPT-OSS, no RAG | 0.00 (n=17) | 0.00 (n=1) | 0.00 (n=2) | 0.00 (n=3) | 0.00 (n=2) | 0.30 (n=2) | 0.00 (n=4) | 0.00 (n=2) | 0.00 (n=4) | 0.12 (n=12) |

## Hallucination (DeepEval; higher is better) by question type

| System | basic | completeness | conflicting_info | constrained | high_level | info_not_found | intra_document_reasoning | miscellaneous | project_related | semantic |
|---|---|---|---|---|---|---|---|---|---|---|
| GPT-OSS + RAGFlow | 0.67 (n=17) | 1.00 (n=2) | 0.65 (n=2) | 0.50 (n=3) | 0.17 (n=2) | 0.50 (n=2) | 0.50 (n=4) | 0.90 (n=2) | 0.50 (n=4) | 0.70 (n=12) |
| GPT-OSS + LangChain | 0.70 (n=17) | 0.96 (n=2) | 0.25 (n=2) | 0.72 (n=3) | 0.17 (n=2) | 0.50 (n=2) | 0.67 (n=4) | 1.00 (n=2) | 0.50 (n=4) | 0.74 (n=12) |
| 4Minds (Constellations) | 0.85 (n=17) | 1.00 (n=2) | 0.70 (n=2) | 0.50 (n=3) | 0.00 (n=2) | 0.00 (n=2) | 0.75 (n=4) | 0.40 (n=2) | 0.40 (n=4) | 0.67 (n=12) |
| GPT-OSS + GraphRAG | 0.33 (n=17) | 0.00 (n=2) | 0.20 (n=2) | 0.04 (n=3) | 0.17 (n=2) | 0.50 (n=2) | 0.25 (n=4) | 0.50 (n=2) | 0.25 (n=4) | 0.31 (n=12) |
| GPT-OSS, no RAG | 0.18 (n=17) | 0.00 (n=1) | 0.20 (n=2) | 0.00 (n=3) | 0.00 (n=2) | 0.50 (n=2) | 0.00 (n=4) | 0.50 (n=2) | 0.00 (n=4) | 0.38 (n=12) |

## Document retrieval (no judge): f1 by question type

| System | basic | completeness | conflicting_info | constrained | high_level | info_not_found | intra_document_reasoning | miscellaneous | project_related | semantic |
|---|---|---|---|---|---|---|---|---|---|---|
| GPT-OSS + RAGFlow | 0.30 (n=17) | 0.75 (n=2) | 0.50 (n=2) | 0.60 (n=3) | – | – | 0.30 (n=4) | 0.29 (n=2) | 0.69 (n=4) | 0.28 (n=12) |
| GPT-OSS + LangChain | 0.16 (n=17) | 0.65 (n=2) | 0.17 (n=2) | 0.28 (n=3) | – | – | 0.14 (n=4) | 0.18 (n=2) | 0.40 (n=4) | 0.14 (n=12) |
| 4Minds (Constellations) | 0.15 (n=17) | 0.65 (n=2) | 0.22 (n=2) | 0.19 (n=3) | – | – | 0.08 (n=4) | 0.10 (n=2) | 0.32 (n=4) | 0.08 (n=12) |
| GPT-OSS + GraphRAG | 0.00 (n=17) | 0.00 (n=2) | 0.00 (n=2) | 0.00 (n=3) | – | – | 0.00 (n=4) | 0.11 (n=2) | 0.13 (n=4) | 0.00 (n=12) |
| GPT-OSS, no RAG | 0.00 (n=17) | 0.00 (n=1) | 0.00 (n=2) | 0.00 (n=3) | – | – | 0.00 (n=4) | 0.00 (n=2) | 0.00 (n=4) | 0.00 (n=12) |

## Scoring

| System | Answers | Items | Not scored | Judge calls | Not JSON | Fences removed | Truncated | Judge cost |
|---|---|---|---|---|---|---|---|---|
| GPT-OSS + RAGFlow | 50 | 246 | 0 | 598 | 4 | 0 | 0 | $0.115 |
| GPT-OSS + LangChain | 50 | 246 | 0 | 598 | 6 | 0 | 0 | $0.118 |
| 4Minds (Constellations) | 50 | 246 | 0 | 600 | 9 | 0 | 0 | $0.136 |
| GPT-OSS + GraphRAG | 50 | 246 | 0 | 599 | 4 | 0 | 0 | $0.111 |
| GPT-OSS, no RAG | 49 | 241 | 0 | 585 | 0 | 0 | 0 | $0.091 |

## Not scored

- GPT-OSS, no RAG: no answer for qst_0443 (no row, not in the means)

## Caveats

- Pilot: 50 of 500 EnterpriseRAG-Bench questions, stratified by question type (2 to 17 per type), on a 10,000-document corpus slice. The judge is not fully repeatable. Do not rank systems from small differences.
- Not an official protocol: these are 4Minds RAG metrics on the saved answers of the EnterpriseRAG-Bench run. The systems did not answer again. The references are the EnterpriseRAG-Bench gold answer (Answer Accuracy, Factual Correctness), gold facts (Summarization, Hallucination) and gold documents (document retrieval).
- Summarization: the 'original text' is the gold facts of the question, not the retrieved context. The score shows how well the answer covers the gold facts (coverage) without statements that the facts do not support (alignment); score = min(alignment, coverage).
- Hallucination: DeepEval checks the answer against each gold fact. The score is the fraction of facts with the verdict 'agrees' (higher is better). The DeepEval prompt says that missing detail is not a contradiction, but the judges often give 'does not agree' to an answer that says the documents do not have the information; so a non-answer scores 0 for most questions and 1 for some (No RAG has 27 non-answers: 22 score 0 with gpt-4o-mini, 18 with Haiku). Read it together with Answer Accuracy and Factual Correctness. (The note in the scorer configs says that 'I don't know' scores 1; that is the intent of the prompt, not what the judges did.)
- Two kinds of precision, recall and F1: Factual Correctness counts claims (claims of the answer supported by the gold answer, and claims of the gold answer found in the answer; judge). Document retrieval counts document IDs (the documents the system gave against the gold documents; no judge, exact match).
- Document retrieval uses the original gold documents (no correction step, unlike the official EnterpriseRAG-Bench scorer) and only the 46 questions that have gold documents. Systems that give many documents get a lower precision.
- 4Minds: the document IDs come from the chunk document_title (file name <dsid>_<title>.txt), in chunk score order.
- LangChain: always gives 10 documents, so its document precision is at most 0.1 for a question with one gold document.
- GraphRAG: this row is not representative of GraphRAG. The fast method writes no entity descriptions, so local search compares the question only with entity names. On a 500-document test, the standard method found 52 of 74 gold documents and the fast method 17 of 74 (see the EnterpriseRAG-Bench run README).
- No RAG: the system gets no documents, so all its document scores are 0 by design. It has 49 answers; the question without an answer is not scored.

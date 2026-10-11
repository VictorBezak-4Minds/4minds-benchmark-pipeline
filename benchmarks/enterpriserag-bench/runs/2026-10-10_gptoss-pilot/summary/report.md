# EnterpriseRAG-Bench PILOT: metrics-based evaluation

Official `metrics_based_eval.py`, default settings (citation stripping, document correction), judge gpt-5.4. Overall = mean of completeness when the answer is correct, else 0 (the leaderboard column). 95% CI: 2000 bootstrap resamples, seed 7.

| System | Overall (95% CI) | Overall, missing = 0 | Correctness | Completeness | Recall | Invalid extra docs | Corrected | Scored | Judge cost |
|---|---|---|---|---|---|---|---|---|---|
| 4Minds (Constellations) | 52.94 (40.7–65.4) | 52.94 | 62.0 | 63.7 | 71.5 | 12.28 | 2 | 50/50 | $6.68 |
| GPT-OSS + LangChain | 41.69 (30.1–52.9) | 41.69 | 76.0 | 45.9 | 82.1 | 8.76 | 1 | 50/50 | $5.91 |
| GPT-OSS, no RAG | 2.55 (0.0–7.1) | 2.50 | 8.2 | 9.2 | 0.0 | 0.00 | 0 | 49/50 | $0.62 |

## Leaderboard rows (transform_raw_data.py)

| model | overall_score | correctness | completeness | recall | invalid_extra_docs | tags |
|---|---|---|---|---|---|---|
| 4Minds Constellations (GPT-OSS-120B) | 52.94 | 62.0 | 63.71 | 71.5 | 12.28 |  |
| LangChain vector (text-embedding-3-large) + GPT-OSS-120B | 41.69 | 76.0 | 45.88 | 82.13 | 8.76 | one_shot |
| GPT-OSS-120B, no retrieval | 2.55 | 8.16 | 9.22 | 0.0 | 0.0 | one_shot |

## Overall by question type

| System | basic | completeness | conflicting_info | constrained | high_level | info_not_found | intra_document_reasoning | miscellaneous | project_related | semantic |
|---|---|---|---|---|---|---|---|---|---|---|
| 4Minds (Constellations) | 68.2 (n=17) | 33.3 (n=2) | 50.0 (n=2) | 89.2 (n=3) | 0.0 (n=2) | 50.0 (n=2) | 50.0 (n=4) | 30.0 (n=2) | 35.7 (n=4) | 45.8 (n=12) |
| GPT-OSS + LangChain | 30.6 (n=17) | 22.5 (n=2) | 50.0 (n=2) | 91.4 (n=3) | 0.0 (n=2) | 100.0 (n=2) | 29.2 (n=4) | 30.0 (n=2) | 50.7 (n=4) | 47.1 (n=12) |
| GPT-OSS, no RAG | 0.0 (n=17) | 0.0 (n=1) | 0.0 (n=2) | 0.0 (n=3) | 0.0 (n=2) | 50.0 (n=2) | 0.0 (n=4) | 0.0 (n=2) | 0.0 (n=4) | 2.1 (n=12) |

## Operations

| System | Answered | Failed | No context | Docs per answer | Median latency | Answer cost |
|---|---|---|---|---|---|---|
| 4Minds (Constellations) | 50/50 | 0 | 0 | 13.22 | 14.75 s | n/a |
| GPT-OSS + LangChain | 50/50 | 0 | 0 | 10.0 | 3.5 s | $0.132 |
| GPT-OSS, no RAG | 49/50 | 1 | 49 | 0.0 | 1.76 s | $0.009 |

## Not scored

- GPT-OSS, no RAG: questions qst_0443 (not in the official averages)

## Caveats

- Pilot: 50 of 500 questions, stratified by question type (2 to 17 per type). The judge (gpt-5.4) is not fully repeatable. Do not rank systems from this table.
- Corpus slice: 10,000 of 511,958 documents (the 74 gold documents of the pilot questions plus 9,926 random others). Retrieval is easier than on the full corpus, so these scores are not comparable with the public leaderboard.
- Official default settings: a retrieved document that is not gold can become gold for that system when 3 judges agree (correction). Recall and invalid extra documents then use a different gold list for each system. The corrected-question count is in the table.
- The official scorer skips a question with no answer and no documents; that question is not in the official averages. The column 'Overall, missing = 0' counts such a question as 0 over all pilot questions.
- GPT-OSS-120B on Amazon Bedrock: temperature 0.3, 4,096 max tokens, reasoning effort medium (the 4Minds server defaults), for every system except 4Minds, which uses its own GPT-OSS-120B deployment.
- 4Minds: the document IDs come from the chunk document_title (file name <dsid>_<title>.txt), in chunk score order. The instructions of the official prompt are the persona's behavioral guidelines; 4Minds builds its own context and has no per-request system prompt, temperature or max-token setting.
- 4Minds ingestion time: setup.json counts only from the restart of the wait (21:36 UTC). The upload started at 21:22 UTC and the chunk count did not change after 21:39 UTC, so the ingestion took about 17 minutes (then 15 minutes of stable wait).
- LangChain: a copy of the official vector baseline (index_document_vectors.py and vector_retrieval.py) with LangChain parts in place of Qdrant. The official README says 1,024-token chunks; the code uses 512 tokens with 10% overlap, and we follow the code.
- No RAG: the official prompt says to answer only from the documents, and the document section is empty. The company is synthetic, so world knowledge cannot answer most questions.

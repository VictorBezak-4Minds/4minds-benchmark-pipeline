# GraphRAG-Bench Medical: generation results (PILOT)

Generated 2026-10-10T17:21:01+00:00. Scores are 0-100 with 95% bootstrap confidence intervals.

Judge `gpt-4o-mini` (gpt-4o-mini-2024-07-18), embeddings `BAAI/bge-large-en-v1.5`, GraphRAG-Bench commit `fdbab59`.

## Answer correctness, all questions

| System | Answer correctness | n |
|---|---|---|
| 4Minds (Constellations) | 75.7 [62.6, 88.3] | 10 |
| GPT-OSS + LightRAG | 71.9 [58.3, 83.6] | 10 |
| GPT-OSS + File Search | 86.8 [76.4, 93.9] | 10 |
| GPT-OSS (no RAG) | 40.3 [17.4, 63.4] | 10 |

## Fact Retrieval

| System | ROUGE-L | Answer correctness |
|---|---|---|
| 4Minds (Constellations) | 16.2 [10.7, 23.5] (n=5) | 66.5 [48.4, 84.8] (n=5) |
| GPT-OSS + LightRAG | 43.1 [28.1, 58.1] (n=5) | 79.5 [65.2, 93.8] (n=5) |
| GPT-OSS + File Search | 43.7 [30.9, 59.6] (n=5) | 88.2 [84.0, 94.0] (n=5) |
| GPT-OSS (no RAG) | 5.7 [0.0, 17.1] (n=5) | 33.4 [17.2, 65.5] (n=5) |

## Complex Reasoning

| System | ROUGE-L | Answer correctness |
|---|---|---|
| 4Minds (Constellations) | 14.5 [4.0, 25.0] (n=2) | 79.5 [60.0, 99.0] (n=2) |
| GPT-OSS + LightRAG | 21.4 [11.0, 31.7] (n=2) | 42.6 [31.3, 53.9] (n=2) |
| GPT-OSS + File Search | 30.7 [12.7, 48.8] (n=2) | 98.6 [97.9, 99.3] (n=2) |
| GPT-OSS (no RAG) | 16.0 [0.0, 32.0] (n=2) | 58.4 [18.2, 98.7] (n=2) |

## Contextual Summarize

| System | Answer correctness | Coverage |
|---|---|---|
| 4Minds (Constellations) | 98.2 [97.3, 99.0] (n=2) | 67.8 [55.6, 80.0] (n=2) |
| GPT-OSS + LightRAG | 77.2 [66.5, 88.0] (n=2) | 61.8 [61.1, 62.5] (n=2) |
| GPT-OSS + File Search | 67.5 [47.2, 87.8] (n=2) | 79.9 [72.2, 87.5] (n=2) |
| GPT-OSS (no RAG) | 51.2 [16.5, 85.9] (n=2) | 25.0 [0.0, 50.0] (n=2) |

## Creative Generation

| System | Answer correctness | Coverage | Faithfulness (official) | Faithfulness (JSON-format fix) |
|---|---|---|---|---|
| 4Minds (Constellations) | 69.5 [69.5, 69.5] (n=1) | 70.8 [70.8, 70.8] (n=1) | n/a | 64.9 [64.9, 64.9] (n=1) |
| GPT-OSS + LightRAG | 81.7 [81.7, 81.7] (n=1) | 83.3 [83.3, 83.3] (n=1) | 69.0 [69.0, 69.0] (n=1) | 27.3 [27.3, 27.3] (n=1) |
| GPT-OSS + File Search | 94.1 [94.1, 94.1] (n=1) | 79.2 [79.2, 79.2] (n=1) | n/a | 100.0 [100.0, 100.0] (n=1) |
| GPT-OSS (no RAG) | 16.6 [16.6, 16.6] (n=1) | 0.0 [0.0, 0.0] (n=1) | not available (no context) | not available (no context) |

Answers with NaN faithfulness (official / JSON-format fix): 4Minds (Constellations) 1/1 / 0; GPT-OSS + LightRAG 0/1 / 0; GPT-OSS + File Search 1/1 / 0.

## Paired differences: 4Minds (Constellations) minus each system

Positive values favor 4Minds. Same questions only.

| Compared with | Question type | Metric | Difference | n |
|---|---|---|---|---|
| GPT-OSS + LightRAG | Fact Retrieval | ROUGE-L | -26.9 [-46.3, -6.8] | 5 |
| GPT-OSS + LightRAG | Fact Retrieval | Answer correctness | -13.0 [-31.5, 6.0] | 5 |
| GPT-OSS + LightRAG | Complex Reasoning | ROUGE-L | -6.9 [-7.0, -6.7] | 2 |
| GPT-OSS + LightRAG | Complex Reasoning | Answer correctness | 36.9 [28.7, 45.1] | 2 |
| GPT-OSS + LightRAG | Contextual Summarize | Answer correctness | 21.0 [11.1, 30.9] | 2 |
| GPT-OSS + LightRAG | Contextual Summarize | Coverage | 6.0 [-5.6, 17.5] | 2 |
| GPT-OSS + LightRAG | Creative Generation | Answer correctness | -12.2 [-12.2, -12.2] | 1 |
| GPT-OSS + LightRAG | Creative Generation | Coverage | -12.5 [-12.5, -12.5] | 1 |
| GPT-OSS + LightRAG | Creative Generation | Faithfulness (JSON-format fix) | 37.6 [37.6, 37.6] | 1 |
| GPT-OSS + LightRAG | All questions | Answer correctness | 3.8 [-13.4, 20.2] | 10 |
| GPT-OSS + File Search | Fact Retrieval | ROUGE-L | -27.5 [-44.7, -11.8] | 5 |
| GPT-OSS + File Search | Fact Retrieval | Answer correctness | -21.8 [-41.8, -1.2] | 5 |
| GPT-OSS + File Search | Complex Reasoning | ROUGE-L | -16.2 [-23.8, -8.7] | 2 |
| GPT-OSS + File Search | Complex Reasoning | Answer correctness | -19.1 [-37.9, -0.3] | 2 |
| GPT-OSS + File Search | Contextual Summarize | Answer correctness | 30.7 [9.5, 51.8] | 2 |
| GPT-OSS + File Search | Contextual Summarize | Coverage | -12.1 [-16.7, -7.5] | 2 |
| GPT-OSS + File Search | Creative Generation | Answer correctness | -24.6 [-24.6, -24.6] | 1 |
| GPT-OSS + File Search | Creative Generation | Coverage | -8.3 [-8.3, -8.3] | 1 |
| GPT-OSS + File Search | Creative Generation | Faithfulness (JSON-format fix) | -35.1 [-35.1, -35.1] | 1 |
| GPT-OSS + File Search | All questions | Answer correctness | -11.0 [-28.9, 7.7] | 10 |
| GPT-OSS (no RAG) | Fact Retrieval | ROUGE-L | 10.4 [5.6, 14.3] | 5 |
| GPT-OSS (no RAG) | Fact Retrieval | Answer correctness | 33.1 [0.4, 62.3] | 5 |
| GPT-OSS (no RAG) | Complex Reasoning | ROUGE-L | -1.5 [-7.0, 4.0] | 2 |
| GPT-OSS (no RAG) | Complex Reasoning | Answer correctness | 21.1 [0.4, 41.8] | 2 |
| GPT-OSS (no RAG) | Contextual Summarize | Answer correctness | 46.9 [13.1, 80.8] | 2 |
| GPT-OSS (no RAG) | Contextual Summarize | Coverage | 42.8 [30.0, 55.6] | 2 |
| GPT-OSS (no RAG) | Creative Generation | Answer correctness | 52.9 [52.9, 52.9] | 1 |
| GPT-OSS (no RAG) | Creative Generation | Coverage | 70.8 [70.8, 70.8] | 1 |
| GPT-OSS (no RAG) | All questions | Answer correctness | 35.4 [14.4, 55.6] | 10 |

## Sensitivity check: Without incomplete File Search replies

In the full run, the File Search adapter accepted some Gemini replies with no chunks and no normal finish reason (most after about 400,000 tokens of search results) as results, and GPT-OSS answered with an empty Knowledge Base. The adapter now retries such replies. A test with 3 of these questions on 2026-10-10 passed 2 at the first attempt and failed 1 again 4 times (runs/2026-10-10_gptoss-full/tests/filesearch-fault-probe). This check takes these questions out for every system and computes answer correctness and the paired differences again.

Excluded for all systems: 0 answered questions whose retrieval returned no chunks and had no normal finish reason (MAX_TOKENS, STOP).

| System | Answer correctness, all questions | n | Paired difference | n |
|---|---|---|---|---|
| 4Minds (Constellations) | 75.7 [61.7, 88.1] | 10 | (reference) |  |
| GPT-OSS + LightRAG | 71.9 [58.2, 83.8] | 10 | 3.8 [-12.8, 20.9] | 10 |
| GPT-OSS + File Search | 86.8 [76.6, 93.9] | 10 | -11.0 [-28.6, 8.7] | 10 |
| GPT-OSS (no RAG) | 40.3 [23.8, 63.3] | 10 | 35.4 [15.2, 55.0] | 10 |

## Operating data

Not scored: answers that the judge could not score (not in the means).

| System | Answered | Failed | Not scored | "I don't know" | Median latency (s) | Est. cost (USD) |
|---|---|---|---|---|---|---|
| 4Minds (Constellations) | 10/10 | 0 | 0 | 0 | 12.63 | n/a |
| GPT-OSS + LightRAG | 10/10 | 0 | 0 | 0 | 5.52 | 0.0215 |
| GPT-OSS + File Search | 10/10 | 0 | 0 | 0 | 16.05 | 0.0819 |
| GPT-OSS (no RAG) | 10/10 | 0 | 0 | 7 | 1.45 | 0.0012 |

## Systems

- **4Minds (Constellations)**: 4Minds prod, Constellations RAG over the dataset graph, GPT-OSS-120B served by 4Minds (AWQ weights, no fine-tuning). Run 2026-10-09T23:45:21+00:00 to 2026-10-09T23:46:06+00:00.
- **GPT-OSS + LightRAG**: LightRAG v1.2.5 (official GraphRAG-Bench runner settings), index and answers with GPT-OSS-120B on Amazon Bedrock. Run 2026-10-10T00:28:37+00:00 to 2026-10-10T00:28:54+00:00.
- **GPT-OSS + File Search**: Gemini File Search (top_k 5) retrieves, GPT-OSS-120B on Amazon Bedrock answers. Run 2026-10-10T00:34:06+00:00 to 2026-10-10T00:35:17+00:00.
- **GPT-OSS (no RAG)**: Amazon Bedrock, openai.gpt-oss-120b-1:0, question only (no retrieval). Run 2026-10-10T00:33:44+00:00 to 2026-10-10T00:33:55+00:00.

## Notes and caveats

- Generation scoring only (generation_eval.py). Retrieval and graph metrics are not part of this comparison.
- Medical subset only (one corpus, Medical.txt). The Novel subset was not run.
- Gold answers come from the official repo at commit fdbab59. The local Questions/ copy (another dataset release) has 251 different Contextual Summarize and Creative Generation answers.
- All systems answer with GPT-OSS-120B. The three Bedrock systems use openai.gpt-oss-120b-1:0 on Amazon Bedrock (us-east-1) with the 4Minds server settings: temperature 0.3, 4,096 max tokens, reasoning effort medium (the GPT-OSS default, which 4Minds does not change). 4Minds serves its own AWQ-quantized GPT-OSS-120B on vLLM; the quantization can change answers a little.
- The judge, gpt-4o-mini, is also an OpenAI model, so a same-family preference by the judge is possible. It applies to all systems in the same way.
- The Bedrock systems get the official prompt as the system message, and the retrieved chunks in the user message under "---Knowledge Base---" (LightRAG uses its own official prompt layout). 4Minds has no per-request system prompt; the official prompt is in the model persona (behavioralGuidelines).
- No RAG: the question only, with the official system prompt. The prompt tells the model to answer from a Knowledge Base, which is empty here, so some answers are "I don't know". It has no context, so it has no faithfulness score.
- File Search has no search-only API, and groundingChunks holds only the chunks that Gemini's text cites. The search call (gemini-3.8-flash, top_k 5) therefore uses the instruction 'cite_each' (systems/retrievers.py): do not answer, write one line for each returned passage. The chunk text comes from groundingChunks, not from Gemini's text. In a 10-question check this gave exactly 5 chunks for every question with one search (the official prompt gave a mean of 2.7, often 1). Gemini can search more than one time for summary and creative questions; then GPT-OSS gets all chunks found (8 to 13 in the check). Gemini's tokens are in the cost and its time is in the latency.
- LightRAG: GPT-OSS often writes LightRAG's field delimiter <|> as |>, <|, <> or |<, or breaks a record over lines. LightRAG 1.2.5 then rejects the record: 34.6% of relationship records and 3.4% of entity records in the first GPT-OSS index (Gemini: 0.4% and 0%). The driver repairs these delimiters in memory before LightRAG parses the extraction output (--repair-delimiters; audit/patches/lightrag-1.2.5-gptoss-delimiter-repair.py); the loss is then 6.4% and 0.8%. The index was rebuilt from the cached extraction output of the first build, so the LLM output is the same; the first index stays in shared/lightrag/workspace_bedrock-gpt-oss-120b/.
- LightRAG: the index was built again with GPT-OSS-120B on Bedrock. The backend generation settings (temperature 0.3, 4,096 max tokens, reasoning effort medium) apply at query time only; the index was built with the LightRAG defaults. GPT-OSS on Bedrock puts its reasoning in <reasoning> tags in the answer text; the driver removes them before LightRAG reads the output.
- LightRAG: the embedding model is BAAI/bge-large-en-v1.5 (the official code sets embedding_dim 1024), and context is stored as a one-item list. Its official string form would be split into characters by the scorer.
- LightRAG: API mode of the official Examples/run_lightrag.py does not run at commit fdbab59 (an UnboundLocalError and a duplicate keyword argument). Both are fixed in memory with a 4-line change; the query settings are unchanged. LightRAG 1.2.5 also needs the README context-return change. Both diffs are in audit/patches/.
- 4Minds: the inference WebSocket has no temperature or max-token settings, so the server defaults apply (temperature 0.3, 4,096 max tokens). The 4Minds dataset also holds the platform's dataset manifest as one extra graph node (204 nodes: 203 Medical.txt chunks + manifest).
- Vertex AI RAG Engine is not in this comparison. On 2026-10-09 Google refused us-central1 (Serverless: no available indexing project) and us-east4 (Spanner mode allowlist-only for new projects), and in europe-west4 retrieveContexts failed with HTTP 500 (Spanner corpus status) on about 60% of calls. The operator removed it; all RAG Engine regions are unprovisioned.
- Each system uses its own default retrieval and chunking settings. top_k is 5 where the system exposes it.
- Faithfulness (official) is NaN for most answers: at commit fdbab59 the verdict prompt does not ask for JSON, gpt-4o-mini answers in Markdown prose and the parser finds no verdicts (audit/diagnostics/faithfulness_nan.json). 'Faithfulness (JSON-format fix)' runs the official code and judge settings again with one added sentence that asks for the format of the prompt's own examples (audit/patches/faithfulness-fdbab59-json-format.diff). It is not part of the official protocol.
- Faithfulness reads only the first 10,000 characters of `context`. Systems that return more context (4Minds multi-step retrieval: up to 50 chunks; File Search on multi-search questions: up to about 15,000 characters) are judged on part of it. 4Minds chunks are stored in 4Minds' own score order (highest first), so the judge sees the strongest chunks.
- The medical source text can be in the training data of the models.
- Each system ran one time. LLM answers and LLM-judge scores vary between runs; use the confidence intervals.
- The judge is not fully repeatable at temperature 0 with a fixed seed: scoring the same 10 pilot answers again changed answer correctness for 4 of 10 answers (the largest change was 0.60 to 0.97; ROUGE-L did not change). Single-question scores are not reliable; the averages over many questions are (runs/2026-10-09_gemini-pilot/tests/judge-repeat).
- Scoring rule, the same for every system: one scoring run, then at most 3 reruns of the shards (50 answers each) that have answers the judge could not score. A rerun scores the full shard again. Answers that the judge still cannot score are not in the means; the Not scored column gives the count. The cause is the judge's output format: it sometimes writes an item of its TP, FP or FN list as plain text, not as an object, and the official scorer drops the sample. This happens with any answer, but more often with "I don't know" answers, so No RAG has the most such samples, and its mean is probably a little too high.
- Prod systems (4Minds, Amazon Bedrock, Gemini File Search) can change over time. The dates are in the run manifests.

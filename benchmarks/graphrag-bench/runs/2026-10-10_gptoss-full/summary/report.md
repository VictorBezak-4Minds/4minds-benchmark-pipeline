# GraphRAG-Bench Medical: generation results

Generated 2026-10-10T17:21:02+00:00. Scores are 0-100 with 95% bootstrap confidence intervals.

Judge `gpt-4o-mini` (gpt-4o-mini-2024-07-18), embeddings `BAAI/bge-large-en-v1.5`, GraphRAG-Bench commit `fdbab59`.

## Answer correctness, all questions

| System | Answer correctness | n |
|---|---|---|
| 4Minds (Constellations) | 70.1 [69.0, 71.3] | 2060 |
| GPT-OSS + LightRAG | 75.4 [74.5, 76.5] | 2062 |
| GPT-OSS + File Search | 75.6 [74.5, 76.7] | 2061 |
| GPT-OSS (no RAG) | 40.8 [39.4, 42.2] | 2057 |

## Fact Retrieval

| System | ROUGE-L | Answer correctness |
|---|---|---|
| 4Minds (Constellations) | 26.3 [25.1, 27.5] (n=1097) | 67.4 [65.8, 68.9] (n=1097) |
| GPT-OSS + LightRAG | 39.9 [38.5, 41.3] (n=1098) | 73.3 [71.6, 74.9] (n=1098) |
| GPT-OSS + File Search | 39.9 [38.5, 41.3] (n=1098) | 73.5 [72.0, 75.2] (n=1098) |
| GPT-OSS (no RAG) | 16.7 [15.4, 18.0] (n=1098) | 43.2 [41.4, 45.2] (n=1098) |

## Complex Reasoning

| System | ROUGE-L | Answer correctness |
|---|---|---|
| 4Minds (Constellations) | 14.1 [13.3, 14.9] (n=509) | 68.1 [66.0, 70.4] (n=509) |
| GPT-OSS + LightRAG | 24.5 [23.4, 25.8] (n=509) | 76.9 [75.1, 78.8] (n=509) |
| GPT-OSS + File Search | 25.7 [24.4, 27.1] (n=509) | 77.4 [75.4, 79.4] (n=509) |
| GPT-OSS (no RAG) | 10.7 [9.5, 12.0] (n=508) | 41.2 [38.4, 44.1] (n=508) |

## Contextual Summarize

| System | Answer correctness | Coverage |
|---|---|---|
| 4Minds (Constellations) | 82.3 [79.9, 84.8] (n=289) | 82.7 [80.4, 85.2] (n=289) |
| GPT-OSS + LightRAG | 82.3 [80.2, 84.3] (n=289) | 68.9 [66.0, 71.6] (n=289) |
| GPT-OSS + File Search | 81.8 [79.4, 84.1] (n=288) | 75.1 [72.2, 77.9] (n=288) |
| GPT-OSS (no RAG) | 34.0 [30.7, 37.5] (n=288) | 17.0 [13.7, 20.6] (n=288) |

## Creative Generation

| System | Answer correctness | Coverage | Faithfulness (official) | Faithfulness (JSON-format fix) |
|---|---|---|---|---|
| 4Minds (Constellations) | 72.7 [69.7, 75.8] (n=165) | 61.5 [58.3, 64.8] (n=165) | 67.1 [54.8, 79.5] (n=28) | 56.3 [50.5, 61.7] (n=166) |
| GPT-OSS + LightRAG | 73.4 [71.2, 75.8] (n=166) | 61.1 [58.3, 64.0] (n=166) | 51.5 [45.0, 57.8] (n=105) | 50.1 [45.3, 54.9] (n=166) |
| GPT-OSS + File Search | 73.2 [70.0, 76.3] (n=166) | 62.4 [58.8, 66.0] (n=166) | 38.0 [24.7, 51.7] (n=27) | 53.7 [48.3, 58.9] (n=165) |
| GPT-OSS (no RAG) | 35.0 [30.8, 39.3] (n=163) | 20.9 [16.4, 25.4] (n=163) | not available (no context) | not available (no context) |

Answers with NaN faithfulness (official / JSON-format fix): 4Minds (Constellations) 137/165 / 0; GPT-OSS + LightRAG 61/166 / 0; GPT-OSS + File Search 139/166 / 1.

## Paired differences: 4Minds (Constellations) minus each system

Positive values favor 4Minds. Same questions only.

| Compared with | Question type | Metric | Difference | n |
|---|---|---|---|---|
| GPT-OSS + LightRAG | Fact Retrieval | ROUGE-L | -13.6 [-15.0, -12.3] | 1097 |
| GPT-OSS + LightRAG | Fact Retrieval | Answer correctness | -5.9 [-7.8, -3.9] | 1097 |
| GPT-OSS + LightRAG | Complex Reasoning | ROUGE-L | -10.5 [-11.4, -9.5] | 509 |
| GPT-OSS + LightRAG | Complex Reasoning | Answer correctness | -8.8 [-11.3, -6.3] | 509 |
| GPT-OSS + LightRAG | Contextual Summarize | Answer correctness | 0.1 [-2.8, 3.0] | 289 |
| GPT-OSS + LightRAG | Contextual Summarize | Coverage | 13.8 [10.9, 16.7] | 289 |
| GPT-OSS + LightRAG | Creative Generation | Answer correctness | -0.8 [-4.2, 2.7] | 165 |
| GPT-OSS + LightRAG | Creative Generation | Coverage | 0.3 [-2.5, 3.0] | 165 |
| GPT-OSS + LightRAG | Creative Generation | Faithfulness (official) | -6.8 [-26.8, 9.2] | 15 |
| GPT-OSS + LightRAG | Creative Generation | Faithfulness (JSON-format fix) | 6.2 [-0.1, 12.3] | 166 |
| GPT-OSS + LightRAG | All questions | Answer correctness | -5.4 [-6.7, -4.0] | 2060 |
| GPT-OSS + File Search | Fact Retrieval | ROUGE-L | -13.6 [-15.0, -12.2] | 1097 |
| GPT-OSS + File Search | Fact Retrieval | Answer correctness | -6.1 [-7.8, -4.2] | 1097 |
| GPT-OSS + File Search | Complex Reasoning | ROUGE-L | -11.7 [-12.7, -10.7] | 509 |
| GPT-OSS + File Search | Complex Reasoning | Answer correctness | -9.3 [-12.0, -6.6] | 509 |
| GPT-OSS + File Search | Contextual Summarize | Answer correctness | 0.5 [-2.5, 3.6] | 288 |
| GPT-OSS + File Search | Contextual Summarize | Coverage | 7.6 [4.7, 10.5] | 288 |
| GPT-OSS + File Search | Creative Generation | Answer correctness | -0.5 [-4.6, 3.4] | 165 |
| GPT-OSS + File Search | Creative Generation | Coverage | -0.9 [-4.4, 2.6] | 165 |
| GPT-OSS + File Search | Creative Generation | Faithfulness (official) | 39.7 [4.0, 90.9] | 3 |
| GPT-OSS + File Search | Creative Generation | Faithfulness (JSON-format fix) | 2.9 [-3.6, 9.3] | 165 |
| GPT-OSS + File Search | All questions | Answer correctness | -5.5 [-6.8, -4.3] | 2059 |
| GPT-OSS (no RAG) | Fact Retrieval | ROUGE-L | 9.6 [8.1, 11.1] | 1097 |
| GPT-OSS (no RAG) | Fact Retrieval | Answer correctness | 24.2 [21.8, 26.5] | 1097 |
| GPT-OSS (no RAG) | Complex Reasoning | ROUGE-L | 3.3 [2.1, 4.5] | 508 |
| GPT-OSS (no RAG) | Complex Reasoning | Answer correctness | 26.9 [23.5, 30.1] | 508 |
| GPT-OSS (no RAG) | Contextual Summarize | Answer correctness | 48.3 [44.3, 52.3] | 288 |
| GPT-OSS (no RAG) | Contextual Summarize | Coverage | 65.6 [61.5, 69.6] | 288 |
| GPT-OSS (no RAG) | Creative Generation | Answer correctness | 37.7 [32.4, 43.3] | 162 |
| GPT-OSS (no RAG) | Creative Generation | Coverage | 40.8 [35.0, 46.3] | 162 |
| GPT-OSS (no RAG) | All questions | Answer correctness | 29.3 [27.6, 31.0] | 2055 |

## Sensitivity check: Without incomplete File Search replies

In the full run, the File Search adapter accepted some Gemini replies with no chunks and no normal finish reason (most after about 400,000 tokens of search results) as results, and GPT-OSS answered with an empty Knowledge Base. The adapter now retries such replies. A test with 3 of these questions on 2026-10-10 passed 2 at the first attempt and failed 1 again 4 times (runs/2026-10-10_gptoss-full/tests/filesearch-fault-probe). This check takes these questions out for every system and computes answer correctness and the paired differences again.

Excluded for all systems: 21 answered questions whose retrieval returned no chunks and had no normal finish reason (MAX_TOKENS, STOP).

| System | Answer correctness, all questions | n | Paired difference | n |
|---|---|---|---|---|
| 4Minds (Constellations) | 70.3 [69.2, 71.4] | 2039 | (reference) |  |
| GPT-OSS + LightRAG | 75.6 [74.6, 76.6] | 2041 | -5.3 [-6.6, -4.0] | 2039 |
| GPT-OSS + File Search | 76.1 [75.1, 77.2] | 2040 | -5.9 [-7.1, -4.6] | 2038 |
| GPT-OSS (no RAG) | 40.8 [39.5, 42.2] | 2036 | 29.4 [27.6, 31.1] | 2034 |

## Operating data

Not scored: answers that the judge could not score (not in the means).

| System | Answered | Failed | Not scored | "I don't know" | Median latency (s) | Est. cost (USD) |
|---|---|---|---|---|---|---|
| 4Minds (Constellations) | 2062/2062 | 0 | 2 | 38 | 11.76 | n/a |
| GPT-OSS + LightRAG | 2062/2062 | 0 | 0 | 49 | 4.36 | 4.2623 |
| GPT-OSS + File Search | 2062/2062 | 0 | 1 | 71 | 15.41 | 42.7408 |
| GPT-OSS (no RAG) | 2062/2062 | 0 | 5 | 1153 | 0.86 | 0.2425 |

## Systems

- **4Minds (Constellations)**: 4Minds prod, Constellations RAG over the dataset graph, GPT-OSS-120B served by 4Minds (AWQ weights, no fine-tuning). Run 2026-10-10T11:36:15+00:00 to 2026-10-10T13:31:06+00:00.
- **GPT-OSS + LightRAG**: LightRAG v1.2.5 (official GraphRAG-Bench runner settings), index and answers with GPT-OSS-120B on Amazon Bedrock. Run 2026-10-10T11:36:25+00:00 to 2026-10-10T12:21:50+00:00.
- **GPT-OSS + File Search**: Gemini File Search (top_k 5) retrieves, GPT-OSS-120B on Amazon Bedrock answers. Run 2026-10-10T11:36:20+00:00 to 2026-10-10T13:05:41+00:00.
- **GPT-OSS (no RAG)**: Amazon Bedrock, openai.gpt-oss-120b-1:0, question only (no retrieval). Run 2026-10-10T11:36:09+00:00 to 2026-10-10T11:42:33+00:00.

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

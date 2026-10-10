# GraphRAG-Bench Medical: generation results (PILOT)

Generated 2026-10-10T18:45:35+00:00. Scores are 0-100 with 95% bootstrap confidence intervals.

Judge `claude-haiku-5-5` (claude-haiku-5-5), embeddings `BAAI/bge-large-en-v1.5`, GraphRAG-Bench commit `fdbab59`.

## Answer correctness, all questions

| System | Answer correctness | n |
|---|---|---|
| 4Minds (Constellations) | 55.6 [45.4, 65.5] | 10 |
| GPT-OSS + LightRAG | 61.5 [53.2, 70.7] | 10 |
| GPT-OSS + File Search | 68.1 [57.9, 79.7] | 10 |
| GPT-OSS (no RAG) | 34.3 [17.5, 56.2] | 10 |

## Fact Retrieval

| System | ROUGE-L | Answer correctness |
|---|---|---|
| 4Minds (Constellations) | 16.2 [10.7, 23.4] (n=5) | 50.1 [35.8, 65.6] (n=5) |
| GPT-OSS + LightRAG | 43.1 [30.0, 58.1] (n=5) | 65.0 [54.9, 75.8] (n=5) |
| GPT-OSS + File Search | 43.7 [30.9, 59.5] (n=5) | 71.2 [58.6, 85.6] (n=5) |
| GPT-OSS (no RAG) | 5.7 [0.0, 17.1] (n=5) | 33.4 [17.2, 65.5] (n=5) |

## Complex Reasoning

| System | ROUGE-L | Answer correctness |
|---|---|---|
| 4Minds (Constellations) | 14.5 [4.0, 25.0] (n=2) | 55.6 [37.3, 74.0] (n=2) |
| GPT-OSS + LightRAG | 21.4 [11.0, 31.7] (n=2) | 63.7 [43.5, 83.9] (n=2) |
| GPT-OSS + File Search | 30.7 [12.7, 48.8] (n=2) | 74.7 [50.2, 99.3] (n=2) |
| GPT-OSS (no RAG) | 16.0 [0.0, 32.0] (n=2) | 52.2 [18.2, 86.2] (n=2) |

## Contextual Summarize

| System | Answer correctness | Coverage |
|---|---|---|
| 4Minds (Constellations) | 64.4 [55.9, 73.0] (n=2) | 80.6 [72.2, 88.9] (n=2) |
| GPT-OSS + LightRAG | 51.8 [47.0, 56.7] (n=2) | 63.9 [61.1, 66.7] (n=2) |
| GPT-OSS + File Search | 50.8 [47.5, 54.0] (n=2) | 75.0 [72.2, 77.8] (n=2) |
| GPT-OSS (no RAG) | 27.5 [16.5, 38.4] (n=2) | 27.8 [0.0, 55.6] (n=2) |

## Creative Generation

| System | Answer correctness | Coverage | Faithfulness (official) | Faithfulness (JSON-format fix) |
|---|---|---|---|---|
| 4Minds (Constellations) | 65.0 [65.0, 65.0] (n=1) | 84.6 [84.6, 84.6] (n=1) | 7.7 [7.7, 7.7] (n=1) | 7.2 [7.2, 7.2] (n=1) |
| GPT-OSS + LightRAG | 58.7 [58.7, 58.7] (n=1) | 84.6 [84.6, 84.6] (n=1) | 31.3 [31.3, 31.3] (n=1) | 24.7 [24.7, 24.7] (n=1) |
| GPT-OSS + File Search | 73.9 [73.9, 73.9] (n=1) | 66.7 [66.7, 66.7] (n=1) | 65.5 [65.5, 65.5] (n=1) | 39.4 [39.4, 39.4] (n=1) |
| GPT-OSS (no RAG) | 16.6 [16.6, 16.6] (n=1) | 0.0 [0.0, 0.0] (n=1) | not available (no context) | not available (no context) |

Answers with NaN faithfulness (official / JSON-format fix): 4Minds (Constellations) 0/1 / 0; GPT-OSS + LightRAG 0/1 / 0; GPT-OSS + File Search 0/1 / 0.

## Paired differences: 4Minds (Constellations) minus each system

Positive values favor 4Minds. Same questions only.

| Compared with | Question type | Metric | Difference | n |
|---|---|---|---|---|
| GPT-OSS + LightRAG | Fact Retrieval | ROUGE-L | -26.9 [-46.3, -6.8] | 5 |
| GPT-OSS + LightRAG | Fact Retrieval | Answer correctness | -14.9 [-24.5, -4.9] | 5 |
| GPT-OSS + LightRAG | Complex Reasoning | ROUGE-L | -6.9 [-7.0, -6.7] | 2 |
| GPT-OSS + LightRAG | Complex Reasoning | Answer correctness | -8.0 [-9.9, -6.2] | 2 |
| GPT-OSS + LightRAG | Contextual Summarize | Answer correctness | 12.6 [8.9, 16.3] | 2 |
| GPT-OSS + LightRAG | Contextual Summarize | Coverage | 16.7 [11.1, 22.2] | 2 |
| GPT-OSS + LightRAG | Creative Generation | Answer correctness | 6.3 [6.3, 6.3] | 1 |
| GPT-OSS + LightRAG | Creative Generation | Coverage | 0.0 [0.0, 0.0] | 1 |
| GPT-OSS + LightRAG | Creative Generation | Faithfulness (official) | -23.7 [-23.7, -23.7] | 1 |
| GPT-OSS + LightRAG | Creative Generation | Faithfulness (JSON-format fix) | -17.4 [-17.4, -17.4] | 1 |
| GPT-OSS + LightRAG | All questions | Answer correctness | -5.9 [-14.3, 2.5] | 10 |
| GPT-OSS + File Search | Fact Retrieval | ROUGE-L | -27.5 [-44.7, -11.8] | 5 |
| GPT-OSS + File Search | Fact Retrieval | Answer correctness | -21.1 [-23.5, -19.2] | 5 |
| GPT-OSS + File Search | Complex Reasoning | ROUGE-L | -16.2 [-23.8, -8.7] | 2 |
| GPT-OSS + File Search | Complex Reasoning | Answer correctness | -19.1 [-25.3, -12.9] | 2 |
| GPT-OSS + File Search | Contextual Summarize | Answer correctness | 13.7 [8.4, 19.0] | 2 |
| GPT-OSS + File Search | Contextual Summarize | Coverage | 5.6 [0.0, 11.1] | 2 |
| GPT-OSS + File Search | Creative Generation | Answer correctness | -8.9 [-8.9, -8.9] | 1 |
| GPT-OSS + File Search | Creative Generation | Coverage | 17.9 [17.9, 17.9] | 1 |
| GPT-OSS + File Search | Creative Generation | Faithfulness (official) | -57.8 [-57.8, -57.8] | 1 |
| GPT-OSS + File Search | Creative Generation | Faithfulness (JSON-format fix) | -32.1 [-32.1, -32.1] | 1 |
| GPT-OSS + File Search | All questions | Answer correctness | -12.5 [-20.7, -2.9] | 10 |
| GPT-OSS (no RAG) | Fact Retrieval | ROUGE-L | 10.4 [5.6, 14.3] | 5 |
| GPT-OSS (no RAG) | Fact Retrieval | Answer correctness | 16.7 [-16.8, 44.6] | 5 |
| GPT-OSS (no RAG) | Complex Reasoning | ROUGE-L | -1.5 [-7.0, 4.0] | 2 |
| GPT-OSS (no RAG) | Complex Reasoning | Answer correctness | 3.5 [-12.1, 19.0] | 2 |
| GPT-OSS (no RAG) | Contextual Summarize | Answer correctness | 37.0 [17.5, 56.4] | 2 |
| GPT-OSS (no RAG) | Contextual Summarize | Coverage | 52.8 [33.3, 72.2] | 2 |
| GPT-OSS (no RAG) | Creative Generation | Answer correctness | 48.4 [48.4, 48.4] | 1 |
| GPT-OSS (no RAG) | Creative Generation | Coverage | 84.6 [84.6, 84.6] | 1 |
| GPT-OSS (no RAG) | All questions | Answer correctness | 21.3 [1.8, 39.7] | 10 |

## Sensitivity check: Without incomplete File Search replies

In the full run, the File Search adapter accepted some Gemini replies with no chunks and no normal finish reason (most after about 400,000 tokens of search results) as results, and GPT-OSS answered with an empty Knowledge Base. The adapter now retries such replies. A test with 3 of these questions on 2026-10-10 passed 2 at the first attempt and failed 1 again 4 times (runs/2026-10-10_gptoss-full/tests/filesearch-fault-probe). This check takes these questions out for every system and computes answer correctness and the paired differences again.

Excluded for all systems: 0 answered questions whose retrieval returned no chunks and had no normal finish reason (MAX_TOKENS, STOP).

| System | Answer correctness, all questions | n | Paired difference | n |
|---|---|---|---|---|
| 4Minds (Constellations) | 55.6 [45.6, 66.0] | 10 | (reference) |  |
| GPT-OSS + LightRAG | 61.5 [53.7, 70.1] | 10 | -5.9 [-14.3, 2.4] | 10 |
| GPT-OSS + File Search | 68.1 [57.6, 80.0] | 10 | -12.5 [-20.1, -3.2] | 10 |
| GPT-OSS (no RAG) | 34.3 [17.5, 53.9] | 10 | 21.3 [2.1, 38.5] | 10 |

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
- Deviation from the official protocol: the judge is Claude Haiku 5.5 (Claude API, OpenAI-compatible endpoint), not gpt-4o-mini. The scorer code, prompts, embeddings (bge-large) and answers are the same as in the gptoss comparison, so the difference in scores comes from the judge.
- Claude Haiku 5.5 refuses temperature below 1 and top_p other than 0.99, so the official judge settings temperature 0 and top_p 1 are removed from each request (pipeline/llm_backends.json judge_drop_params) and the judge uses its default sampling. The endpoint ignores seed and the penalties. The judge is therefore less repeatable than the official one; use the confidence intervals.
- Haiku 5.5 puts its JSON replies in a ```json code fence. The official factuality step (answer_accuracy.py calculate_factuality) reads replies with plain json.loads and gives factuality 0 when that fails, so without a fix every answer gets factuality 0 (answer correctness about 23 for every system). Sometimes Haiku also writes a comment after the fence. If a judge reply is not JSON, the scorer uses the JSON in its first code fence instead, in memory, before the official parser reads it (pipeline/llm_backends.json judge_strip_code_fence). The judge usage counts fences_removed, prose_dropped (text outside the fence) and not_json_replies (still not JSON). The prompts and the parsers are not changed, and the fix is the same for all systems.
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
- Faithfulness reads only the first 10,000 characters of `context`. Systems that return more context (4Minds multi-step retrieval: up to 50 chunks; File Search on multi-search questions: up to about 15,000 characters) are judged on part of it. 4Minds chunks are stored in 4Minds' own score order (highest first), so the judge sees the strongest chunks.
- The medical source text can be in the training data of the models.
- Each system ran one time. LLM answers and LLM-judge scores vary between runs; use the confidence intervals.
- Scoring rule, the same for every system: one scoring run, then at most 3 reruns of the shards (50 answers each) that have answers the judge could not score. A rerun scores the full shard again. Answers that the judge still cannot score are not in the means; the Not scored column gives the count. The cause is the judge's output format: it sometimes writes an item of its TP, FP or FN list as plain text, not as an object, and the official scorer drops the sample. This happens with any answer, but more often with "I don't know" answers, so No RAG has the most such samples, and its mean is probably a little too high.
- Prod systems (4Minds, Amazon Bedrock, Gemini File Search) can change over time. The dates are in the run manifests.
- Faithfulness (official): the verdict prompt at commit fdbab59 does not ask for JSON. Answers whose verdicts the parser cannot read score NaN; the report gives the NaN count for this judge. 'Faithfulness (JSON-format fix)' adds one sentence that asks for the format of the prompt's own examples (audit/patches/faithfulness-fdbab59-json-format.diff). Not part of the official protocol.

# GraphRAG-Bench Medical: generation results (PILOT)

Generated 2026-10-09T16:05:28+00:00. Scores are 0-100 with 95% bootstrap confidence intervals.

Judge `gpt-4o-mini` (gpt-4o-mini-2024-07-18), embeddings `BAAI/bge-large-en-v1.5`, GraphRAG-Bench commit `fdbab59`.

## Answer correctness, all questions

| System | Answer correctness | n |
|---|---|---|
| 4Minds (Constellations) | 79.0 [66.5, 90.5] | 10 |
| 4Minds (SYMI) | 73.8 [56.7, 89.9] | 10 |
| Gemini + File Search | 89.9 [83.8, 95.2] | 10 |
| Gemini + RAG Engine | 84.0 [75.8, 91.7] | 10 |
| LightRAG + Gemini | 84.9 [76.3, 92.5] | 10 |

## Fact Retrieval

| System | ROUGE-L | Answer correctness |
|---|---|---|
| 4Minds (Constellations) | 20.5 [14.0, 26.5] (n=5) | 68.5 [49.5, 85.2] (n=5) |
| 4Minds (SYMI) | 24.0 [14.7, 34.7] (n=5) | 56.9 [33.6, 82.7] (n=5) |
| Gemini + File Search | 53.7 [28.3, 81.6] (n=5) | 91.2 [81.1, 99.3] (n=5) |
| Gemini + RAG Engine | 53.2 [27.2, 82.6] (n=5) | 84.5 [70.5, 97.7] (n=5) |
| LightRAG + Gemini | 48.3 [34.8, 70.5] (n=5) | 85.5 [70.4, 98.3] (n=5) |

## Complex Reasoning

| System | ROUGE-L | Answer correctness |
|---|---|---|
| 4Minds (Constellations) | 17.1 [6.3, 27.9] (n=2) | 91.0 [82.9, 99.1] (n=2) |
| 4Minds (SYMI) | 16.8 [6.9, 26.7] (n=2) | 85.8 [72.8, 98.7] (n=2) |
| Gemini + File Search | 44.8 [22.9, 66.7] (n=2) | 82.3 [74.6, 90.0] (n=2) |
| Gemini + RAG Engine | 44.3 [20.3, 68.3] (n=2) | 84.2 [79.6, 88.9] (n=2) |
| LightRAG + Gemini | 52.9 [22.5, 83.3] (n=2) | 87.5 [84.9, 90.0] (n=2) |

## Contextual Summarize

| System | Answer correctness | Coverage |
|---|---|---|
| 4Minds (Constellations) | 83.6 [68.1, 99.2] (n=2) | 79.9 [72.2, 87.5] (n=2) |
| 4Minds (SYMI) | 91.8 [84.2, 99.4] (n=2) | 77.8 [55.6, 100.0] (n=2) |
| Gemini + File Search | 96.2 [94.9, 97.5] (n=2) | 76.7 [70.0, 83.3] (n=2) |
| Gemini + RAG Engine | 86.1 [73.2, 99.0] (n=2) | 58.3 [50.0, 66.7] (n=2) |
| LightRAG + Gemini | 85.0 [72.2, 97.8] (n=2) | 65.6 [61.1, 70.0] (n=2) |

## Creative Generation

| System | Answer correctness | Coverage | Faithfulness (official) | Faithfulness (JSON-format fix) |
|---|---|---|---|---|
| 4Minds (Constellations) | 98.8 [98.8, 98.8] (n=1) | 70.8 [70.8, 70.8] (n=1) | n/a | 0.0 [0.0, 0.0] (n=1) |
| 4Minds (SYMI) | 99.0 [99.0, 99.0] (n=1) | 70.8 [70.8, 70.8] (n=1) | not available (no context) | not available (no context) |
| Gemini + File Search | 85.8 [85.8, 85.8] (n=1) | 66.7 [66.7, 66.7] (n=1) | n/a | 100.0 [100.0, 100.0] (n=1) |
| Gemini + RAG Engine | 77.4 [77.4, 77.4] (n=1) | 54.2 [54.2, 54.2] (n=1) | n/a | 54.5 [54.5, 54.5] (n=1) |
| LightRAG + Gemini | 76.1 [76.1, 76.1] (n=1) | 44.0 [44.0, 44.0] (n=1) | 63.6 [63.6, 63.6] (n=1) | 63.6 [63.6, 63.6] (n=1) |

Answers with NaN faithfulness (official / JSON-format fix): 4Minds (Constellations) 1/1 / 0; Gemini + File Search 1/1 / 0; Gemini + RAG Engine 1/1 / 0; LightRAG + Gemini 0/1 / 0.

## Paired differences: 4Minds (Constellations) minus each system

Positive values favor 4Minds. Same questions only.

| Compared with | Question type | Metric | Difference | n |
|---|---|---|---|---|
| 4Minds (SYMI) | Fact Retrieval | ROUGE-L | -3.5 [-11.0, 3.6] | 5 |
| 4Minds (SYMI) | Fact Retrieval | Answer correctness | 11.6 [-14.3, 38.9] | 5 |
| 4Minds (SYMI) | Complex Reasoning | ROUGE-L | 0.3 [-0.7, 1.2] | 2 |
| 4Minds (SYMI) | Complex Reasoning | Answer correctness | 5.2 [0.3, 10.1] | 2 |
| 4Minds (SYMI) | Contextual Summarize | Answer correctness | -8.1 [-16.1, -0.2] | 2 |
| 4Minds (SYMI) | Contextual Summarize | Coverage | 2.1 [-12.5, 16.7] | 2 |
| 4Minds (SYMI) | Creative Generation | Answer correctness | -0.2 [-0.2, -0.2] | 1 |
| 4Minds (SYMI) | Creative Generation | Coverage | 0.0 [0.0, 0.0] | 1 |
| 4Minds (SYMI) | All questions | Answer correctness | 5.2 [-8.1, 21.1] | 10 |
| Gemini + File Search | Fact Retrieval | ROUGE-L | -33.2 [-55.9, -12.1] | 5 |
| Gemini + File Search | Fact Retrieval | Answer correctness | -22.7 [-40.9, -3.6] | 5 |
| Gemini + File Search | Complex Reasoning | ROUGE-L | -27.7 [-38.8, -16.6] | 2 |
| Gemini + File Search | Complex Reasoning | Answer correctness | 8.7 [-7.1, 24.5] | 2 |
| Gemini + File Search | Contextual Summarize | Answer correctness | -12.6 [-26.8, 1.6] | 2 |
| Gemini + File Search | Contextual Summarize | Coverage | 3.2 [-11.1, 17.5] | 2 |
| Gemini + File Search | Creative Generation | Answer correctness | 13.0 [13.0, 13.0] | 1 |
| Gemini + File Search | Creative Generation | Coverage | 4.2 [4.2, 4.2] | 1 |
| Gemini + File Search | Creative Generation | Faithfulness (JSON-format fix) | -100.0 [-100.0, -100.0] | 1 |
| Gemini + File Search | All questions | Answer correctness | -10.8 [-25.6, 4.3] | 10 |
| Gemini + RAG Engine | Fact Retrieval | ROUGE-L | -32.6 [-56.1, -11.7] | 5 |
| Gemini + RAG Engine | Fact Retrieval | Answer correctness | -16.0 [-37.3, 1.8] | 5 |
| Gemini + RAG Engine | Complex Reasoning | ROUGE-L | -27.2 [-40.4, -14.0] | 2 |
| Gemini + RAG Engine | Complex Reasoning | Answer correctness | 6.8 [3.4, 10.2] | 2 |
| Gemini + RAG Engine | Contextual Summarize | Answer correctness | -2.5 [-5.1, 0.1] | 2 |
| Gemini + RAG Engine | Contextual Summarize | Coverage | 21.5 [5.6, 37.5] | 2 |
| Gemini + RAG Engine | Creative Generation | Answer correctness | 21.4 [21.4, 21.4] | 1 |
| Gemini + RAG Engine | Creative Generation | Coverage | 16.7 [16.7, 16.7] | 1 |
| Gemini + RAG Engine | Creative Generation | Faithfulness (JSON-format fix) | -54.5 [-54.5, -54.5] | 1 |
| Gemini + RAG Engine | All questions | Answer correctness | -5.0 [-18.2, 6.0] | 10 |
| LightRAG + Gemini | Fact Retrieval | ROUGE-L | -27.8 [-45.1, -13.8] | 5 |
| LightRAG + Gemini | Fact Retrieval | Answer correctness | -17.1 [-42.0, 2.7] | 5 |
| LightRAG + Gemini | Complex Reasoning | ROUGE-L | -35.8 [-55.4, -16.2] | 2 |
| LightRAG + Gemini | Complex Reasoning | Answer correctness | 3.5 [-7.1, 14.2] | 2 |
| LightRAG + Gemini | Contextual Summarize | Answer correctness | -1.4 [-4.1, 1.4] | 2 |
| LightRAG + Gemini | Contextual Summarize | Coverage | 14.3 [11.1, 17.5] | 2 |
| LightRAG + Gemini | Creative Generation | Answer correctness | 22.7 [22.7, 22.7] | 1 |
| LightRAG + Gemini | Creative Generation | Coverage | 26.8 [26.8, 26.8] | 1 |
| LightRAG + Gemini | Creative Generation | Faithfulness (JSON-format fix) | -63.6 [-63.6, -63.6] | 1 |
| LightRAG + Gemini | All questions | Answer correctness | -5.8 [-20.5, 6.4] | 10 |

## Operating data

| System | Answered | Failed | "I don't know" | Median latency (s) | Est. cost (USD) |
|---|---|---|---|---|---|
| 4Minds (Constellations) | 10/10 | 0 | 0 | 11.31 | n/a |
| 4Minds (SYMI) | 10/10 | 0 | 0 | 10.84 | n/a |
| Gemini + File Search | 10/10 | 0 | 0 | 10.25 | 0.1454 |
| Gemini + RAG Engine | 10/10 | 0 | 0 | 8.42 | 0.0313 |
| LightRAG + Gemini | 10/10 | 0 | 0 | 10.89 | 0.0828 |

## Systems

- **4Minds (Constellations)**: 4Minds prod, Constellations RAG over the dataset graph, GPT-OSS-120B standard weights. Run 2026-10-09T14:50:12+00:00 to 2026-10-09T14:50:54+00:00.
- **4Minds (SYMI)**: 4Minds prod, SYMI agent engine over the same model and dataset. Run 2026-10-09T15:03:49+00:00 to 2026-10-09T15:04:32+00:00.
- **Gemini + File Search**: Gemini Developer API, gemini-3.8-flash with the File Search tool (top_k 5). Run 2026-10-09T14:33:11+00:00 to 2026-10-09T14:38:54+00:00.
- **Gemini + RAG Engine**: Vertex AI, gemini-3.8-flash with the RAG Engine retrieval tool (top_k 5). Run 2026-10-09T15:24:09+00:00 to 2026-10-09T15:29:41+00:00.
- **LightRAG + Gemini**: LightRAG v1.2.5 (official GraphRAG-Bench runner settings), gemini-3.8-flash. Run 2026-10-09T15:39:31+00:00 to 2026-10-09T15:40:07+00:00.

## Notes and caveats

- Generation scoring only (generation_eval.py). Retrieval and graph metrics are not part of this comparison.
- Medical subset only (one corpus, Medical.txt). The Novel subset was not run.
- Gold answers come from the official repo at commit fdbab59. The local Questions/ copy (another dataset release) has 251 different Contextual Summarize and Creative Generation answers.
- 4Minds has no per-request system prompt. The official prompt is in the model persona (behavioralGuidelines). The other systems get it as the system instruction of each request.
- 4Minds answers with GPT-OSS-120B (standard weights, no Ghost Weights fine-tuning). The judge, gpt-4o-mini, is also an OpenAI model, so a same-family preference by the judge is possible.
- Gemini + File Search: `context` holds only the chunks that the answer cites. The other systems store all retrieved chunks. Only faithfulness reads `context`, and the judge reads the first 10,000 characters.
- LightRAG: the embedding model is BAAI/bge-large-en-v1.5 (the official code sets embedding_dim 1024), and context is stored as a one-item list. Its official string form would be split into characters by the scorer.
- LightRAG: API mode of the official Examples/run_lightrag.py does not run at commit fdbab59 (an UnboundLocalError and a duplicate keyword argument). Both are fixed in memory with a 4-line change; the query settings are unchanged. LightRAG 1.2.5 also needs the README context-return change. Both diffs are in results/audit/patches/.
- Each system uses its own default retrieval and chunking settings. top_k is 5 where the system exposes it.
- 4Minds: the inference WebSocket has no temperature or max-token settings, so the server defaults apply (temperature 0.3, 4,096 max tokens). The 4Minds dataset also holds the platform's dataset manifest as one extra graph node (204 nodes: 203 Medical.txt chunks + manifest).
- 4Minds (SYMI) runs through POST /api/v1/user/inference (inference_engine symi): the SYMI WebSocket path rejects API keys. For API keys this endpoint returns chunk references (all from Medical.txt) but not chunk text, so SYMI has no faithfulness score. SYMI is an agent with its own instructions; the persona prompt may not apply to it in the same way as on Constellations.
- Gemini + RAG Engine: the corpus is in europe-west4 (RAG Engine defaults: Spanner mode, RagManagedDb, Basic tier, default chunking and embeddings). us-central1 is allowlist-only for new projects, and its Serverless mode failed with a Google capacity error. The model is served from the global endpoint.
- Faithfulness (official) is NaN for most answers: at commit fdbab59 the verdict prompt does not ask for JSON, gpt-4o-mini answers in Markdown prose and the parser finds no verdicts (results/audit/diagnostics/faithfulness_nan.json). 'Faithfulness (JSON-format fix)' runs the official code and judge settings again with one added sentence that asks for the format of the prompt's own examples (results/audit/patches/faithfulness-fdbab59-json-format.diff). It is not part of the official protocol.
- Faithfulness reads only the first 10,000 characters of `context`. Systems that return more context (4Minds multi-step retrieval: up to 50 chunks; RAG Engine: about 20,000 characters) are judged on part of it. 4Minds chunks are stored in 4Minds' own score order (highest first) so that the judge sees the strongest chunks; RAG Engine returns its chunks in relevance order.
- The medical source text can be in the training data of the models.
- Each system ran one time. LLM answers and LLM-judge scores vary between runs; use the confidence intervals.
- The judge is not fully repeatable at temperature 0 with a fixed seed: scoring the same 10 pilot answers again changed answer correctness for 4 of 10 answers (the largest change was 0.60 to 0.97; ROUGE-L did not change). Single-question scores are not reliable; the averages over many questions are (results/pilot/_judge_repeat_test).
- Prod systems (4Minds, Gemini, Vertex AI) can change over time. The dates are in the run manifests.

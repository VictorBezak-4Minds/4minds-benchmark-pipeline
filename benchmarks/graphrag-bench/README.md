# GraphRAG-Bench (Medical)

**Status:** pilot complete (10 questions, 5 systems, scored). A full run is **not approved**.
A full run was started by mistake on 2026-10-09 and stopped after about 2 minutes; its
partial output is in `results/_stopped_full_run_20261009/` and was not scored.

- Upstream: <https://github.com/GraphRAG-Bench/GraphRAG-Benchmark>, pinned at
  `fdbab5959b18c96532580877ffe27d112bccc0ec` in `upstream/`.
- Pilot report: [results/pilot/summary/report.html](results/pilot/summary/report.html)
  (tables in `results/pilot/summary/report.md`).

## Protocol

| Item | Value |
|---|---|
| Subset | Medical only: 2,062 questions, 1 corpus (Fact Retrieval 1,098, Complex Reasoning 509, Contextual Summarize 289, Creative Generation 166) |
| Questions and gold answers | `upstream/Datasets/Questions/medical_questions.json` (the local `data/Questions` copy is another release with 251 different answers) |
| Scoring | generation only: official `Evaluation/generation_eval.py`, run unchanged |
| Judge | gpt-4o-mini (snapshot gpt-4o-mini-2024-07-18), embeddings BAAI/bge-large-en-v1.5 |
| System prompt | Role and Goal of `upstream/Examples/run_lightrag.py`, for every system (`benchmark_profile.SYSTEM_PROMPT`) |
| Pilot sample | `data/Questions/pilot_questions.json`: 5/2/2/1 per type, seed 42 (`make_pilot.py`) |

## Systems

| Folder in results | System | Adapter |
|---|---|---|
| `4minds_constellations` | 4Minds prod, Constellations, GPT-OSS-120B standard weights, prompt in the persona | `systems/run_4minds.py --engine constellations` |
| `4minds_symi` | 4Minds prod, SYMI (REST/SSE; no chunk text, so no faithfulness) | `systems/run_4minds.py --engine symi` |
| `gemini` | Gemini Developer API + File Search, top_k 5 | `systems/run_gemini.py` |
| `rag_engine` | Gemini + Vertex AI RAG Engine (europe-west4), top_k 5 | `systems/run_rag_engine.py` |
| `lightrag` | LightRAG 1.2.5 + Gemini through the official runner | `run_lightrag_bench.py` (benchmark-only adapter) |

## Pilot result (10 questions; not a conclusion)

| System | Answer correctness, all questions (95% CI) | Median latency | Pilot cost |
|---|---|---|---|
| Gemini + File Search | 89.9 (83.8–95.2) | 10.3 s | $0.15 |
| LightRAG + Gemini | 84.9 (76.3–92.5) | 10.9 s | $0.08 |
| Gemini + RAG Engine | 84.0 (75.8–91.7) | 8.4 s | $0.03 |
| 4Minds (Constellations) | 79.0 (66.5–90.5) | 11.3 s | n/a |
| 4Minds (SYMI) | 73.8 (56.7–89.9) | 10.8 s | n/a |

All intervals overlap. 10 questions cannot separate these systems.

Full-run estimate from the pilot (`results/pilot/timing.json`): about 4.7 h, limited by
4Minds at 4 workers (Constellations, then SYMI). Answer cost about $54 for the
three Gemini-based systems, plus the judge.

## Findings and fixes (apply them to future benchmarks too)

1. **4Minds answers are long.** Median about 1,000 characters against 200–270 for the Gemini
   systems, with the same "direct and concise" prompt. This lowers ROUGE-L and can lower
   answer correctness. It is product behaviour; it is reported, not changed.
2. **Official faithfulness is NaN for most answers.** The verdict prompt does not ask for
   JSON; gpt-4o-mini answers in prose. `score_faithfulness.py` adds a labelled
   "JSON-format fix" score (diff in `results/audit/patches/`, diagnosis in
   `results/audit/diagnostics/faithfulness_nan.json`).
3. **Faithfulness reads only 10,000 characters of context.** 4Minds multi-step retrieval
   returns up to 50 chunks. The 4Minds adapter stores chunks in 4Minds' own score order.
4. **The judge is not repeatable.** 4 of 10 answer-correctness scores changed when the same
   answers were scored again (`results/pilot/_judge_repeat_test`).
5. **Scoring is slow** (3 samples at a time). `score.py --shards N` runs N official scorer
   processes on parts of the predictions and merges them; the scores do not change.
6. **Upstream bugs:** the official LightRAG runner has 2 bugs in API mode (fixed in memory,
   diff in `results/audit/patches/`); LightRAG 1.2.5 needs the README context-return patch
   (`patch_lightrag.py`).
7. **System quirks:** the SYMI WebSocket rejects API keys (use REST); RAG Engine grounding
   chunks carry no text from the global endpoint (use `retrieveContexts`); us-central1 RAG
   Engine is allowlist-only for new projects; Gemini and RAG Engine requests can hang for
   300 s (use `--timeout 120`); the scorer crashes on Apple MPS (`score_launcher.py` hides MPS).
8. **4Minds metadata says "enhancing"** after the build is complete: the platform counts its
   own manifest file as one more ETL file. `setup_4minds.py` explains the readiness rule.

All caveats for the report are in `aggregate.py` (`CAVEATS`).

## Files

| File | Purpose |
|---|---|
| `benchmark_profile.py` | the benchmark-specific values for the pipeline |
| `make_pilot.py` | writes the stratified pilot question file |
| `run_lightrag_bench.py`, `patch_lightrag.py` | LightRAG through the official runner (env `lightrag`) |
| `score.py`, `score_launcher.py` | official scorer wrapper (clean-repo check, CPU launcher, shards, manifest) |
| `score_faithfulness.py`, `diagnose_faithfulness.py` | supplementary faithfulness score and its diagnosis |
| `aggregate.py` | per-type metrics, bootstrap CIs, paired differences, caveats → `summary/` |
| `make_timing.py` | full-run time and cost estimate from a pilot → `timing.json` |
| `make_report.py` | the 4Minds-style HTML report → `summary/report.html` |

## Results folders

| Folder | Content |
|---|---|
| `results/pilot/` | the pilot (5 systems), `summary/`, `timing.json` |
| `results/pilot/_*` | kept for audit: failed SYMI WebSocket attempt, RAG Engine run without context text, judge repeat test |
| `results/4minds/setup.json`, `results/rag_engine/setup.json` | the external resources that setup created |
| `results/lightrag/workspace/` | the LightRAG index (36 min, about $3 to build) |
| `results/_stopped_full_run_20261009/` | the stopped full run (not scored) |
| `results/_superseded_early_tests/` | tests made before the protocol was fixed |
| `results/audit/` | `audit.log`, step logs, patches, diagnostics. Records before 2026-10-09 16:07 UTC use the old paths (`GraphRag-Bench Medical/`). |

## Reproduce the pilot

```
./bench graphrag-bench setup_4minds eval systems/setup_4minds.py
./bench graphrag-bench setup_rag_engine eval systems/setup_rag_engine.py      # provisions Spanner (costs money hourly)
./bench graphrag-bench lightrag_index lightrag run_lightrag_bench.py --subset medical --index-only
P=(--subset medical --questions-file data/Questions/pilot_questions.json)
./bench graphrag-bench pilot_gemini eval systems/run_gemini.py $P --out-dir results/pilot/gemini --workers 10 --timeout 120
./bench graphrag-bench pilot_rag_engine eval systems/run_rag_engine.py $P --out-dir results/pilot/rag_engine --workers 10 --timeout 120
./bench graphrag-bench pilot_lightrag lightrag run_lightrag_bench.py $P --out-dir results/pilot/lightrag --workers 4
./bench graphrag-bench pilot_4minds_c eval systems/run_4minds.py --engine constellations $P --out-dir results/pilot/4minds_constellations --workers 4
./bench graphrag-bench pilot_4minds_s eval systems/run_4minds.py --engine symi $P --out-dir results/pilot/4minds_symi --workers 4
./bench graphrag-bench score_pilot_<system> eval score.py --system-dir results/pilot/<system>/medical
./bench graphrag-bench faith_pilot_<system> eval score_faithfulness.py --system-dir results/pilot/<system>/medical
./bench graphrag-bench timing_pilot eval make_timing.py --results results/pilot
./bench graphrag-bench aggregate_pilot eval aggregate.py --results results/pilot --label PILOT
./bench graphrag-bench report_pilot eval make_report.py --results results/pilot
```

The existing pilot folders have a settings lock; use a new `--out-dir` for a new pilot.

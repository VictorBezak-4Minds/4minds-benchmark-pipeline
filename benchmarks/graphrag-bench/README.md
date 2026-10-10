# GraphRAG-Bench (Medical)

**Status:** GPT-OSS-120B full run complete (2,062 Medical questions, 4 systems, scored on
2026-10-10; `configs/comparisons/gptoss.json`): [runs/2026-10-10_gptoss-full/summary/report.html](runs/2026-10-10_gptoss-full/summary/report.html).
First pilot complete (10 questions, 5 systems; `configs/comparisons/gemini.json`). A full run of
the Gemini matrix is **not approved**. A full run was started by mistake on 2026-10-09 and stopped
after about 2 minutes; its partial output is in `runs/2026-10-09_gemini-full_stopped/` and was not scored.

- Upstream: <https://github.com/GraphRAG-Bench/GraphRAG-Benchmark>, pinned at
  `fdbab5959b18c96532580877ffe27d112bccc0ec` in `upstream/`.
- Pilot report: [runs/2026-10-09_gemini-pilot/summary/report.html](runs/2026-10-09_gemini-pilot/summary/report.html)
  (tables in `runs/2026-10-09_gemini-pilot/summary/report.md`).

## Protocol

| Item | Value |
|---|---|
| Subset | Medical only: 2,062 questions, 1 corpus (Fact Retrieval 1,098, Complex Reasoning 509, Contextual Summarize 289, Creative Generation 166) |
| Questions and gold answers | `upstream/Datasets/Questions/medical_questions.json` (the local `data/Questions` copy is another release with 251 different answers) |
| Scoring | generation only: official `Evaluation/generation_eval.py`, run unchanged |
| Judge | gpt-4o-mini (snapshot gpt-4o-mini-2024-07-18), embeddings BAAI/bge-large-en-v1.5 |
| System prompt | Role and Goal of `upstream/Examples/run_lightrag.py`, for every system (`benchmark_profile.SYSTEM_PROMPT`) |
| Pilot sample | `data/Questions/pilot_questions.json`: 5/2/2/1 per type, seed 42 (`scripts/make_pilot.py`) |

## Systems

| Run subfolder | System | Adapter |
|---|---|---|
| `4minds_constellations` | 4Minds prod, Constellations, GPT-OSS-120B standard weights, prompt in the persona | `systems/run_4minds.py --engine constellations` |
| `4minds_symi` | 4Minds prod, SYMI (REST/SSE; no chunk text, so no faithfulness) | `systems/run_4minds.py --engine symi` |
| `gemini` | Gemini Developer API + File Search, top_k 5 | `systems/run_gemini.py` |
| `rag_engine` | Gemini + Vertex AI RAG Engine (europe-west4), top_k 5 | `systems/run_rag_engine.py` |
| `lightrag` | LightRAG 1.2.5 + Gemini through the official runner | `scripts/run_lightrag_bench.py` (benchmark-only adapter) |

### GPT-OSS-120B matrix (`configs/comparisons/gptoss.json`, results in `runs/2026-10-09_gptoss-pilot/` and `runs/2026-10-10_gptoss-full/`)

GPT-OSS-120B answers in every system, so only the retrieval changes. The three Bedrock systems
use backend `bedrock-gpt-oss-120b` (`pipeline/llm_backends.json`: temperature 0.3, 4,096 max
tokens, reasoning effort medium, the same as the 4Minds server).

| Run subfolder | System | Adapter |
|---|---|---|
| `4minds_constellations` | 4Minds prod, Constellations (reference) | `systems/run_4minds.py --engine constellations` |
| `gptoss_lightrag` | LightRAG 1.2.5, index built again with GPT-OSS, delimiter repair | `scripts/run_lightrag_bench.py --llm bedrock-gpt-oss-120b --repair-delimiters` |
| `gptoss_filesearch` | Gemini File Search (top_k 5, `cite_each`), then GPT-OSS | `systems/run_rag.py --retriever gemini_file_search` |
| `gptoss_norag` | GPT-OSS with the question only (baseline) | `systems/run_rag.py --retriever none` |

RAG Engine is not in this comparison (operator decision, 2026-10-09). Google refused
us-central1 (Serverless: "No available indexing project") and us-east4 (Spanner mode is
allowlist-only for new projects). In europe-west4, `retrieveContexts` failed with HTTP 500
("Failed to fetch corpus status from spanner") on about 60% of calls, the same fault as in
the QASPER pilot. The `vertex_rag_engine` retriever stays in the code for a later run.

```
P=(--subset medical --questions-file data/Questions/pilot_questions.json --llm bedrock-gpt-oss-120b)
./bench graphrag-bench preflight_llm_bedrock eval systems/preflight.py llm --llm bedrock-gpt-oss-120b
./bench graphrag-bench lightrag_index_gptoss lightrag run_lightrag_bench.py --subset medical --llm bedrock-gpt-oss-120b --index-only --repair-delimiters
./bench graphrag-bench gptoss_pilot_norag eval systems/run_rag.py $P --retriever none --out-dir runs/2026-10-09_gptoss-pilot/gptoss_norag --timeout 120
./bench graphrag-bench gptoss_pilot_filesearch eval systems/run_rag.py $P --retriever gemini_file_search --retrieval-instruction cite_each --out-dir runs/2026-10-09_gptoss-pilot/gptoss_filesearch --timeout 120
./bench graphrag-bench gptoss_pilot_lightrag lightrag run_lightrag_bench.py $P --repair-delimiters --out-dir runs/2026-10-09_gptoss-pilot/gptoss_lightrag --workers 4
./bench graphrag-bench gptoss_pilot_4minds eval systems/run_4minds.py --engine constellations --subset medical \
    --questions-file data/Questions/pilot_questions.json --out-dir runs/2026-10-09_gptoss-pilot/4minds_constellations --workers 4
./bench graphrag-bench score_gptoss_pilot_<system> eval score.py --system-dir runs/2026-10-09_gptoss-pilot/<system>/medical --shard-size 50
./bench graphrag-bench faith_gptoss_pilot_<system> eval score_faithfulness.py --system-dir runs/2026-10-09_gptoss-pilot/<system>/medical
./bench graphrag-bench timing_gptoss_pilot eval make_timing.py --matrix configs/comparisons/gptoss.json --run runs/2026-10-09_gptoss-pilot
./bench graphrag-bench aggregate_gptoss_pilot eval aggregate.py --matrix configs/comparisons/gptoss.json --run runs/2026-10-09_gptoss-pilot --label PILOT
./bench graphrag-bench report_gptoss_pilot eval make_report.py --run runs/2026-10-09_gptoss-pilot
```

If a step stops, run the same command again: answering resumes from `runs.jsonl`, scoring
from the complete shards, faithfulness from `faithfulness_json_fix.partial.jsonl`, and the
LightRAG index build from LightRAG's LLM cache. The full run used the same commands with
`--full` (no `--questions-file`), `--out-dir runs/2026-10-10_gptoss-full/<system>`, the workers and timeouts
of the matrix, and `score.py --shard-size 50 --parallel 8` with at most 3 reruns.

## GPT-OSS full result (2,062 questions)

| System | Answer correctness (95% CI) | 4Minds minus system | Median latency | Answer cost |
|---|---|---|---|---|
| GPT-OSS + File Search | 75.6 (74.5–76.7) | −5.5 (−6.8 to −4.3) | 15.4 s | $42.74 |
| GPT-OSS + LightRAG | 75.4 (74.5–76.5) | −5.4 (−6.7 to −4.0) | 4.4 s | $4.26 |
| 4Minds (Constellations) | 70.1 (69.0–71.3) | (reference) | 11.8 s | n/a |
| GPT-OSS (no RAG) | 40.8 (39.4–42.2) | +29.3 (+27.6 to +31.0) | 0.9 s | $0.24 |

4Minds is lower on Fact Retrieval (−6) and Complex Reasoning (−9), and equal on Contextual
Summarize and Creative Generation. Its median answers are about 3 times longer on the first
two types (356 and 1,129 characters, against about 105 and 380), see finding 1. Without the
21 incomplete File Search replies, the differences do not change (−5.3 and −5.9).

### Judge comparison: Claude Haiku 5.5 (`configs/comparisons/gptoss_judge-haiku.json`)

The same answers, scored again with another judge, so only the judge changes. The derived run
links the answer files of the source run (`pipeline/derive_run.py`) and writes its own scores.
Haiku 5.5 cannot use the official settings temperature 0 and top_p 1 (HTTP 400), so it runs at its
default sampling (`judge_drop_params` in `pipeline/llm_backends.json`). Haiku also puts its JSON
replies in a code fence, sometimes with a comment after it, which the official factuality parser
cannot read (factuality 0 for every answer), so the scorer uses the JSON inside the fence, in
memory (`judge_strip_code_fence`). Check a new judge with `diagnose_judge_format.py` before you
score with it, and check `not_json_replies` in the score manifests after. The key is in
`~/.config/anthropic/api_key` (mode 600).

```
H=(--judge anthropic-claude-haiku-5-5)
./bench graphrag-bench diagnose_<name> eval diagnose_judge_format.py --system-dir runs/<run>/<system>/medical $H --n 4
./bench graphrag-bench derive_<name> eval pipeline/derive_run.py --from runs/<source> --to runs/<YYYY-MM-DD>_<name> \
    --change "Judge: Claude Haiku 5.5 instead of gpt-4o-mini" --title "..."
./bench graphrag-bench score_<name>_<system> eval score.py --system-dir runs/<run>/<system>/medical $H --shard-size 50 --parallel 8
./bench graphrag-bench faith_<name>_<system> eval score_faithfulness.py --system-dir runs/<run>/<system>/medical $H
./bench graphrag-bench aggregate_<name> eval aggregate.py --matrix gptoss_judge-haiku --run runs/<run> [--label PILOT]
./bench graphrag-bench report_<name> eval make_report.py --run runs/<run>
```

## Pilot result (10 questions; not a conclusion)

| System | Answer correctness, all questions (95% CI) | Median latency | Pilot cost |
|---|---|---|---|
| Gemini + File Search | 89.9 (83.8–95.2) | 10.3 s | $0.15 |
| LightRAG + Gemini | 84.9 (76.3–92.5) | 10.9 s | $0.08 |
| Gemini + RAG Engine | 84.0 (75.8–91.7) | 8.4 s | $0.03 |
| 4Minds (Constellations) | 79.0 (66.5–90.5) | 11.3 s | n/a |
| 4Minds (SYMI) | 73.8 (56.7–89.9) | 10.8 s | n/a |

All intervals overlap. 10 questions cannot separate these systems.

Full-run estimate from the pilot (`runs/2026-10-09_gemini-pilot/timing.json`): about 4.7 h, limited by
4Minds at 4 workers (Constellations, then SYMI). Answer cost about $54 for the
three Gemini-based systems, plus the judge.

## Findings and fixes (apply them to future benchmarks too)

1. **4Minds answers are long.** Median about 1,000 characters against 200–270 for the Gemini
   systems, with the same "direct and concise" prompt. This lowers ROUGE-L and can lower
   answer correctness. It is product behaviour; it is reported, not changed.
2. **Official faithfulness is NaN for most answers.** The verdict prompt does not ask for
   JSON; gpt-4o-mini answers in prose. `score_faithfulness.py` adds a labelled
   "JSON-format fix" score (diff in `audit/patches/`, diagnosis in
   `audit/diagnostics/faithfulness_nan.json`).
3. **Faithfulness reads only 10,000 characters of context.** 4Minds multi-step retrieval
   returns up to 50 chunks. The 4Minds adapter stores chunks in 4Minds' own score order.
4. **The judge is not repeatable.** 4 of 10 answer-correctness scores changed when the same
   answers were scored again (`runs/2026-10-09_gemini-pilot/tests/judge-repeat`).
5. **Scoring is slow** (3 samples at a time). `score.py --shards N` runs N official scorer
   processes on parts of the predictions and merges them; the scores do not change.
   `--shard-size 50 --parallel 8` does the same with a fixed shard plan, and a rerun scores
   only the shards that are not complete.
6. **Upstream bugs:** the official LightRAG runner has 2 bugs in API mode (fixed in memory,
   diff in `audit/patches/`); LightRAG 1.2.5 needs the README context-return patch
   (`patch_lightrag.py`).
7. **System quirks:** the SYMI WebSocket rejects API keys (use REST); RAG Engine grounding
   chunks carry no text from the global endpoint (use `retrieveContexts`); us-central1 RAG
   Engine is allowlist-only for new projects; Gemini and RAG Engine requests can hang for
   300 s (use `--timeout 120`); the scorer crashes on Apple MPS (`score_launcher.py` hides MPS).
8. **4Minds metadata says "enhancing"** after the build is complete: the platform counts its
   own manifest file as one more ETL file. `setup_4minds.py` explains the readiness rule.
9. **GPT-OSS on Bedrock returns its reasoning in the answer text** (`<reasoning>` tags).
   `llm_backends.py` and `run_lightrag_bench.py` remove it. Without this, LightRAG would read
   the reasoning as entity and keyword output. GPT-OSS also damages LightRAG's `<|>` field
   delimiter (often `|>`): 34.6% of relationship records were rejected. `--repair-delimiters`
   repairs them in memory (loss 6.4%); check the rejection rate of every new extraction model.
10. **Gemini File Search returns only the cited chunks.** There is no search-only API, and
   `groundingChunks` holds the chunks that Gemini's answer cites (often 1), not the top_k
   chunks that the tool read. `--retrieval-instruction cite_each` makes Gemini cite every
   returned passage: 5 of 5 chunks for every one-search question in a 10-question check
   (`systems/preflight.py file-search` measures this).
11. **File Search can loop until its reply is empty.** In the GPT-OSS full run, 21 of 2,062
   File Search replies had no chunks and no normal finish reason (19 after about 400,000
   tokens of search results, 2 `MALFORMED_*`). The adapter accepted them, and GPT-OSS answered
   with an empty Knowledge Base. These rare questions also made the File Search cost $42.74,
   not the $17 from the pilot (the top 5% of questions used 61% of the search tokens). The
   retriever now retries such replies (`incomplete_response`) and records the billed tokens
   of failed attempts. A 3-question test passed 2 at the first attempt and failed 1 every
   time. The matrix check "Without incomplete File Search replies" gives the scores without
   these questions. Estimate File Search cost from a pilot with a margin for such outliers.
12. **The judge sometimes returns a TP, FP or FN item as plain text, not as an object.** The
   official scorer cannot read it and drops the sample. It happens with any answer, but more
   often with "I don't know" answers (No RAG: 24 of 2,062 at first), so a system with many of
   them gets a mean that is a little too high. Run `score.py` again for the incomplete
   shards; use the same number of reruns for every system (3 in the GPT-OSS run). The report
   shows the count in the "Not scored" column.

The caveats for a report are in its matrix file (`configs/comparisons/*.json`); the caveats that apply
to every comparison are `COMMON_CAVEATS` in `aggregate.py`.

## Layout

Find a result in this order: the benchmark (this folder), then the run (`runs/<YYYY-MM-DD>_<name>/`),
then the assets of that run. The list of runs, with title, status and report, is
[runs/README.md](runs/README.md). Each run has its own `README.md`.

| Folder | Content |
|---|---|
| `README.md`, `benchmark_profile.py` | the protocol, status and findings; the benchmark-specific values for the pipeline |
| `upstream/`, `data/` | the official repo at the pinned commit (never edited); local data (pilot question files) |
| `configs/comparisons/` | one file per version of the protocol: the systems, names, colors, reference, timing plan, caveats and sensitivity checks (`gemini.json`, `gptoss.json`) |
| `configs/scorers/` | scorers that are not part of the official protocol (`extra_v1.json` for `score_extra.py`) |
| `scripts/` | the benchmark scripts; `./bench` finds them by name (below) |
| `runs/<run>/` | one run: a folder per system (`<system>/medical/`), `summary/` (report), `timing.json`, and the files below |
| `runs/<run>/README.md`, `run.json`, `config.json` | made by `pipeline/run_readme.py`: what the run is, its status, systems, deviations, assets and the steps that made it; `run.json` is the part that you write; `config.json` is the copy of the comparison file that made the summary |
| `runs/<run>/tests/<name>/` | diagnostic tests on this run (not in its report) |
| `runs/<run>/extra/<name>/` | extra scores of this run's answers (for example `extra_v1_pilot/`) |
| `runs/<run>/_superseded_<reason>/`, `_failed_<reason>/` | system folders that were replaced or failed, kept for audit |
| `runs/<date>_<name>_stopped/` | a run that was stopped and not scored |
| `shared/` | what several runs use: `4minds/` and `rag_engine/` (`setup.json`: the external resources that setup made), `lightrag/` (indexes), `extra/` (shared inputs of the extra scorers) |
| `archive/` | output that belongs to no run (early tests) |
| `audit/` | `audit.log`, step logs, patches, diagnostics, `moves/`. Records before 2026-10-09 16:07 UTC use the paths `GraphRag-Bench Medical/`; older records use the old folder names (maps in `audit/moves/`; each run README follows them). |

The LightRAG indexes in `shared/lightrag/`:

| Index | Use |
|---|---|
| `workspace/` | Gemini (36 min, about $3 to build); `gemini.json` |
| `workspace_bedrock-gpt-oss-120b/` | the first GPT-OSS index (57 min, $1.43); kept, not used (35% of relationships rejected) |
| `workspace_bedrock-gpt-oss-120b_delimfix/` | rebuilt from the same LLM cache with `--repair-delimiters`; `gptoss.json` |

| Script (`scripts/`) | Purpose |
|---|---|
| `make_pilot.py` | writes the stratified pilot question file |
| `run_lightrag_bench.py`, `patch_lightrag.py` | LightRAG through the official runner (env `lightrag`) |
| `score.py`, `score_launcher.py` | official scorer wrapper (clean-repo check, CPU launcher, shards, manifest) |
| `score_faithfulness.py`, `diagnose_faithfulness.py` | supplementary faithfulness score and its diagnosis |
| `score_extra.py` | extra metrics from `configs/scorers/` |
| `aggregate.py` | per-type metrics, bootstrap CIs, paired differences, caveats → `summary/`, `config.json`, run README (`--matrix`) |
| `make_timing.py` | full-run time and cost estimate from a pilot → `timing.json` (`--matrix`) |
| `make_report.py` | the 4Minds-style HTML report → `summary/report.html` |

For a new version of the protocol (other systems, another model, a changed scorer), add a file
in `configs/comparisons/` and start a new run folder. Do not change a config that a run used:
the run keeps a copy with its sha256 in `config.json`, and its README shows a changed source.

## Reproduce the pilot

```
./bench graphrag-bench setup_4minds eval systems/setup_4minds.py
./bench graphrag-bench setup_rag_engine eval systems/setup_rag_engine.py      # provisions Spanner (costs money hourly)
./bench graphrag-bench lightrag_index lightrag run_lightrag_bench.py --subset medical --index-only
P=(--subset medical --questions-file data/Questions/pilot_questions.json)
./bench graphrag-bench pilot_gemini eval systems/run_gemini.py $P --out-dir runs/2026-10-09_gemini-pilot/gemini --workers 10 --timeout 120
./bench graphrag-bench pilot_rag_engine eval systems/run_rag_engine.py $P --out-dir runs/2026-10-09_gemini-pilot/rag_engine --workers 10 --timeout 120
./bench graphrag-bench pilot_lightrag lightrag run_lightrag_bench.py $P --out-dir runs/2026-10-09_gemini-pilot/lightrag --workers 4
./bench graphrag-bench pilot_4minds_c eval systems/run_4minds.py --engine constellations $P --out-dir runs/2026-10-09_gemini-pilot/4minds_constellations --workers 4
./bench graphrag-bench pilot_4minds_s eval systems/run_4minds.py --engine symi $P --out-dir runs/2026-10-09_gemini-pilot/4minds_symi --workers 4
./bench graphrag-bench score_pilot_<system> eval score.py --system-dir runs/2026-10-09_gemini-pilot/<system>/medical
./bench graphrag-bench faith_pilot_<system> eval score_faithfulness.py --system-dir runs/2026-10-09_gemini-pilot/<system>/medical
./bench graphrag-bench timing_pilot eval make_timing.py --matrix configs/comparisons/gemini.json --run runs/2026-10-09_gemini-pilot
./bench graphrag-bench aggregate_pilot eval aggregate.py --matrix configs/comparisons/gemini.json --run runs/2026-10-09_gemini-pilot --label PILOT
./bench graphrag-bench report_pilot eval make_report.py --run runs/2026-10-09_gemini-pilot
```

The existing pilot folders have a settings lock; use a new `--out-dir` for a new pilot.

# Benchmark hub

This folder is the starting point for every benchmark that compares **4Minds** with other
RAG systems. One pipeline runs all benchmarks. It sends each benchmark question to each
system, records everything for audit, scores the answers with the benchmark's own scorer,
and makes a report in the 4Minds style.

The question that the pipeline answers: *does 4Minds give output of similar quality to the
systems that our customers can use?*

Agents: read [AGENTS.md](AGENTS.md) before you do any work here.

## Benchmarks

| Benchmark | Folder | Status |
|---|---|---|
| GraphRAG-Bench (Medical) | [benchmarks/graphrag-bench](benchmarks/graphrag-bench/README.md) | Pilot complete (10 questions, 5 systems). Full run not approved. |

## Layout

```
Benchmark Datasets/
├── README.md               this file
├── AGENTS.md               rules for AI agents (and a checklist for people)
├── bench                   the entry point for every step (see "Run a step")
├── pipeline/               benchmark-agnostic core
│   ├── bench_common.py     run loop, resume, retries, readiness, audit files, full-run guard
│   └── run_logged.sh       records each step in the benchmark's audit log
├── systems/                adapters for the systems under test (shared by all benchmarks)
│   ├── setup_4minds.py     4Minds prod: dataset + persona + model, waits for the graph build
│   ├── run_4minds.py       4Minds Constellations (WebSocket) and SYMI (REST/SSE)
│   ├── run_gemini.py       Gemini Developer API + File Search
│   ├── setup_rag_engine.py Vertex AI RAG Engine corpus (europe-west4)
│   ├── run_rag_engine.py   Gemini + RAG Engine retrieval
│   └── cleanup_rag_engine.py  deletes the corpus and stops Spanner billing
├── envs/                   Python environments (.venv-eval, .venv-lightrag) and setup_envs.sh
└── benchmarks/
    └── <benchmark>/
        ├── benchmark_profile.py   the benchmark-specific part (see "Profile contract")
        ├── README.md              protocol, status, findings, caveats
        ├── upstream/              the official repo, pinned to one commit, never edited
        ├── data/                  local data (pilot question files, corpus copies)
        ├── results/               all output, including results/audit/
        └── *.py                   scorer wrappers, aggregation, report, benchmark-only adapters
```

The split between `pipeline/`, `systems/` and `benchmarks/` is the main idea:

- **pipeline/** does not know about any benchmark. It reads the active benchmark profile.
- **systems/** knows how to talk to one system (4Minds, Gemini, ...). It does not know the
  questions or the scorer. It gets names, the corpus and the system prompt from the profile.
- **benchmarks/<name>/** knows the questions, the corpus, the scorer and the metrics.

Some code is still in a benchmark folder because only one benchmark uses it now:
`aggregate.py`, `make_report.py` and `make_timing.py` in `benchmarks/graphrag-bench/` have
GraphRAG-Bench metric sets and text. When a second benchmark needs a report, move the
shared parts (bootstrap statistics, the 4Minds HTML style) to `pipeline/` and keep the
benchmark text in the benchmark folder. Do not generalize before the second benchmark
shows what is really shared.

## Run a step

Every step goes through `./bench`. It selects the benchmark and the Python environment,
sets `PYTHONPATH`, runs the step in the benchmark folder and records it in the audit log.

```
./bench <benchmark> <step-name> <env> <script> [args...]
./bench --bg <benchmark> <step-name> <env> <script> [args...]    # detached; keeps the Mac awake
```

- `benchmark`: a folder in `benchmarks/` (for example `graphrag-bench`).
- `step-name`: a short name for the audit log (for example `pilot_4minds_constellations`).
- `env`: `eval` or `lightrag` (the folder `envs/.venv-<env>`).
- `script`: a path from the hub root (`systems/run_4minds.py`) or from the benchmark folder (`score.py`).

Relative paths in the arguments are relative to the benchmark folder.

Examples (GraphRAG-Bench pilot):

```
./bench graphrag-bench pilot_4minds_constellations eval systems/run_4minds.py --engine constellations \
    --subset medical --questions-file data/Questions/pilot_questions.json \
    --out-dir results/pilot/4minds_constellations --workers 4
./bench graphrag-bench score_pilot_4minds eval score.py --system-dir results/pilot/4minds_constellations/medical
./bench graphrag-bench aggregate_pilot eval aggregate.py --results results/pilot --label PILOT
./bench graphrag-bench report_pilot eval make_report.py --results results/pilot
```

Every runner accepts `--dry-run`: it prints the first request and sends nothing.

## The run lifecycle

Use these steps for every benchmark and every system.

1. **Setup.** Load the benchmark corpus into each system (`systems/setup_*.py`).
2. **Readiness.** Each runner checks that the system finished ingestion (ETL) before it
   sends a question. If ingestion is not complete, the runner stops.
3. **Pilot.** Run a small stratified sample (`--questions-file` or `--sample`). Score it.
   Look at the answers, the contexts and the scores. Fix problems in the pipeline.
4. **Estimate.** Calculate the time and cost of the full run from the pilot
   (for example `make_timing.py`).
5. **Approval.** The operator decides if a full run is necessary. Without approval,
   do not run the full set. The runners stop unless you give `--full`.
6. **Full run, scoring, aggregation, report.**
7. **Cleanup.** Stop resources that cost money (see "Cloud resources").

## Output of a run

A runner writes to `results/<...>/<system>/<subset>/`:

| File | Content |
|---|---|
| `run_config.json` | the settings; a second run with different settings stops (no mixed results) |
| `runs.jsonl` | one line per question attempt: status, attempts, latency, usage, prediction |
| `raw.jsonl` | the raw response of each system call |
| `predictions.json` | the answers in the format that the benchmark scorer reads |
| `manifest.json` | command, settings, readiness state, input hashes, code hashes, package versions, summary |

A stopped run continues where it stopped (resume from `runs.jsonl`).
`results/audit/audit.log` has one JSON line for each event, in time order.
`results/audit/steps/` has the full console output of each step.
`results/audit/patches/` has a diff for each change to upstream code that the pipeline makes in memory.

## Profile contract

Each `benchmarks/<name>/benchmark_profile.py` defines:

| Name | Meaning |
|---|---|
| `TITLE` | display name |
| `RESOURCE_NAME`, `RESOURCE_DESCRIPTION` | names for datasets/corpora that setup scripts create in external systems |
| `SUBSETS` | allowed values of `--subset` |
| `QUESTION_FILES` | `{subset: path}` of the official question files |
| `CORPUS_FILE` | the corpus file that setup scripts upload |
| `SYSTEM_PROMPT` | the prompt that every system must use |
| `question_key(q)` | a unique key per question (resume and pairing) |
| `select_questions(questions, subset, sample)` | subset filter and `--sample` |
| `prediction(q, answer, contexts)` | one item of `predictions.json`; must have `generated_answer` and `context` |
| `UPSTREAM_REPO`, `UPSTREAM_COMMIT` | optional: the pinned official repo |
| `GEMINI_FILE_SEARCH_STORE` | optional: used by `systems/run_gemini.py` |

Known limits of the current contract (change them when a benchmark needs it):

- One corpus file per benchmark. A benchmark with many documents needs a list of files.
- `systems/run_gemini.py` filters retrieval by the question field `source`.
- The prediction format follows GraphRAG-Bench (answer + context list). Benchmarks that
  score retrieval also need the IDs of the retrieved documents.

## Add a benchmark

1. Clone the official repo into `benchmarks/<name>/upstream/` and record the commit.
2. Write `benchmark_profile.py` (see the contract) and `README.md`.
3. Write a scorer wrapper that runs the official scorer unchanged. If the official code
   needs a change, apply it in memory and write the diff to `results/audit/patches/`.
4. Make a stratified pilot question file in `data/`.
5. Run the lifecycle above, from setup to pilot report. Stop and ask before a full run.

## Credentials

Keys are in files with mode 600. Code reads them with `bench_common.load_key(provider)`.

| Provider | File |
|---|---|
| 4Minds (prod API key) | `~/.config/4minds/api_key` |
| Gemini Developer API | `~/.config/gemini/api_key` |
| OpenAI (judge) | `~/.config/openai/api_key` |
| Google Cloud (Vertex AI) | application default credentials (`gcloud auth application-default login`) |

Never print a key, put it in a URL or a command line, or write it to a log.

## Cloud resources

Resources that exist now, and what they cost:

| Resource | Cost while not in use | Notes |
|---|---|---|
| 4Minds dataset 4033, model 3592, persona 1275 (prod) | none | GraphRAG-Bench Medical. Many benchmark conversations also exist. |
| Gemini File Search store `graphragbench-9lax22b99qlk` | storage only | GraphRAG-Bench corpus |
| RAG Engine, project `minds-vs-gemini-benchmark`, europe-west4 | none | Unprovisioned on 2026-10-09; no corpus. `setup_rag_engine.py` provisions Spanner Basic again, which costs money every hour. |
| RAG Engine us-central1 config (Serverless), Vector Search API | none | |
| LightRAG index | none (local) | `benchmarks/graphrag-bench/results/lightrag/workspace/` |

## Environments

`envs/setup_envs.sh` creates the environments. Use `envs/.venv-<env>/bin/python -m pip`
to install packages: the `pip` launcher scripts keep the absolute path of the folder where
they were made. Add a new environment when a benchmark needs packages that conflict with
the existing ones.

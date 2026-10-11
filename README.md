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
| QASPER (answer-only) | [benchmarks/qasper](benchmarks/qasper/README.md) | Pilot complete (25 questions, 4 systems; RAG Engine blocked). Full run not approved. |
| EnterpriseRAG-Bench (metrics-based) | [benchmarks/enterpriserag-bench](benchmarks/enterpriserag-bench/README.md) | Pilot complete (50 questions, 5 systems, 10,000-document slice). Full run not approved. |
| 4Minds RAG (our metrics on saved answers) | [benchmarks/4minds-rag](benchmarks/4minds-rag/README.md) | RAGAS, DeepEval and document P/R/F1 on the EnterpriseRAG-Bench pilot answers; two judge versions (gpt-4o-mini, Claude Haiku 5.5). |

## Layout

```
Benchmark Datasets/
├── README.md               this file
├── AGENTS.md               rules for AI agents (and a checklist for people)
├── bench                   the entry point for every step (see "Run a step")
├── metrics_cheatsheet.html the metrics of each benchmark: why and how (from pipeline/make_cheatsheet.py)
├── pipeline/               benchmark-agnostic core
│   ├── bench_common.py     run loop, resume, retries, readiness, audit files, full-run guard
│   ├── llm_backends.json   named LLM backends: endpoint, auth method, model, generation params, prices
│   ├── llm_backends.py     one chat() for all backends; Bedrock tokens made in memory from an AWS profile
│   ├── make_cheatsheet.py  writes metrics_cheatsheet.html; edit its text when a metric changes
│   ├── score_extra.py      scorers outside an official protocol (RAGAS, DeepEval, document P/R/F1) on saved answers
│   ├── derive_run.py       a new run that links the answers of a run (also of another benchmark) to change only the scorer
│   ├── run_readme.py       writes the run README and runs/README.md from run.json, config.json and the audit log
│   ├── report_html.py      4Minds HTML style for reports: CSS, logo, system colors, bar with CI,
│   │                       quality vs. median latency scatter (plotly.js 4.1.2 from cdn.plot.ly, SRI-pinned)
│   └── run_logged.sh       records each step in the benchmark's audit log
├── systems/                adapters for the systems under test (shared by all benchmarks)
│   ├── setup_4minds.py     4Minds prod: dataset + persona + model, waits for the graph build
│   ├── run_4minds.py       4Minds Constellations (WebSocket) and SYMI (REST/SSE)
│   ├── setup_gemini.py     Gemini File Search store: creates it and uploads the corpus
│   ├── run_gemini.py       Gemini Developer API + File Search
│   ├── run_lightrag.py     LightRAG 1.2.5 + Gemini or a backend (--llm): builds the local index (--index-only) and answers
│   ├── lightrag_hooks.py   in-memory LightRAG hooks: usage, Bedrock token, <reasoning> removal, GPT-OSS delimiter repair, document IDs
│   ├── setup_langchain.py  LangChain vector index (FAISS) of the profile's documents
│   ├── setup_graphrag.py   Microsoft GraphRAG 3.3.0 index (fast method) of the profile's documents
│   ├── graphrag_hooks.py   in-memory GraphRAG config and LiteLLM hooks: Bedrock token, <reasoning> removal, JSON repair, usage
│   ├── setup_rag_engine.py Vertex AI RAG Engine: provisions Spanner Basic if necessary, creates the corpus (--location)
│   ├── run_rag_engine.py   Gemini + RAG Engine retrieval
│   ├── cleanup_rag_engine.py  deletes the corpus and stops Spanner billing
│   ├── setup_ragflow.py    self-hosted RAGFlow: one dataset, one file per document, waits for the parse
│   ├── retrievers.py       retrieval only: none, gemini_file_search, vertex_rag_engine, langchain_vector, graphrag_local, ragflow
│   ├── run_rag.py          any retriever + any LLM backend (--retriever, --llm)
│   └── preflight.py        one-request checks: LLM backend, Gemini key project, File Search chunk count
├── envs/                   Python environments (.venv-eval, .venv-lightrag, .venv-erag, .venv-graphrag, .venv-extra) and setup_envs.sh
└── benchmarks/
    └── <benchmark>/
        ├── README.md              protocol, status, findings, caveats
        ├── benchmark_profile.py   the benchmark-specific part (see "Profile contract")
        ├── upstream/              the official repo, pinned to one commit, never edited
        ├── data/                  local data (pilot question files, corpus copies)
        ├── configs/
        │   ├── comparisons/       one file per version of the protocol (systems, caveats, checks)
        │   └── scorers/           scorers that are not in the official protocol
        ├── scripts/               scorer wrappers, aggregation, report, benchmark-only adapters
        ├── runs/                  README.md: the list of runs (generated)
        │   └── <YYYY-MM-DD>_<name>/
        │       ├── README.md      generated: status, config, systems, deviations, assets, steps
        │       ├── run.json       you write it: title, purpose, status, notes
        │       ├── config.json    copy of the comparison config that made the summary (with sha256)
        │       ├── <system>/<subset>/   answers, logs, scores of one system
        │       ├── summary/       scores.json, report.md, report.html
        │       ├── tests/<name>/  diagnostic tests on this run
        │       ├── extra/<name>/  extra scores of this run's answers
        │       └── _superseded_<reason>/  replaced system folders, kept for audit
        ├── shared/                what several runs use: cloud resource IDs, indexes, shared scorer inputs
        ├── archive/               output that belongs to no run
        └── audit/                 audit log, step logs, patches, diagnostics, moves/
```

Find a result in this order: the benchmark, then the run, then the assets of the run. The
layout is in `bench_common` (`RUNS`, `SHARED`, `CONFIGS`, `ARCHIVE`, `AUDIT_DIR`); scripts use
these, not literal paths. `./bench` finds a script by its name in `scripts/`.
`pipeline/run_readme.py` writes the run README and the run list; `aggregate.py` and
`make_report.py` call it, and you can run it alone for a run with no summary.

The split between `pipeline/`, `systems/` and `benchmarks/` is the main idea:

- **pipeline/** does not know about any benchmark. It reads the active benchmark profile.
- **systems/** knows how to talk to one system (4Minds, Gemini, ...). It does not know the
  questions or the scorer. It gets names, the corpus and the system prompt from the profile.
- **benchmarks/<name>/** knows the questions, the corpus, the scorer and the metrics.

Each benchmark has its own `aggregate.py` and `make_report.py`, because the metrics and the
text are different. The HTML style is shared: `pipeline/report_html.py`. Every benchmark
writes `runs/<run>/summary/report.html` as the final result. Move more code to
`pipeline/` only when two benchmarks use the same code (the bootstrap is still a copy in
each `aggregate.py`).

### Configuration, not code

- **LLM backend** (`pipeline/llm_backends.json`): to answer with another model or host, add
  a backend entry and pass `--llm <name>`. Do not put a model ID or URL in a runner.
- **Judge** (`pipeline/llm_backends.json`, GraphRAG-Bench): `score.py --judge <backend>` and
  `score_faithfulness.py --judge <backend>`; the default `openai-gpt-4o-mini` is the official judge.
  A backend's `judge_drop_params` are removed from each judge request, a backend with
  `judge_strip_code_fence` has the JSON taken out of a code-fenced reply, and the judge tokens and
  cost go to the score manifest (`pipeline/judge_hooks.py`). A comparison file names its judge
  (`"judge"`), and `aggregate.py` stops if a system was scored by another judge. To change only
  the judge, start a new run with the same answers: `pipeline/derive_run.py`.
  `pipeline/score_extra.py` takes the judge from its scorer config: `{"provider": "backend",
  "backend": <name>}` uses the same backend entry and the same request and reply fixes.
- **Retriever** (`systems/retrievers.py`): `systems/run_rag.py --retriever <name> --llm <name>`
  combines any retriever with any backend. A new retriever is one class with `settings()`,
  `readiness()`, `retrieve()` and `cost()`.
- **Comparison** (`benchmarks/<name>/configs/comparisons/*.json`, GraphRAG-Bench): the systems of one
  report, their names, colors, the reference system, the timing plan, the caveats and the
  sensitivity checks (scores again without a set of questions; rules in
  `aggregate.SENSITIVITY_RULES`). `aggregate.py --matrix` and `make_timing.py --matrix` read it.

## Run a step

Every step goes through `./bench`. It selects the benchmark and the Python environment,
sets `PYTHONPATH`, runs the step in the benchmark folder and records it in the audit log.

```
./bench <benchmark> <step-name> <env> <script> [args...]
./bench --bg <benchmark> <step-name> <env> <script> [args...]    # detached; keeps the Mac awake
```

**Warning: do not use `--bg` from an agent shell.** The agent tool stops the process group
when its shell call ends, and this also stops `nohup` jobs. Two steps stopped this way
(audit event `step_killed`). Run long steps in a terminal that stays open.

- `benchmark`: a folder in `benchmarks/` (for example `graphrag-bench`).
- `step-name`: a short name for the audit log (for example `pilot_4minds_constellations`).
- `env`: `eval`, `lightrag` or `erag` (the folder `envs/.venv-<env>`).
- `script`: a path from the hub root (`systems/run_4minds.py`) or from the benchmark folder (`score.py`).

Relative paths in the arguments are relative to the benchmark folder.

Examples (GraphRAG-Bench pilot):

```
./bench graphrag-bench pilot_4minds_constellations eval systems/run_4minds.py --engine constellations \
    --subset medical --questions-file data/Questions/pilot_questions.json \
    --out-dir runs/2026-10-09_gemini-pilot/4minds_constellations --workers 4
./bench graphrag-bench score_pilot_4minds eval score.py --system-dir runs/2026-10-09_gemini-pilot/4minds_constellations/medical
./bench graphrag-bench aggregate_pilot eval aggregate.py --matrix configs/comparisons/gemini.json \
    --run runs/2026-10-09_gemini-pilot --label PILOT
./bench graphrag-bench report_pilot eval make_report.py --run runs/2026-10-09_gemini-pilot
```

Every runner accepts `--dry-run`: it prints the first request and sends nothing.
Before a new backend or retriever is used in a run, check it with one request:
`./bench <benchmark> preflight_llm eval systems/preflight.py llm --llm <backend>`.

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

A runner writes to `runs/<YYYY-MM-DD>_<comparison>/<system>/<subset>/`:

| File | Content |
|---|---|
| `run_config.json` | the settings; a second run with different settings stops (no mixed results) |
| `runs.jsonl` | one line per question attempt: status, attempts, latency, usage, prediction |
| `raw.jsonl` | the raw response of each system call |
| `predictions.json` | the answers in the format that the benchmark scorer reads |
| `manifest.json` | command, settings, readiness state, input hashes, code hashes, package versions, summary |

A stopped run continues where it stopped (resume from `runs.jsonl`).
`audit/audit.log` has one JSON line for each event, in time order.
`audit/steps/` has the full console output of each step.
`audit/patches/` has a diff for each change to upstream code that the pipeline makes in memory.

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
| `prediction(q, answer, contexts, document_ids=None)` | one item of `predictions.json`; must have `generated_answer` and `context`. A runner gives `document_ids` only when its result has them |
| `UPSTREAM_REPO`, `UPSTREAM_COMMIT` | optional: the pinned official repo |
| `GEMINI_FILE_SEARCH_STORE` | optional: used by `systems/run_gemini.py` |
| `corpus_documents()` | optional: the corpus as a list of documents (`dsid`, `title`, `text`). The setup scripts of LangChain, GraphRAG, LightRAG and 4Minds then load one document per item, with its ID, instead of `CORPUS_FILE` (which is then the manifest of the list) |
| `messages(q, contexts)` | optional: the chat messages for `systems/run_rag.py`, when the benchmark has its own prompt layout. Without it: `SYSTEM_PROMPT` as the system message and the contexts in a "Knowledge Base" user message |
| `EXTRA_QUESTION_TYPES` | optional: the `question_type` values that a `pipeline/score_extra.py` config can select |
| `extra_rows(predictions, questions_file)` | optional: the `pipeline/score_extra.py` rows (answer joined with its gold answer, evidence and gold document IDs). Without it, `predictions.json` must have these fields |

A runner result can have `document_ids` (the IDs of the retrieved documents, in rank order).
Benchmarks that score retrieval (EnterpriseRAG-Bench) need them; the others ignore them.

Known limits of the current contract (change them when a benchmark needs it):

- `systems/run_gemini.py` filters retrieval by the question field `source`.
- `systems/run_gemini.py` and `run_rag_engine.py` do not use `corpus_documents()` yet.

## Add a benchmark

1. Clone the official repo into `benchmarks/<name>/upstream/` and record the commit.
2. Write `benchmark_profile.py` (see the contract) and `README.md`.
3. Write a scorer wrapper that runs the official scorer unchanged. If the official code
   needs a change, apply it in memory and write the diff to `audit/patches/`.
4. Make a stratified pilot question file in `data/`.
5. Write `aggregate.py` and `make_report.py` (HTML report with `pipeline/report_html.py`).
   Add the metrics to `pipeline/make_cheatsheet.py` and run it.
6. Run the lifecycle above, from setup to the pilot HTML report. Stop and ask before a full run.

## Credentials

Keys are in files with mode 600. Code reads them with `bench_common.load_key(provider)`.

| Provider | File |
|---|---|
| 4Minds (prod API key) | `~/.config/4minds/api_key` |
| Gemini Developer API | `~/.config/gemini/api_key` |
| OpenAI (judge) | `~/.config/openai/api_key` |
| RAGFlow (self-hosted server API key) | `~/.config/ragflow/api_key`. The embedding key of the server is set in the RAGFlow web page (Model providers), and the server keeps it in its own database. |
| Google Cloud (Vertex AI) | application default credentials (`gcloud auth application-default login`) |
| Amazon Bedrock | the AWS profile in the backend's `auth.profile` (now `bedrock`, region us-east-1). No key file: `llm_backends.py` makes a short-term Bedrock token in memory and makes it again before it expires. |

Never print a key, put it in a URL or a command line, or write it to a log.

For AWS, short-term credentials from `aws login --profile bedrock` are better than a
long-term access key in `~/.aws/credentials`. Give the IAM identity only
`bedrock:InvokeModel` (and `bedrock:CallWithBearerToken`) on the models in `llm_backends.json`.

## Cloud resources

Resources that exist now, and what they cost:

| Resource | Cost while not in use | Notes |
|---|---|---|
| 4Minds dataset 4033, model 3592, persona 1275 (prod) | none | GraphRAG-Bench Medical. Many benchmark conversations also exist. |
| Gemini File Search store `graphragbench-9lax22b99qlk` | storage only | GraphRAG-Bench corpus |
| 4Minds dataset 4039, model 3598, persona 1283 (prod) | none | QASPER pilot slice. |
| Gemini File Search store `qaspertestpilot-jva5no5yqkow` | storage only | QASPER pilot slice |
| RAG Engine, project `minds-vs-gemini-benchmark`, europe-west4 and us-east4 | none | Both unprovisioned on 2026-10-09; no corpus. us-east4 was on Spanner Basic with no corpus (probably since the September attempts) until then. `setup_rag_engine.py` provisions Spanner Basic, which costs money every hour. Run `cleanup_rag_engine.py --location <region>` after use, and check every region you tried. |
| RAG Engine us-central1 config (Serverless), Vector Search API | none | Serverless corpus creation fails: "No available indexing project" (Sep and Oct 2026). |
| 4Minds dataset 4046, model 3604, persona 1291 (prod) | none | EnterpriseRAG-Bench pilot slice (10,000 files, one per document). |
| LightRAG indexes | none (local) | `benchmarks/<benchmark>/shared/lightrag/workspace/` (Gemini), `workspace_<llm backend>/` (others) |
| LangChain FAISS indexes | none (local) | `benchmarks/<benchmark>/shared/langchain/<resource name>/` (EnterpriseRAG-Bench pilot slice) |
| RAGFlow v0.27.2 server (Docker Compose in WSL2 on the operator's Windows PC) | none (local); embedding calls to OpenAI during the parse | EnterpriseRAG-Bench pilot slice (`shared/ragflow/setup.json`). WSL in NAT mode (mirrored mode did not pass traffic into WSL on this PC); a Windows port proxy sends `192.168.1.230:9380` to `127.0.0.1:9380`, and the firewall rule `RAGFlowAPI-LAN` opens only that port to `192.168.1.0/24` (Private profile). If the PC address changes, update both. Stop it with `docker compose -f docker-compose.yml down` in `~/ragflow/docker`. |
| GraphRAG indexes | none (local) | `benchmarks/<benchmark>/shared/graphrag/<resource name>/` (EnterpriseRAG-Bench pilot slice; `_first<N>` folders are cost tests) |

**RAG Engine check:** "ACTIVE" in the control plane does not prove that queries work. In the
QASPER pilot, europe-west4 returned HTTP 500 "Failed to fetch corpus status from spanner" for
3 new corpora. Send one real retrieval query before a run.

## Environments

`envs/setup_envs.sh` creates the environments. Use `envs/.venv-<env>/bin/python -m pip`
to install packages: the `pip` launcher scripts keep the absolute path of the folder where
they were made. Add a new environment when a benchmark needs packages that conflict with
the existing ones.

# Rules for agents in the benchmark hub

Read [README.md](README.md) first: it explains the layout, `./bench`, the run lifecycle
and the profile contract. These rules are mandatory.

## The operator

- The operator prefers to learn. Explain what you do and why, so the operator can do it next time.
- Write operator-facing text in ASD-STE100 Simplified Technical English.
- Do only the scope that the operator approved. If a plan exists, follow it. If a step is
  not in the plan, ask first.

## Runs and cost

- **Never run a full question set without explicit operator approval for that run.**
  Pilots use `--questions-file` or `--sample`. The runners stop without `--full`. Do not
  add `--full` on your own decision, also not when an estimate says "it fits in today".
- After a pilot: report the results and the time and cost estimate, then stop and ask.
- Start every step with `./bench` so that the audit log records it. Do not call the
  Python scripts directly.
- Check readiness before testing: every system must finish ingestion (ETL) first. The
  runners check this; do not bypass the check.
- Before you leave a paid resource on, ask the operator. Spanner (RAG Engine) costs money
  every hour. `systems/cleanup_rag_engine.py` stops it.

## Protocol integrity

- Never edit `benchmarks/*/upstream/`. It is the official repo at a pinned commit. If the
  official code needs a fix, apply it in memory and write the diff to
  `audit/patches/`. Keep the official result too, and label the fixed one.
- Use the same system prompt, questions and scorer settings for all systems in a comparison.
- Do not delete results. A superseded or failed system folder inside a run goes to
  `_superseded_<reason>/` or `_failed_<reason>/` in that run; a stopped run gets the suffix
  `_stopped`; output that belongs to no run goes to `archive/<date>_<reason>/`. Write an
  audit event (a `move` event and a map in `audit/moves/`).
- Benchmark layout (`bench_common.RUNS`, `SHARED`, `CONFIGS`, `ARCHIVE`, `AUDIT_DIR`): one run goes
  to `runs/<YYYY-MM-DD>_<name>/<system>/`; tests on a run to `runs/<run>/tests/<name>/`; extra
  scores of a run to `runs/<run>/extra/<name>/`; cloud resource IDs, indexes and shared scorer
  inputs to `shared/`; scripts to `scripts/`; comparison and scorer configs to `configs/`.
  For a new run, write `runs/<run>/run.json` (title, purpose, status) with
  `pipeline/run_readme.py --title ... --status ...`; it also writes the run README and
  `runs/README.md`. Do not edit a generated README. The layout changed on 2026-10-10 (twice);
  older audit records use the old paths (maps in `audit/moves/`).
- git ignores run data (`.gitignore`): `shared/`, `archive/` and all of `runs/` except `README.md`,
  `run.json`, `config.json`, `timing.json`, `blocked.json` and `summary/`. To track one more small
  file type, add a `!` line; do not track answers, logs, score shards or indexes.
- One run folder = one set of settings (`run_config.json`). For new settings, use a new `--out-dir`.
- Models, hosts and the systems of a comparison are configuration: `pipeline/llm_backends.json`,
  `systems/retrievers.py` and `benchmarks/<name>/configs/comparisons/*.json`. Do not hard-code them in a runner,
  `aggregate.py` or `make_report.py`. When you change aggregation code, rebuild an old report
  and check that it is byte-identical (except the generated time); put the old files back after the check.
- Full runs score with `score.py --shard-size 50 --parallel 8`, so a failure does not restart the scoring.
- A change after answering (judge, scorer) is a new run that links the same answers
  (`pipeline/derive_run.py`). Do not answer again: new answers change a second variable.
  Do not score one folder with two judges; `score.py` and `score_faithfulness.py` stop if you try.

## Credentials and data

- Keys are in `~/.config/<provider>/api_key` (mode 600). Read them inside Python with
  `bench_common.load_key()`.
- Never print a key, put it in a URL or a command line, or write it to a log or to chat.
  Show only the length and the first characters if you must identify a key.
- Amazon Bedrock: credentials come only from the AWS profile in the backend entry. The Bedrock
  token stays in memory (`llm_backends.py`); never write it to a file, a log or an environment
  variable. Do not read `~/.aws/credentials`. Ask the operator before `aws login` or any IAM change.
- 4Minds: use prod with the API key (no JWT). Use at most 4 concurrent workers on prod.
  Do not change datasets, models or personas that the benchmark did not create.
  Do not send scrape URLs to 4Minds.

## Known traps

- `/Users/victorbezak/Documents/Benchmark Datasets` is outside the agent sandbox. Shell
  commands that write here need full permissions.
- zsh does not split a variable into words: use an array (`P=(--a 1 --b 2)`) for argument lists.
- Background Python output is buffered unless `PYTHONUNBUFFERED=1` (`./bench` sets it).
- The LLM judge is not fully repeatable at temperature 0. Do not draw conclusions from
  single-question scores or from 10-question pilots.
- Judge context limits: GraphRAG-Bench faithfulness reads only the first 10,000 characters of
  context, so the order of stored chunks matters.
- Requests can hang. Use a timeout shorter than the default 300 s on full runs (for example `--timeout 120`).
- GPT-OSS on Bedrock puts its reasoning in `<reasoning>...</reasoning>` inside the answer text.
  `llm_backends.chat()` and the LightRAG driver remove it; any new caller must remove it too.
- Gemini File Search has no search-only API: `groundingChunks` holds only the chunks that
  Gemini's answer cites, not all chunks that the tool read (`systems/preflight.py file-search`).
- An HTTP 200 reply is not always a result. A File Search reply with no chunks and no normal
  finish reason is an error to retry (`retrievers.COMPLETE_FINISH_REASONS`). Check "no context"
  counts after every run; a mean cost from a 10-question pilot can be 2.5 times too low.
- `score.py` exits 1 when the judge could not score some samples (a format error in the judge
  output; more frequent with "I don't know" answers). Rerun it for the incomplete shards, with
  the same rerun limit for every system.
- Claude 4.7 and later models (Haiku 5.5 included) return HTTP 400 for `temperature` below 1 or
  `top_p` other than 0.99, so they cannot use the official judge settings. Their backend entry
  lists `judge_drop_params`; `judge_hooks.preflight()` checks a judge before scoring starts.
- "0 failed samples" does not prove that the judge replies were read. The GraphRAG-Bench
  factuality step parses with plain `json.loads` and silently gives 0 on failure; Claude puts
  its JSON in a code fence, so answer correctness falls to 0.25 × similarity (about 23). Before
  a new judge is used, run `scripts/diagnose_judge_format.py` (with `--repeat 3` on a long
  answer: Haiku sometimes adds a comment after the fence); if it needs a fix, set
  `judge_strip_code_fence` in its backend entry and add a caveat to the comparison file. After
  scoring, check `not_json_replies` in the judge usage of each score manifest.
- GraphRAG-Bench `upstream/` commits `.pyc` files. Runs change them; `score.py` ignores
  `__pycache__` and `.DS_Store` in its clean-repo check.

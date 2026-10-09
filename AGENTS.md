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
  `results/audit/patches/`. Keep the official result too, and label the fixed one.
- Use the same system prompt, questions and scorer settings for all systems in a comparison.
- Do not delete results. Move superseded or stopped output to `results/_superseded_<reason>/`
  or `results/_stopped_<reason>/` and write an audit event.
- One run folder = one set of settings (`run_config.json`). For new settings, use a new `--out-dir`.

## Credentials and data

- Keys are in `~/.config/<provider>/api_key` (mode 600). Read them inside Python with
  `bench_common.load_key()`.
- Never print a key, put it in a URL or a command line, or write it to a log or to chat.
  Show only the length and the first characters if you must identify a key.
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
- GraphRAG-Bench `upstream/` commits `.pyc` files. Runs change them; `score.py` ignores
  `__pycache__` and `.DS_Store` in its clean-repo check.

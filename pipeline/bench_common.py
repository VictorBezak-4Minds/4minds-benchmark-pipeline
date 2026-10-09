"""Benchmark-agnostic core of the pipeline.

Each system adapter supplies a readiness check and an `ask(question)` function. This module
does the rest: question loading, the settings lock, resume from runs.jsonl, retries, the
audit files (runs.jsonl, raw.jsonl, manifest.json, results/audit/audit.log) and
predictions.json.

The benchmark-specific part (question files, corpus, system prompt, prediction format)
comes from benchmarks/<BENCHMARK>/benchmark_profile.py. ./bench sets BENCHMARK and
PYTHONPATH; see the README.md in the hub root.
"""
import argparse
import hashlib
import importlib
import json
import os
import platform
import random
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

HUB = Path(__file__).resolve().parents[1]
BENCHMARK = os.environ.get("BENCHMARK")
if not BENCHMARK:
    sys.exit("BENCHMARK is not set. Start scripts with ./bench <benchmark> <step> <env> <script> [args].")
BENCH_DIR = HUB / "benchmarks" / BENCHMARK
profile = importlib.import_module("benchmark_profile")
if Path(profile.__file__).resolve().parent != BENCH_DIR:
    sys.exit(f"benchmark_profile was loaded from {profile.__file__}, not from {BENCH_DIR}. Use ./bench.")
RESULTS = BENCH_DIR / "results"
AUDIT_DIR = RESULTS / "audit"

UPSTREAM_REPO = getattr(profile, "UPSTREAM_REPO", None)
UPSTREAM_COMMIT = getattr(profile, "UPSTREAM_COMMIT", None)
QUESTION_FILES = profile.QUESTION_FILES
CORPUS_FILE = profile.CORPUS_FILE
SYSTEM_PROMPT = profile.SYSTEM_PROMPT
question_key = profile.question_key
prediction = profile.prediction

# Set when retries cannot succeed (for example a daily quota): no new attempts start.
STOP = threading.Event()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def audit(event, **fields):
    """Append one record to the chronological audit log. Never pass secrets."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    with (AUDIT_DIR / "audit.log").open("a") as f:
        f.write(json.dumps({"time": now(), "event": event, **fields}, default=str) + "\n")


def load_key(provider, name="api_key"):
    path = Path.home() / ".config" / provider / name
    if not path.exists():
        sys.exit(f"Missing credential file {path}.")
    key = path.read_text().strip()
    if not key:
        sys.exit(f"Credential file {path} is empty.")
    return key


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def question_file(args):
    return Path(args.questions_file) if args.questions_file else QUESTION_FILES[args.subset]


def load_questions(args):
    if not args.questions_file and not args.sample and not args.full:
        sys.exit("This would run the full question set. Use --questions-file or --sample for pilots, "
                 "or --full when the operator has approved a full run.")
    questions = json.loads(question_file(args).read_text())
    return profile.select_questions(questions, args.subset, args.sample)


def add_common_args(parser, system, workers=4):
    parser.add_argument("--subset", required=True, choices=profile.SUBSETS,
                        help=f"{profile.TITLE} subset to process")
    parser.add_argument("--questions-file", help="a question file in the official format (default: the full subset)")
    parser.add_argument("--sample", type=int, default=0, help="first N questions of each source (0 = all)")
    parser.add_argument("--full", action="store_true",
                        help="run the full question set (only when the operator has approved a full run)")
    parser.add_argument("--workers", type=int, default=workers)
    parser.add_argument("--max-attempts", type=int, default=6)
    parser.add_argument("--backoff", type=float, default=10.0, help="first retry wait in seconds; doubles each time")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--out-dir", default=str(RESULTS / system))
    parser.add_argument("--dry-run", action="store_true", help="print the first request and stop")


def retry(attempt_fn, args):
    """attempt_fn() -> (payload, error, retryable). Returns (payload, attempts, error)."""
    error = None
    for attempt in range(1, args.max_attempts + 1):
        if STOP.is_set():
            return None, attempt - 1, {"code": "stopped"}
        payload, error, retryable = attempt_fn()
        if error is None:
            return payload, attempt, None
        if not retryable or STOP.is_set() or attempt == args.max_attempts:
            return None, attempt, error
        time.sleep(min(120, args.backoff * 2 ** (attempt - 1)) + random.uniform(0, 1))
    return None, args.max_attempts, error


def check_settings(out_dir, settings):
    path = out_dir / "run_config.json"
    if path.exists():
        saved = json.loads(path.read_text())["settings"]
        changed = sorted(k for k in set(saved) | set(settings) if saved.get(k) != settings.get(k))
        if changed:
            sys.exit(f"{path} was made with different settings ({', '.join(changed)}). "
                     f"Use a new --out-dir, or delete {out_dir} to start again.")
        return
    path.write_text(json.dumps({"created": now(), "settings": settings}, indent=2))


def load_log(log_path):
    latest = {}
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            if line.strip():
                record = json.loads(line)
                latest[record["key"]] = record
    return latest


def package_versions():
    names = ("openai", "google-auth", "requests", "websockets", "lightrag-hku", "transformers", "torch")
    versions = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    return versions


def latency_stats(values):
    if not values:
        return {}
    values = sorted(values)
    return {
        "n": len(values),
        "mean_s": round(statistics.fmean(values), 2),
        "median_s": round(statistics.median(values), 2),
        "p90_s": round(values[min(len(values) - 1, int(0.9 * len(values)))], 2),
        "max_s": round(values[-1], 2),
    }


def acquire_lock(path):
    """Exit if another live process holds the lock. The lock is released when this process ends."""
    import atexit
    import os
    if path.exists():
        try:
            pid = int(path.read_text().strip())
            os.kill(pid, 0)
            sys.exit(f"Another process (pid {pid}) is already running in {path.parent}. Stop it or wait.")
        except (ValueError, ProcessLookupError):
            pass
        except PermissionError:
            sys.exit(f"Another process holds {path}.")
    path.write_text(str(os.getpid()))
    atexit.register(lambda: path.exists() and path.read_text().strip() == str(os.getpid()) and path.unlink())


def run(system, args, ask, settings, readiness, cost_fn=None, extra_manifest=None):
    """Run every question that has no successful record yet, then write predictions and the manifest.

    ask(q) returns a dict with: status ("ok"/"failed"), attempts, error, answer, contexts,
    usage (dict of token counts), raw (the raw API response), latency_s, extra (dict).
    It returns None when the run was stopped before the question was sent.
    readiness() returns a dict that describes the ready state; it must sys.exit() if not ready.
    """
    sys.stdout.reconfigure(line_buffering=True)
    out_dir = Path(args.out_dir) / args.subset
    out_dir.mkdir(parents=True, exist_ok=True)
    acquire_lock(out_dir / ".lock")
    check_settings(out_dir, settings)
    log_path, raw_path = out_dir / "runs.jsonl", out_dir / "raw.jsonl"

    questions = load_questions(args)
    done = {k for k, r in load_log(log_path).items() if r["status"] == "ok"}
    todo = [q for q in questions if question_key(q) not in done]
    print(f"== {system} / {args.subset}: {len(questions)} questions, "
          f"{len(questions) - len(todo)} already done, {len(todo)} to run, {args.workers} workers")

    ready = readiness()
    print(f"  readiness: {json.dumps(ready, default=str)}")
    audit("readiness_ok", system=system, subset=args.subset, out_dir=str(out_dir), ready=ready)

    started, t0 = now(), time.monotonic()
    audit("run_start", system=system, subset=args.subset, out_dir=str(out_dir), to_run=len(todo), workers=args.workers)
    lock = threading.Lock()

    def one(q):
        start = time.monotonic()
        result = ask(q)
        if result is None:
            return None, None
        record = {
            "key": question_key(q),
            "time": now(),
            "status": result["status"],
            "attempts": result.get("attempts"),
            "elapsed_s": round(time.monotonic() - start, 2),
            "latency_s": result.get("latency_s"),
            "error": result.get("error"),
            "usage": result.get("usage") or {},
            "extra": result.get("extra") or {},
        }
        if result["status"] == "ok":
            record["prediction"] = prediction(q, result["answer"], result["contexts"])
        return record, result.get("raw")

    with log_path.open("a") as log, raw_path.open("a") as raw_log, ThreadPoolExecutor(args.workers) as pool:
        futures = [pool.submit(one, q) for q in todo]
        for n, future in enumerate(as_completed(futures), 1):
            record, raw = future.result()
            if record is None:
                continue
            with lock:
                log.write(json.dumps(record, ensure_ascii=False) + "\n")
                log.flush()
                raw_log.write(json.dumps({"key": record["key"], "time": record["time"], "raw": raw},
                                         ensure_ascii=False, default=str) + "\n")
                raw_log.flush()
            if record["status"] != "ok":
                print(f"  [{n}/{len(todo)}] FAILED {record['key']}: {json.dumps(record['error'])[:300]}")
            elif n % 25 == 0 or n == len(todo):
                print(f"  [{n}/{len(todo)}] ok ({time.monotonic() - t0:.0f} s)")

    wall_s = round(time.monotonic() - t0, 1)
    if STOP.is_set():
        print("\n  STOPPED: retries cannot succeed now (for example a daily quota). Run the same command later.")
    summary = write_predictions(questions, load_log(log_path), out_dir, cost_fn)
    manifest = {
        "system": system,
        "subset": args.subset,
        "started": started,
        "finished": now(),
        "wall_clock_s_this_invocation": wall_s,
        "ran_this_invocation": len(todo),
        "workers": args.workers,
        "command": sys.argv,
        "settings": settings,
        "readiness": ready,
        "inputs": {
            "questions_file": str(question_file(args)),
            "questions_sha256": sha256(question_file(args)),
            "corpus_file": str(CORPUS_FILE),
            "corpus_sha256": sha256(CORPUS_FILE),
        },
        "benchmark": BENCHMARK,
        "code": {Path(p).name: sha256(p) for p in (sys.argv[0], __file__, profile.__file__)},
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": package_versions(),
        "summary": summary,
        **(extra_manifest or {}),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    audit("run_end", system=system, subset=args.subset, out_dir=str(out_dir), wall_clock_s=wall_s,
          answered=summary["answered"], failed=summary["failed"], not_run=summary["not_run"],
          cost_usd=summary.get("estimated_cost_usd"), stopped=STOP.is_set())
    return summary


def write_predictions(questions, latest, out_dir, cost_fn=None):
    predictions, failed, missing, no_context, dont_know = [], [], 0, 0, 0
    totals, latencies = {}, []
    for q in questions:
        record = latest.get(question_key(q))
        if record is None:
            missing += 1
            continue
        if record["status"] != "ok":
            failed.append(record["key"])
            continue
        stored = record["prediction"]
        predictions.append(prediction(q, stored["generated_answer"], stored["context"]))
        no_context += not any(c.strip() for c in stored["context"])
        dont_know += stored["generated_answer"].strip().lower().startswith("i don't know")
        for k, v in (record.get("usage") or {}).items():
            if isinstance(v, (int, float)):
                totals[k] = totals.get(k, 0) + v
        if record.get("latency_s") is not None:
            latencies.append(record["latency_s"])

    (out_dir / "predictions.json").write_text(json.dumps(predictions, indent=2, ensure_ascii=False))
    summary = {
        "questions": len(questions),
        "answered": len(predictions),
        "failed": len(failed),
        "failed_keys": failed,
        "not_run": missing,
        "no_context": no_context,
        "dont_know": dont_know,
        "tokens": totals,
        "latency": latency_stats(latencies),
    }
    if cost_fn:
        summary["estimated_cost_usd"] = round(cost_fn(totals), 4)
    print(f"\n== summary -> {out_dir / 'predictions.json'}")
    print(f"  answered: {len(predictions)} / {len(questions)}   failed: {len(failed)}   not run: {missing}")
    print(f"  no context: {no_context}   \"I don't know\": {dont_know}")
    print(f"  tokens: {totals}")
    print(f"  latency: {summary['latency']}   estimated cost: {summary.get('estimated_cost_usd')}")
    if failed:
        print("  Run the same command again to retry the failed questions.")
    return summary


def parser(description, system, workers=4):
    p = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(p, system, workers)
    return p

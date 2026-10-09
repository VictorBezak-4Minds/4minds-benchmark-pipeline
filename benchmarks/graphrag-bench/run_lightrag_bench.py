#!/usr/bin/env python3
"""Run GraphRAG-Bench with LightRAG v1.2.5 + Gemini, through the official Examples/run_lightrag.py.

This driver imports the official runner and uses its initialize_rag(), SYSTEM_PROMPT and
query settings (hybrid mode, top_k 5, 4000-token context limits, chunk size 1200/100,
llm_model_max_async 4). It adds what the official script does not have: a questions file,
parallel questions, resume, a readiness check and the audit files. LightRAG must have the
context-return change from Examples/README.md (see patch_lightrag.py).

  index:  ./bench graphrag-bench lightrag_index lightrag run_lightrag_bench.py --subset medical --index-only
  answer: ./bench graphrag-bench pilot_lightrag lightrag run_lightrag_bench.py --subset medical \\
              --questions-file data/Questions/pilot_questions.json --out-dir results/pilot/lightrag

Differences from the official script (also in manifest.json):
  - --embed_model BAAI/bge-large-en-v1.5: the official code sets embedding_dim=1024, which
    only matches a 1024-dimension model (its default "bge-base-en" is not a valid HF id).
  - context is stored as a one-item list: generation_eval.py joins context with newlines,
    so the official string form would put a newline after every character.
"""
import asyncio
import contextvars
import json
import logging
import logging.handlers
import os
import sys
import threading
import time
from pathlib import Path

import bench_common as bc

import difflib  # noqa: E402
import types  # noqa: E402

OFFICIAL_RUNNER = bc.UPSTREAM_REPO / "Examples" / "run_lightrag.py"
# Two bugs make API mode of the official runner fail at fdbab59; both are fixed in memory
# (the repo stays clean for score.py) and the diff is saved to results/audit/patches/.
OFFICIAL_FIXES = [
    # initialize_rag: the ollama branch assigns llm_model_func, so the API branch hits UnboundLocalError.
    ("        llm_model_func_input = llm_model_func\n",
     "        llm_model_func = globals()[\"llm_model_func\"]\n"),
    # llm_model_func: get() leaves these keys in kwargs, so base_url/api_key are passed twice.
    ('    model_name = kwargs.get("model_name", "qwen2.5-14b-instruct")\n',
     '    model_name = kwargs.pop("model_name", "qwen2.5-14b-instruct")\n'),
    ('    base_url = kwargs.get("base_url", "")\n', '    base_url = kwargs.pop("base_url", "")\n'),
    ('    api_key = kwargs.get("api_key", "")\n', '    api_key = kwargs.pop("api_key", "")\n'),
]


def load_official():
    source = OFFICIAL_RUNNER.read_text()
    fixed = source
    for old, new in OFFICIAL_FIXES:
        if fixed.count(old) != 1:
            sys.exit(f"Official runner changed; fix not applicable: {old.strip()}")
        fixed = fixed.replace(old, new)
    diff = "".join(difflib.unified_diff(source.splitlines(True), fixed.splitlines(True),
                                        "a/Examples/run_lightrag.py", "b/Examples/run_lightrag.py"))
    patch_file = bc.AUDIT_DIR / "patches" / "run_lightrag-fdbab59-api-mode.diff"
    patch_file.parent.mkdir(parents=True, exist_ok=True)
    patch_file.write_text(diff)
    module = types.ModuleType("run_lightrag")
    module.__file__ = str(OFFICIAL_RUNNER)
    exec(compile(fixed, str(OFFICIAL_RUNNER), "exec"), module.__dict__)
    return module, patch_file


official, OFFICIAL_PATCH = load_official()
from datasets import load_dataset  # noqa: E402
from lightrag import QueryParam  # noqa: E402
from lightrag.utils import setup_logger  # noqa: E402
from openai.resources.chat.completions import AsyncCompletions  # noqa: E402

GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
PRICE_IN, PRICE_OUT = 0.75, 3.75
USAGE = contextvars.ContextVar("usage", default=None)
INDEX_USAGE = {}
_original_create = AsyncCompletions.create


async def _counting_create(self, *args, **kwargs):
    response = await _original_create(self, *args, **kwargs)
    counter = USAGE.get()
    usage = getattr(response, "usage", None)
    if counter is not None and usage is not None:
        counter["calls"] = counter.get("calls", 0) + 1
        counter["prompt_tokens"] = counter.get("prompt_tokens", 0) + (usage.prompt_tokens or 0)
        counter["completion_tokens"] = counter.get("completion_tokens", 0) + (usage.completion_tokens or 0)
        details = getattr(usage, "completion_tokens_details", None)
        reasoning = getattr(details, "reasoning_tokens", None) if details else None
        counter["reasoning_tokens"] = counter.get("reasoning_tokens", 0) + (reasoning or 0)
    return response

AsyncCompletions.create = _counting_create


def cost(tokens):
    # Gemini's OpenAI endpoint reports thinking tokens inside completion_tokens.
    return (tokens.get("prompt_tokens", 0) * PRICE_IN + tokens.get("completion_tokens", 0) * PRICE_OUT) / 1e6


def official_corpus(subset):
    path = bc.UPSTREAM_REPO / "Datasets" / "Corpus" / f"{subset}.parquet"
    return [{"corpus_name": r["corpus_name"], "context": r["context"]}
            for r in load_dataset("parquet", data_files=str(path), split="train")], path


def doc_status(working_dir):
    path = Path(working_dir) / "kv_store_doc_status.json"
    if not path.exists():
        return {}
    return {k: v.get("status") for k, v in json.loads(path.read_text()).items()}


class Engine:
    """One LightRAG instance on its own event loop thread, shared by the worker threads."""

    def __init__(self, args, api_key, source):
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.working_dir = os.path.join(args.base_dir, source)
        # The "lightrag" logger has no handler unless setup_logger runs, so its progress is lost.
        setup_logger("lightrag", level="INFO", log_file_path=os.path.join(self.working_dir, "lightrag.log"))
        if not args.index_only:
            lightrag_logger = logging.getLogger("lightrag")
            lightrag_logger.handlers = [h for h in lightrag_logger.handlers if isinstance(h, logging.FileHandler)]
        self.rag = self.call(official.initialize_rag(
            base_dir=args.base_dir, source=source, mode="API", model_name=args.model_name,
            embed_model_name=args.embed_model, llm_base_url=args.llm_base_url, llm_api_key=api_key))

    def call(self, coroutine, timeout=None):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout)


async def with_usage(counter, coroutine):
    USAGE.set(counter)
    return await coroutine


def main():
    parser = bc.parser(__doc__, "lightrag", workers=4)
    parser.add_argument("--base-dir", default=str(bc.RESULTS / "lightrag" / "workspace"))
    parser.add_argument("--model-name", default="gemini-3.8-flash")
    parser.add_argument("--embed-model", default="BAAI/bge-large-en-v1.5")
    parser.add_argument("--llm-base-url", default=GEMINI_OPENAI_URL)
    parser.add_argument("--retrieve-topk", type=int, default=5)
    parser.add_argument("--index-only", action="store_true", help="build the index and stop")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    corpus, corpus_path = official_corpus(args.subset)
    if args.index_only:
        args.full = True  # the index only needs the corpus name; no question is sent
    questions = bc.load_questions(args)
    sources = sorted({q["source"] for q in questions})
    if len(sources) != 1:
        sys.exit("This driver runs one corpus at a time (the medical subset has one).")
    source = sources[0]
    context = next(c["context"] for c in corpus if c["corpus_name"] == source)
    param = dict(mode="hybrid", top_k=args.retrieve_topk, max_token_for_text_unit=4000,
                 max_token_for_global_context=4000, max_token_for_local_context=4000)
    if args.dry_run:
        print(json.dumps({"source": source, "context_chars": len(context), "query_param": param,
                          "system_prompt": official.SYSTEM_PROMPT}, indent=2))
        return

    api_key = bc.load_key("gemini")
    os.makedirs(args.base_dir, exist_ok=True)
    engine = Engine(args, api_key, source)

    if args.index_only:
        bc.acquire_lock(Path(engine.working_dir) / ".index.lock")
        statuses = doc_status(engine.working_dir)
        if statuses and all(s == "processed" for s in statuses.values()):
            print(f"Index already complete: {statuses}")
            return
        bc.audit("lightrag_index_start", working_dir=engine.working_dir, corpus=str(corpus_path), chars=len(context))
        start = time.monotonic()
        engine.call(with_usage(INDEX_USAGE, engine.rag.ainsert(context)))
        took = round(time.monotonic() - start, 1)
        statuses = doc_status(engine.working_dir)
        result = {"finished": bc.now(), "index_wall_clock_s": took, "doc_status": statuses, "usage": INDEX_USAGE,
                  "estimated_cost_usd": round(cost(INDEX_USAGE), 4), "model": args.model_name,
                  "embed_model": args.embed_model, "corpus": str(corpus_path), "corpus_sha256": bc.sha256(corpus_path)}
        (Path(engine.working_dir) / "index_manifest.json").write_text(json.dumps(result, indent=2))
        bc.audit("lightrag_index_end", **result)
        print(json.dumps(result, indent=2))
        sys.exit(0 if statuses and all(s == "processed" for s in statuses.values()) else 1)

    def readiness():
        statuses = doc_status(engine.working_dir)
        if not statuses or any(s != "processed" for s in statuses.values()):
            sys.exit(f"Readiness: LightRAG index in {engine.working_dir} is not complete: {statuses}. "
                     "Run with --index-only first.")
        index_manifest = Path(engine.working_dir) / "index_manifest.json"
        return {"working_dir": engine.working_dir, "doc_status": statuses,
                "index": json.loads(index_manifest.read_text()) if index_manifest.exists() else None}

    def ask(q):
        timing, counter = {}, {}

        def attempt():
            start = time.monotonic()
            try:
                response, ctx = engine.call(with_usage(counter, engine.rag.aquery(
                    q["question"], param=QueryParam(**param), system_prompt=official.SYSTEM_PROMPT)), args.timeout)
            except Exception as e:  # LightRAG raises many types; all are retried
                timing["latency_s"] = round(time.monotonic() - start, 2)
                return None, {"code": type(e).__name__, "message": str(e)[:500]}, True
            timing["latency_s"] = round(time.monotonic() - start, 2)
            return (str(response).strip(), ctx), None, False

        result, attempts, error = bc.retry(attempt, args)
        if error and error.get("code") == "stopped":
            return None
        if result is None:
            return {"status": "failed", "attempts": attempts, "error": error, "usage": counter, **timing}
        answer, ctx = result
        contexts = [ctx] if isinstance(ctx, str) and ctx.strip() else list(ctx or [])
        return {"status": "ok", "attempts": attempts, "answer": answer, "contexts": contexts, "usage": counter,
                "raw": {"response": answer, "context": ctx}, "extra": {"context_chars": len(str(ctx or ""))},
                **timing}

    settings = {"lightrag": "1.2.5", "model": args.model_name, "llm_base_url": args.llm_base_url,
                "embed_model": args.embed_model, "query_param": param, "system_prompt": official.SYSTEM_PROMPT,
                "base_dir": args.base_dir}
    summary = bc.run("lightrag_gemini", args, ask, settings, readiness, cost, {
        "official_runner": str(OFFICIAL_RUNNER),
        "official_runner_sha256": bc.sha256(OFFICIAL_RUNNER),
        "official_runner_fixes": str(OFFICIAL_PATCH),
        "deviations": ["two API-mode bugs of the official runner fixed in memory (see official_runner_fixes)",
                       "embed_model BAAI/bge-large-en-v1.5 (embedding_dim 1024 in the official code)",
                       "context stored as a one-item list instead of a string",
                       "questions answered in parallel threads with resume (same LightRAG instance and settings)"],
        "price_usd_per_1m": {"input": PRICE_IN, "output": PRICE_OUT}})
    sys.exit(1 if bc.STOP.is_set() or summary["failed"] else 0)


if __name__ == "__main__":
    main()

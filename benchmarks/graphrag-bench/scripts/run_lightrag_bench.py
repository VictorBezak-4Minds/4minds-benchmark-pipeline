#!/usr/bin/env python3
"""Run GraphRAG-Bench with LightRAG v1.2.5 through the official Examples/run_lightrag.py.

This driver imports the official runner and uses its initialize_rag(), SYSTEM_PROMPT and
query settings (hybrid mode, top_k 5, 4000-token context limits, chunk size 1200/100,
llm_model_max_async 4). It adds what the official script does not have: a questions file,
parallel questions, resume, a readiness check and the audit files. LightRAG must have the
context-return change from Examples/README.md (see patch_lightrag.py).

The LLM is Gemini by default (--model-name, --llm-base-url, Gemini key file). With
--llm <backend> it is a backend from pipeline/llm_backends.json: its model, URL and
credentials (a Bedrock token is made again before it expires), and its generation params at
query time. The index is built without those params, as LightRAG does by default, so the
extraction output is not cut by max_tokens. Each backend has its own index folder.

  index:  ./bench graphrag-bench lightrag_index lightrag run_lightrag_bench.py --subset medical --index-only
  answer: ./bench graphrag-bench pilot_lightrag lightrag run_lightrag_bench.py --subset medical \\
              --questions-file data/Questions/pilot_questions.json --out-dir runs/2026-10-09_gemini-pilot/lightrag
  GPT-OSS: add --llm bedrock-gpt-oss-120b to both (index in shared/lightrag/workspace_bedrock-gpt-oss-120b)

Differences from the official script (also in manifest.json):
  - --embed_model BAAI/bge-large-en-v1.5: the official code sets embedding_dim=1024, which
    only matches a 1024-dimension model (its default "bge-base-en" is not a valid HF id).
  - context is stored as a one-item list: generation_eval.py joins context with newlines,
    so the official string form would put a newline after every character.
  - <reasoning>...</reasoning> is removed from LLM output (GPT-OSS on Bedrock puts it in the
    content, and LightRAG would parse it as entities, keywords or answer text).
"""
import asyncio
import contextvars
import inspect
import json
import logging
import logging.handlers
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

import bench_common as bc
import llm_backends

import difflib  # noqa: E402
import types  # noqa: E402

OFFICIAL_RUNNER = bc.UPSTREAM_REPO / "Examples" / "run_lightrag.py"
# Two bugs make API mode of the official runner fail at fdbab59; both are fixed in memory
# (the repo stays clean for score.py) and the diff is saved to audit/patches/.
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
BACKEND = None          # llm_backends.Backend when --llm is set
QUERY_PARAMS = {}       # backend params, added to query-time calls only
_original_create = AsyncCompletions.create


async def _counting_create(self, *args, **kwargs):
    if BACKEND is not None:
        self._client.api_key = BACKEND.api_key()
    if QUERY_PARAMS:
        kwargs = {**kwargs, **QUERY_PARAMS}
    response = await _original_create(self, *args, **kwargs)
    for choice in getattr(response, "choices", None) or []:
        message = getattr(choice, "message", None)
        if message is not None and isinstance(message.content, str):
            message.content = llm_backends.REASONING_TAGS.sub("", message.content).strip()
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

import lightrag.operate as lightrag_operate  # noqa: E402
from lightrag.prompt import PROMPTS  # noqa: E402

TUPLE_DELIMITER = PROMPTS["DEFAULT_TUPLE_DELIMITER"]
RECORD_MARKERS = [PROMPTS["DEFAULT_RECORD_DELIMITER"], PROMPTS["DEFAULT_COMPLETION_DELIMITER"]]
DAMAGED_DELIMITER = re.compile(r"(?<!<)\|>|<\|(?!>)|<>|\|<")
_original_split = lightrag_operate.split_string_by_multi_markers


def _repairing_split(content, markers):
    """Record split of entity extraction only: GPT-OSS often writes the tuple delimiter <|> as
    |>, <|, <> or |<, breaks a record over lines, or leaves out its parentheses."""
    records = _original_split(content, markers)
    if markers != RECORD_MARKERS:
        return records
    repaired = []
    for record in records:
        record = DAMAGED_DELIMITER.sub(TUPLE_DELIMITER, record.replace("\\\n", " ").replace("\n", " "))
        if "(" not in record and re.match(r'\s*"(entity|relationship)"', record):
            record = f"({record.strip()})"
        repaired.append(record)
    return repaired


def enable_delimiter_repair():
    lightrag_operate.split_string_by_multi_markers = _repairing_split
    path = bc.AUDIT_DIR / "patches" / "lightrag-1.2.5-gptoss-delimiter-repair.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# lightrag.operate.split_string_by_multi_markers is replaced in memory by:\n"
                    f"DAMAGED_DELIMITER = re.compile({DAMAGED_DELIMITER.pattern!r})\n\n"
                    + inspect.getsource(_repairing_split))
    return path


def cost(tokens):
    if BACKEND is not None:
        return BACKEND.cost(tokens)
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
    global BACKEND
    parser = bc.parser(__doc__, "lightrag", workers=4)
    parser.add_argument("--llm", choices=llm_backends.names(),
                        help="LLM backend; replaces --model-name, --llm-base-url and the Gemini key")
    parser.add_argument("--base-dir", help="index folder (default shared/lightrag/workspace, "
                                           "or shared/lightrag/workspace_<llm> with --llm)")
    parser.add_argument("--model-name", default="gemini-3.8-flash")
    parser.add_argument("--embed-model", default="BAAI/bge-large-en-v1.5")
    parser.add_argument("--llm-base-url", default=GEMINI_OPENAI_URL)
    parser.add_argument("--retrieve-topk", type=int, default=5)
    parser.add_argument("--index-only", action="store_true", help="build the index and stop")
    parser.add_argument("--repair-delimiters", action="store_true",
                        help="accept damaged <|> delimiters in entity extraction output (GPT-OSS); "
                             "default index folder gets the suffix _delimfix")
    parser.add_argument("--reuse-llm-cache-from", help="--index-only: copy kv_store_llm_response_cache.json from this "
                                                       "index folder into a new one, so cached extraction calls are reused")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    if args.llm:
        BACKEND = llm_backends.Backend(args.llm)
        args.model_name, args.llm_base_url = BACKEND.model, BACKEND.base_url
    default_dir = ("workspace_" + args.llm if args.llm else "workspace") + ("_delimfix" if args.repair_delimiters else "")
    args.base_dir = args.base_dir or str(bc.SHARED / "lightrag" / default_dir)
    repair_patch = enable_delimiter_repair() if args.repair_delimiters else None

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
                          "model": args.model_name, "llm_base_url": args.llm_base_url, "base_dir": args.base_dir,
                          "query_llm_params": BACKEND.params if BACKEND else {},
                          "system_prompt": official.SYSTEM_PROMPT}, indent=2))
        return

    api_key = BACKEND.api_key() if BACKEND else bc.load_key("gemini")
    os.makedirs(args.base_dir, exist_ok=True)
    reused_cache = None
    if args.reuse_llm_cache_from:
        if not args.index_only:
            sys.exit("--reuse-llm-cache-from is for --index-only.")
        source_cache = Path(args.reuse_llm_cache_from) / source / "kv_store_llm_response_cache.json"
        target_cache = Path(args.base_dir) / source / "kv_store_llm_response_cache.json"
        if not source_cache.exists():
            sys.exit(f"{source_cache} does not exist.")
        if not target_cache.exists():
            target_cache.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_cache, target_cache)
            bc.audit("lightrag_llm_cache_reused", source=str(source_cache), target=str(target_cache),
                     sha256=bc.sha256(target_cache))
        reused_cache = {"from": str(source_cache), "sha256": bc.sha256(source_cache)}
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
                  "llm_base_url": args.llm_base_url, "llm_backend": args.llm,
                  "repair_delimiters": args.repair_delimiters, "repair_patch": str(repair_patch) if repair_patch else None,
                  "reused_llm_cache": reused_cache,
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
        index = json.loads(index_manifest.read_text()) if index_manifest.exists() else None
        if index and index.get("model") != args.model_name:
            sys.exit(f"Readiness: the index in {engine.working_dir} was built with {index.get('model')}, "
                     f"not {args.model_name}. Use the index folder of this model (--base-dir).")
        if index and bool(index.get("repair_delimiters")) != args.repair_delimiters:
            sys.exit(f"Readiness: the index in {engine.working_dir} has repair_delimiters="
                     f"{bool(index.get('repair_delimiters'))}; run with the same --repair-delimiters setting.")
        return {"working_dir": engine.working_dir, "doc_status": statuses, "index": index}

    QUERY_PARAMS.update(BACKEND.params if BACKEND else {})

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
    if BACKEND:
        settings.update({"llm": BACKEND.settings(), "query_llm_params": BACKEND.params})
    if args.repair_delimiters:
        settings["repair_delimiters"] = True
    summary = bc.run(f"lightrag_{args.llm}" if args.llm else "lightrag_gemini", args, ask, settings, readiness, cost, {
        "official_runner": str(OFFICIAL_RUNNER),
        "official_runner_sha256": bc.sha256(OFFICIAL_RUNNER),
        "official_runner_fixes": str(OFFICIAL_PATCH),
        "deviations": ["two API-mode bugs of the official runner fixed in memory (see official_runner_fixes)",
                       "embed_model BAAI/bge-large-en-v1.5 (embedding_dim 1024 in the official code)",
                       "context stored as a one-item list instead of a string",
                       "questions answered in parallel threads with resume (same LightRAG instance and settings)",
                       "<reasoning>...</reasoning> removed from LLM output"]
                      + (["backend generation params added at query time only (not at indexing)"] if BACKEND else [])
                      + ([f"damaged <|> delimiters in extraction output repaired in memory ({repair_patch})"]
                         if repair_patch else []),
        "price_usd_per_1m": BACKEND.prices if BACKEND else {"input": PRICE_IN, "output": PRICE_OUT}})
    sys.exit(1 if bc.STOP.is_set() or summary["failed"] else 0)


if __name__ == "__main__":
    main()

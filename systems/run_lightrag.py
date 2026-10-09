#!/usr/bin/env python3
"""Run benchmark questions against LightRAG v1.2.5 + Gemini (environment `lightrag`).

The index holds only the profile's CORPUS_FILE. Query settings: hybrid mode, top_k 5 (the
top_k of the other systems in the matrix), 4000-token context limits. Index settings: the
LightRAG 1.2.5 defaults (chunk size 1200/100, entity gleaning 1, 16 parallel LLM calls), an
OpenAI-compatible LLM endpoint (here Gemini) and BAAI/bge-large-en-v1.5 embeddings
(embedding_dim 1024). The parallel calls change only the speed. The system prompt is the
profile's SYSTEM_PROMPT followed by LightRAG's conversation history and knowledge base
sections, in the layout of that runner. LightRAG must have the context-return change
(benchmarks/graphrag-bench/patch_lightrag.py).

    index:  ./bench --bg qasper lightrag_index lightrag systems/run_lightrag.py --subset test --index-only
    answer: ./bench qasper pilot_lightrag lightrag systems/run_lightrag.py --subset test \\
                --questions-file data/pilot_questions.json --out-dir results/pilot/lightrag
"""
import asyncio
import contextvars
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

import bench_common as bc

from lightrag import LightRAG, QueryParam  # noqa: E402
from lightrag.kg.shared_storage import initialize_pipeline_status  # noqa: E402
from lightrag.llm.hf import hf_embed  # noqa: E402
from lightrag.llm.openai import openai_complete_if_cache  # noqa: E402
from lightrag.utils import EmbeddingFunc, setup_logger  # noqa: E402
from openai.resources.chat.completions import AsyncCompletions  # noqa: E402

GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
PRICE_IN, PRICE_OUT = 0.75, 3.75
USAGE = contextvars.ContextVar("usage", default=None)
INDEX_USAGE = {}
_original_create = AsyncCompletions.create
# LightRAG calls str.format() on the system prompt, so braces in the profile text are escaped.
LIGHTRAG_PROMPT = (bc.SYSTEM_PROMPT.replace("{", "{{").replace("}", "}}")
                   + "\n\n---Conversation History---\n{history}\n\n---Knowledge Base---\n{context_data}\n")


async def _counting_create(self, *args, **kwargs):
    response = await _original_create(self, *args, **kwargs)
    counter = USAGE.get()
    usage = getattr(response, "usage", None)
    if counter is not None and usage is not None:
        counter["calls"] = counter.get("calls", 0) + 1
        counter["prompt_tokens"] = counter.get("prompt_tokens", 0) + (usage.prompt_tokens or 0)
        counter["completion_tokens"] = counter.get("completion_tokens", 0) + (usage.completion_tokens or 0)
    return response

AsyncCompletions.create = _counting_create


def cost(tokens):
    # Gemini's OpenAI endpoint reports thinking tokens inside completion_tokens.
    return (tokens.get("prompt_tokens", 0) * PRICE_IN + tokens.get("completion_tokens", 0) * PRICE_OUT) / 1e6


def doc_status(working_dir):
    path = Path(working_dir) / "kv_store_doc_status.json"
    if not path.exists():
        return {}
    return {k: v.get("status") for k, v in json.loads(path.read_text()).items()}


async def initialize_rag(working_dir, args, api_key):
    from transformers import AutoModel, AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.embed_model)
    embed_model = AutoModel.from_pretrained(args.embed_model)

    async def llm(prompt, system_prompt=None, history_messages=[], keyword_extraction=False, **kwargs):
        return await openai_complete_if_cache(args.model_name, prompt, system_prompt=system_prompt,
                                              history_messages=history_messages, base_url=args.llm_base_url,
                                              api_key=api_key, **kwargs)

    rag = LightRAG(
        working_dir=working_dir,
        llm_model_func=llm,
        llm_model_name=args.model_name,
        llm_model_max_async=args.max_async,
        llm_model_max_token_size=32768,
        chunk_token_size=1200,
        chunk_overlap_token_size=100,
        embedding_func=EmbeddingFunc(embedding_dim=1024, max_token_size=8192,
                                     func=lambda texts: hf_embed(texts, tokenizer, embed_model)),
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()
    return rag


class Engine:
    """One LightRAG instance on its own event loop thread, shared by the worker threads."""

    def __init__(self, args, api_key, working_dir):
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.working_dir = working_dir
        os.makedirs(working_dir, exist_ok=True)
        setup_logger("lightrag", level="INFO", log_file_path=os.path.join(working_dir, "lightrag.log"))
        if not args.index_only:
            lightrag_logger = logging.getLogger("lightrag")
            lightrag_logger.handlers = [h for h in lightrag_logger.handlers if isinstance(h, logging.FileHandler)]
        self.rag = self.call(initialize_rag(working_dir, args, api_key))

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
    parser.add_argument("--max-async", type=int, default=16, help="parallel LLM calls (LightRAG 1.2.5 default)")
    parser.add_argument("--index-only", action="store_true", help="build the index and stop")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    working_dir = os.path.join(args.base_dir, bc.profile.RESOURCE_NAME)
    param = dict(mode="hybrid", top_k=args.retrieve_topk, max_token_for_text_unit=4000,
                 max_token_for_global_context=4000, max_token_for_local_context=4000)
    if args.dry_run:
        questions = bc.load_questions(args)
        print(json.dumps({"working_dir": working_dir, "corpus": str(bc.CORPUS_FILE),
                          "corpus_chars": len(bc.CORPUS_FILE.read_text()), "query": questions[0]["question"],
                          "query_param": param, "system_prompt": LIGHTRAG_PROMPT}, indent=2))
        return

    api_key = bc.load_key("gemini")
    engine = Engine(args, api_key, working_dir)

    if args.index_only:
        bc.acquire_lock(Path(working_dir) / ".index.lock")
        statuses = doc_status(working_dir)
        if statuses and all(s == "processed" for s in statuses.values()):
            print(f"Index already complete: {statuses}")
            return
        context = bc.CORPUS_FILE.read_text()
        bc.audit("lightrag_index_start", working_dir=working_dir, corpus=str(bc.CORPUS_FILE), chars=len(context))
        start = time.monotonic()
        engine.call(with_usage(INDEX_USAGE, engine.rag.ainsert(context)))
        statuses = doc_status(working_dir)
        result = {"finished": bc.now(), "index_wall_clock_s": round(time.monotonic() - start, 1),
                  "doc_status": statuses, "usage": INDEX_USAGE, "estimated_cost_usd": round(cost(INDEX_USAGE), 4),
                  "model": args.model_name, "embed_model": args.embed_model, "max_async": args.max_async,
                  "corpus": str(bc.CORPUS_FILE),
                  "corpus_sha256": bc.sha256(bc.CORPUS_FILE)}
        (Path(working_dir) / "index_manifest.json").write_text(json.dumps(result, indent=2))
        bc.audit("lightrag_index_end", **result)
        print(json.dumps(result, indent=2))
        sys.exit(0 if statuses and all(s == "processed" for s in statuses.values()) else 1)

    def readiness():
        statuses = doc_status(working_dir)
        if not statuses or any(s != "processed" for s in statuses.values()):
            sys.exit(f"Readiness: LightRAG index in {working_dir} is not complete: {statuses}. "
                     "Run with --index-only first.")
        index_manifest = json.loads((Path(working_dir) / "index_manifest.json").read_text())
        if index_manifest["corpus_sha256"] != bc.sha256(bc.CORPUS_FILE):
            sys.exit(f"Readiness: the index in {working_dir} was built from another corpus file.")
        return {"working_dir": working_dir, "doc_status": statuses, "index": index_manifest}

    def ask(q):
        timing, counter = {}, {}

        def attempt():
            start = time.monotonic()
            try:
                response, ctx = engine.call(with_usage(counter, engine.rag.aquery(
                    q["question"], param=QueryParam(**param), system_prompt=LIGHTRAG_PROMPT)), args.timeout)
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
                "embed_model": args.embed_model, "max_async": args.max_async, "query_param": param,
                "system_prompt": LIGHTRAG_PROMPT, "working_dir": working_dir}
    summary = bc.run("lightrag_gemini", args, ask, settings, readiness, cost,
                     {"price_usd_per_1m": {"input": PRICE_IN, "output": PRICE_OUT}})
    sys.exit(1 if bc.STOP.is_set() or summary["failed"] else 0)


if __name__ == "__main__":
    main()

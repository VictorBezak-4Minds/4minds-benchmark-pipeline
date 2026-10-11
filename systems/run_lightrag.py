#!/usr/bin/env python3
"""Run benchmark questions against LightRAG v1.2.5 (environment `lightrag`).

The index holds only the profile's corpus. Query settings: hybrid mode, top_k 5 (the top_k of
the other systems in the matrix), 4000-token context limits. Index settings: the LightRAG
1.2.5 defaults (chunk size 1200/100, entity gleaning 1, 16 parallel LLM calls), an
OpenAI-compatible LLM endpoint and BAAI/bge-large-en-v1.5 embeddings (embedding_dim 1024).
The parallel calls change only the speed. The system prompt is the profile's SYSTEM_PROMPT
followed by LightRAG's conversation history and knowledge base sections, in the layout of that
runner. LightRAG must have the context-return change (benchmarks/graphrag-bench/patch_lightrag.py).

The LLM is Gemini by default (--model-name, --llm-base-url, Gemini key file). With --llm
<backend> it is a backend from pipeline/llm_backends.json: its model, URL and credentials, and
its generation params at query time only (the index is built with the LightRAG defaults). Each
backend has its own index folder. --repair-delimiters (for GPT-OSS) is in lightrag_hooks.py.

Corpus: a profile with corpus_documents() (a document list) has each document inserted with
its own ID, in groups of --insert-group documents; LightRAG writes its files to disk only at
the end of an insert, so a stopped index loses at most one group. The answers then carry the
IDs of the documents whose chunks LightRAG put into the context (document_ids). A profile with
one CORPUS_FILE has the file inserted as one document.

    index:  ./bench --bg qasper lightrag_index lightrag systems/run_lightrag.py --subset test --index-only
    answer: ./bench qasper pilot_lightrag lightrag systems/run_lightrag.py --subset test \\
                --questions-file data/pilot_questions.json --out-dir runs/<YYYY-MM-DD>_<name>/lightrag
    GPT-OSS: add --llm bedrock-gpt-oss-120b --repair-delimiters to both
"""
import asyncio
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

import bench_common as bc
import lightrag_hooks
import llm_backends

from lightrag import LightRAG, QueryParam  # noqa: E402
from lightrag.kg.shared_storage import initialize_pipeline_status  # noqa: E402
from lightrag.llm.hf import hf_embed  # noqa: E402
from lightrag.llm.openai import openai_complete_if_cache  # noqa: E402
from lightrag.utils import EmbeddingFunc, setup_logger  # noqa: E402

GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
PRICE_IN, PRICE_OUT = 0.75, 3.75
INDEX_USAGE = {}
BACKEND = None
# LightRAG calls str.format() on the system prompt, so braces in the profile text are escaped.
LIGHTRAG_PROMPT = (bc.SYSTEM_PROMPT.replace("{", "{{").replace("}", "}}")
                   + "\n\n---Conversation History---\n{history}\n\n---Knowledge Base---\n{context_data}\n")


def cost(tokens):
    if BACKEND is not None:
        return BACKEND.cost(tokens)
    # Gemini's OpenAI endpoint reports thinking tokens inside completion_tokens.
    return (tokens.get("prompt_tokens", 0) * PRICE_IN + tokens.get("completion_tokens", 0) * PRICE_OUT) / 1e6


def doc_status(working_dir):
    path = Path(working_dir) / "kv_store_doc_status.json"
    if not path.exists():
        return {}
    return {k: v.get("status") for k, v in json.loads(path.read_text()).items()}


def status_counts(statuses):
    counts = {}
    for s in statuses.values():
        counts[s] = counts.get(s, 0) + 1
    return counts


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


async def with_usage(counter, coroutine, doc_ids=None):
    lightrag_hooks.USAGE.set(counter)
    lightrag_hooks.DOC_IDS.set(doc_ids)
    return await coroutine


def corpus():
    """(texts, ids or None, description) of the profile's corpus."""
    if hasattr(bc.profile, "corpus_documents"):
        docs = bc.profile.corpus_documents()
        return [d["text"] for d in docs], [d["dsid"] for d in docs], f"{len(docs)} documents in {bc.CORPUS_FILE.name}"
    return [bc.CORPUS_FILE.read_text()], None, bc.CORPUS_FILE.name


def build_index(engine, args, repair_patch):
    bc.acquire_lock(Path(engine.working_dir) / ".index.lock")
    texts, ids, description = corpus()
    statuses = doc_status(engine.working_dir)
    if statuses and all(s == "processed" for s in statuses.values()) and (ids is None or set(ids) <= set(statuses)):
        print(f"Index already complete: {status_counts(statuses)}")
        return 0
    previous = json.loads((Path(engine.working_dir) / "index_manifest.json").read_text()) \
        if (Path(engine.working_dir) / "index_manifest.json").exists() else {}
    for key in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "calls"):
        INDEX_USAGE[key] = (previous.get("usage") or {}).get(key, 0)
    wall_before = previous.get("index_wall_clock_s", 0)
    bc.audit("lightrag_index_start", working_dir=engine.working_dir, corpus=description,
             chars=sum(map(len, texts)), already_processed=sum(s == "processed" for s in statuses.values()))
    start = time.monotonic()
    groups = [(texts, ids)] if ids is None else [
        (texts[i:i + args.insert_group], ids[i:i + args.insert_group]) for i in range(0, len(texts), args.insert_group)]
    for n, (group_texts, group_ids) in enumerate(groups, 1):
        if group_ids is not None and all(statuses.get(i) == "processed" for i in group_ids):
            continue
        group_start = time.monotonic()
        engine.call(with_usage(INDEX_USAGE, engine.rag.ainsert(group_texts, ids=group_ids)))
        statuses = doc_status(engine.working_dir)
        result = write_index_manifest(engine, args, repair_patch, description, statuses,
                                      wall_before + round(time.monotonic() - start, 1))
        print(f"  {bc.now()} group {n}/{len(groups)}: {round(time.monotonic() - group_start)} s, "
              f"status {status_counts(statuses)}, usage {INDEX_USAGE}, cost so far {result['estimated_cost_usd']}")
    statuses = doc_status(engine.working_dir)
    result = write_index_manifest(engine, args, repair_patch, description, statuses,
                                  wall_before + round(time.monotonic() - start, 1))
    bc.audit("lightrag_index_end", **{k: v for k, v in result.items() if k != "doc_status"},
             doc_status_counts=status_counts(statuses))
    print(json.dumps({k: v for k, v in result.items() if k != "doc_status"}, indent=2))
    return 0 if statuses and all(s == "processed" for s in statuses.values()) else 1


def write_index_manifest(engine, args, repair_patch, description, statuses, wall_s):
    result = {"finished": bc.now(), "index_wall_clock_s": wall_s, "doc_status_counts": status_counts(statuses),
              "usage": dict(INDEX_USAGE), "estimated_cost_usd": round(cost(INDEX_USAGE), 4), "model": args.model_name,
              "llm_base_url": args.llm_base_url, "llm_backend": args.llm, "max_async": args.max_async,
              "insert_group": args.insert_group, "repair_delimiters": args.repair_delimiters,
              "repair_patch": str(repair_patch) if repair_patch else None, "embed_model": args.embed_model,
              "corpus": str(bc.CORPUS_FILE), "corpus_description": description,
              "corpus_sha256": bc.sha256(bc.CORPUS_FILE)}
    if len(statuses) <= 50:
        result["doc_status"] = statuses
    (Path(engine.working_dir) / "index_manifest.json").write_text(json.dumps(result, indent=2))
    return result


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
    parser.add_argument("--max-async", type=int, default=16, help="parallel LLM calls (LightRAG 1.2.5 default)")
    parser.add_argument("--insert-group", type=int, default=500, help="documents per insert (document lists only)")
    parser.add_argument("--index-only", action="store_true", help="build the index and stop")
    parser.add_argument("--repair-delimiters", action="store_true",
                        help="accept damaged <|> delimiters in entity extraction output (GPT-OSS); "
                             "default index folder gets the suffix _delimfix")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    if args.llm:
        BACKEND = llm_backends.Backend(args.llm)
        args.model_name, args.llm_base_url = BACKEND.model, BACKEND.base_url
    default_dir = ("workspace_" + args.llm if args.llm else "workspace") + ("_delimfix" if args.repair_delimiters else "")
    args.base_dir = args.base_dir or str(bc.SHARED / "lightrag" / default_dir)
    lightrag_hooks.install_create_hook(BACKEND)
    lightrag_hooks.install_doc_id_hook()
    repair_patch = lightrag_hooks.enable_delimiter_repair(
        bc.AUDIT_DIR / "patches" / "lightrag-1.2.5-gptoss-delimiter-repair.py") if args.repair_delimiters else None

    working_dir = os.path.join(args.base_dir, bc.profile.RESOURCE_NAME)
    param = dict(mode="hybrid", top_k=args.retrieve_topk, max_token_for_text_unit=4000,
                 max_token_for_global_context=4000, max_token_for_local_context=4000)
    if args.dry_run:
        texts, ids, description = corpus()
        questions = bc.load_questions(args) if not args.index_only else []
        print(json.dumps({"working_dir": working_dir, "corpus": description, "corpus_chars": sum(map(len, texts)),
                          "model": args.model_name, "llm_base_url": args.llm_base_url,
                          "query_llm_params": BACKEND.params if BACKEND else {},
                          "query": questions[0]["question"] if questions else None,
                          "query_param": param, "system_prompt": LIGHTRAG_PROMPT}, indent=2))
        return

    api_key = BACKEND.api_key() if BACKEND else bc.load_key("gemini")
    engine = Engine(args, api_key, working_dir)

    if args.index_only:
        sys.exit(build_index(engine, args, repair_patch))

    def readiness():
        statuses = doc_status(working_dir)
        if not statuses or any(s != "processed" for s in statuses.values()):
            sys.exit(f"Readiness: LightRAG index in {working_dir} is not complete: {status_counts(statuses)}. "
                     "Run with --index-only first.")
        index_manifest = json.loads((Path(working_dir) / "index_manifest.json").read_text())
        if index_manifest["corpus_sha256"] != bc.sha256(bc.CORPUS_FILE):
            sys.exit(f"Readiness: the index in {working_dir} was built from another corpus file.")
        if index_manifest.get("model") != args.model_name:
            sys.exit(f"Readiness: the index in {working_dir} was built with {index_manifest.get('model')}, "
                     f"not {args.model_name}. Use the index folder of this model (--base-dir).")
        if bool(index_manifest.get("repair_delimiters")) != args.repair_delimiters:
            sys.exit(f"Readiness: the index in {working_dir} has repair_delimiters="
                     f"{bool(index_manifest.get('repair_delimiters'))}; run with the same --repair-delimiters setting.")
        return {"working_dir": working_dir, "doc_status_counts": status_counts(statuses), "index": index_manifest}

    lightrag_hooks.QUERY_PARAMS.update(BACKEND.params if BACKEND else {})
    with_ids = hasattr(bc.profile, "corpus_documents")

    def ask(q):
        timing, counter = {}, {}

        def attempt():
            start = time.monotonic()
            found = []
            try:
                response, ctx = engine.call(with_usage(counter, engine.rag.aquery(
                    q["question"], param=QueryParam(**param), system_prompt=LIGHTRAG_PROMPT), found), args.timeout)
            except Exception as e:  # LightRAG raises many types; all are retried
                timing["latency_s"] = round(time.monotonic() - start, 2)
                return None, {"code": type(e).__name__, "message": str(e)[:500]}, True
            timing["latency_s"] = round(time.monotonic() - start, 2)
            return (str(response).strip(), ctx, list(dict.fromkeys(found))), None, False

        result, attempts, error = bc.retry(attempt, args)
        if error and error.get("code") == "stopped":
            return None
        if result is None:
            return {"status": "failed", "attempts": attempts, "error": error, "usage": counter, **timing}
        answer, ctx, doc_ids = result
        contexts = [ctx] if isinstance(ctx, str) and ctx.strip() else list(ctx or [])
        out = {"status": "ok", "attempts": attempts, "answer": answer, "contexts": contexts, "usage": counter,
               "raw": {"response": answer, "context": ctx, "document_ids": doc_ids},
               "extra": {"context_chars": len(str(ctx or "")), "documents": len(doc_ids)}, **timing}
        if with_ids:
            out["document_ids"] = doc_ids
        return out

    settings = {"lightrag": "1.2.5", "model": args.model_name, "llm_base_url": args.llm_base_url,
                "embed_model": args.embed_model, "max_async": args.max_async, "query_param": param,
                "system_prompt": LIGHTRAG_PROMPT, "working_dir": working_dir}
    if BACKEND:
        settings.update({"llm": BACKEND.settings(), "query_llm_params": BACKEND.params})
    if args.repair_delimiters:
        settings["repair_delimiters"] = True
    if with_ids:
        settings["document_ids"] = "full_doc_id of the text chunks in the query context, first-seen order"
    deviations = (["backend generation params added at query time only (not at indexing)",
                   "<reasoning>...</reasoning> removed from LLM output"] if BACKEND else []) + \
        ([f"damaged <|> delimiters in extraction output repaired in memory ({repair_patch})"] if repair_patch else [])
    summary = bc.run(f"lightrag_{args.llm}" if args.llm else "lightrag_gemini", args, ask, settings, readiness, cost,
                     {"price_usd_per_1m": BACKEND.prices if BACKEND else {"input": PRICE_IN, "output": PRICE_OUT},
                      "deviations": deviations})
    sys.exit(1 if bc.STOP.is_set() or summary["failed"] else 0)


if __name__ == "__main__":
    main()

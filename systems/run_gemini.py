#!/usr/bin/env python3
"""Run benchmark questions against a Gemini File Search store (Gemini Developer API).

Each question is sent with a metadata filter on its own `source`, so retrieval only sees
that one corpus (the isolation used by GraphRAG-Bench's reference runners). The questions
of the profile must have a `source` field, and the store documents a matching metadata key.

Output: results/gemini/<subset>/predictions.json, in the format of the profile's
prediction(). Progress is logged to runs.jsonl, so a stopped run continues where it stopped.

    ./bench graphrag-bench pilot_gemini eval systems/run_gemini.py --subset medical \\
        --questions-file data/Questions/pilot_questions.json --out-dir results/pilot/gemini --workers 10
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import bench_common as bc

API = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_STORE = getattr(bc.profile, "GEMINI_FILE_SEARCH_STORE", None)
RETRYABLE_HTTP = {0, 408, 429, 500, 502, 503, 504}
RETRYABLE_CODES = {"service_unavailable", "resource_exhausted", "unavailable", "internal",
                   "deadline_exceeded", "too_many_requests"}
# gemini-3.8-flash paid tier, until Dec 31, 2026 (USD per 1M tokens). Retrieved tokens are input.
PRICE_IN, PRICE_OUT = 0.75, 3.75


def cost(tokens):
    tokens_in = tokens.get("total_input_tokens", 0) + tokens.get("total_tool_use_tokens", 0)
    tokens_out = tokens.get("total_output_tokens", 0) + tokens.get("total_thought_tokens", 0)
    return (tokens_in * PRICE_IN + tokens_out * PRICE_OUT) / 1e6


def request(api_key, method, url, body=None, timeout=60):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode() if body is not None else None, method=method,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"error": {"message": raw.decode(errors="replace")[:500]}}
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        return 0, {"error": {"code": "network", "message": str(e)}}


def build_request(args, q):
    tool = {
        "type": "file_search",
        "file_search_store_names": [args.store],
        "metadata_filter": f'source = "{q["source"]}"',
        "top_k": args.top_k,
    }
    body = {"model": args.model, "input": q["question"], "system_instruction": bc.SYSTEM_PROMPT, "tools": [tool]}
    generation_config = {}
    if args.temperature is not None:
        generation_config["temperature"] = args.temperature
    if args.seed is not None:
        generation_config["seed"] = args.seed
    if args.thinking_level:
        generation_config["thinking_level"] = args.thinking_level
    if generation_config:
        body["generation_config"] = generation_config
    return body


def parse_response(payload):
    """Return (answer, cited chunk texts, cited sources, number of searches)."""
    texts, contexts, cited_sources, searches = [], [], set(), 0
    for step in payload.get("steps", []):
        if step.get("type") == "file_search_call":
            searches += 1
        if step.get("type") != "model_output":
            continue
        for part in step.get("content", []):
            if part.get("type") != "text":
                continue
            texts.append(part.get("text", ""))
            for ann in part.get("annotations", []):
                if ann.get("type") != "file_citation":
                    continue
                cited_sources.add((ann.get("custom_metadata") or {}).get("source"))
                chunk = ann.get("source")
                if chunk and chunk not in contexts:
                    contexts.append(chunk)
    return "".join(texts).strip(), contexts, cited_sources, searches


def make_ask(api_key, args):
    def ask(q):
        body = build_request(args, q)
        timing = {}

        def attempt():
            start = time.monotonic()
            status, payload = request(api_key, "POST", f"{API}/interactions", body, args.timeout)
            timing["latency_s"] = round(time.monotonic() - start, 2)
            error = payload.get("error")
            if status == 200 and not error:
                if payload.get("status") == "completed":
                    return payload, None, False
                return None, {"message": f"interaction status {payload.get('status')!r}"}, True
            error = error if isinstance(error, dict) else {"message": str(error or f"HTTP {status}")}
            error["http_status"] = status
            if status == 429 and "per day" in str(error.get("message", "")).lower():
                bc.STOP.set()
                return None, error, False
            code = str(error.get("code", "")).lower()
            return None, error, status in RETRYABLE_HTTP or code in RETRYABLE_CODES

        payload, attempts, error = bc.retry(attempt, args)
        if error and error.get("code") == "stopped":
            return None
        if payload is None:
            return {"status": "failed", "attempts": attempts, "error": error, **timing}
        answer, contexts, cited_sources, searches = parse_response(payload)
        usage = payload.get("usage", {})
        leaks = sorted(str(s) for s in cited_sources if s != q["source"])
        if leaks:
            print(f"  LEAK {bc.question_key(q)} cited {leaks}")
        return {
            "status": "ok", "attempts": attempts, "answer": answer, "contexts": contexts, "raw": payload,
            "usage": {k: usage.get(k, 0) for k in ("total_input_tokens", "total_output_tokens",
                                                   "total_tool_use_tokens", "total_thought_tokens")},
            "extra": {"interaction_id": payload.get("id"), "searches": searches, "leaked_sources": leaks},
            **timing,
        }
    return ask


def make_readiness(api_key, args, subset_sources):
    def readiness():
        status, store = request(api_key, "GET", f"{API}/{args.store}")
        if status != 200:
            sys.exit(f"Readiness: cannot read {args.store}: HTTP {status} {store.get('error')}")
        counts = {k: int(store.get(k) or 0) for k in
                  ("activeDocumentsCount", "pendingDocumentsCount", "failedDocumentsCount")}
        docs, token = [], None
        while True:
            query = urllib.parse.urlencode({"pageSize": 20, **({"pageToken": token} if token else {})})
            status, page = request(api_key, "GET", f"{API}/{args.store}/documents?{query}")
            if status != 200:
                sys.exit(f"Readiness: cannot list documents: HTTP {status} {page.get('error')}")
            docs += page.get("documents", [])
            token = page.get("nextPageToken")
            if not token:
                break
        by_source = {}
        for d in docs:
            for m in d.get("customMetadata", []):
                if m.get("key") == "source":
                    by_source[m.get("stringValue")] = d.get("state")
        missing = sorted(s for s in subset_sources if by_source.get(s) != "STATE_ACTIVE")
        if counts["pendingDocumentsCount"] or counts["failedDocumentsCount"] or missing:
            sys.exit(f"Readiness: store not ready: {counts}, sources not active: {missing}")
        return {"store": args.store, **counts, "sources_active": sorted(subset_sources)}
    return readiness


def main():
    parser = bc.parser(__doc__, "gemini")
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--model", default="gemini-3.8-flash")
    parser.add_argument("--top-k", type=int, default=5, help="chunks retrieved per search (reference runner: 5)")
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--thinking-level", choices=["minimal", "low", "medium", "high"])
    args = parser.parse_args()

    questions = bc.load_questions(args)
    if args.dry_run:
        print(json.dumps(build_request(args, questions[0]), indent=2))
        return
    api_key = bc.load_key("gemini")
    settings = {"store": args.store, "model": args.model, "top_k": args.top_k, "temperature": args.temperature,
                "seed": args.seed, "thinking_level": args.thinking_level, "system_prompt": bc.SYSTEM_PROMPT}
    summary = bc.run("gemini_file_search", args, make_ask(api_key, args), settings,
                     make_readiness(api_key, args, {q["source"] for q in questions}), cost,
                     {"endpoint": f"{API}/interactions", "price_usd_per_1m": {"input": PRICE_IN, "output": PRICE_OUT}})
    sys.exit(1 if bc.STOP.is_set() or summary["failed"] else 0)


if __name__ == "__main__":
    main()

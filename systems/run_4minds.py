#!/usr/bin/env python3
"""Run benchmark questions against 4Minds (prod) with the API key.

The dataset, persona and model are made by setup_4minds.py. Each question gets a new
conversation (no history).
  --engine constellations: WebSocket wss://.../api/v1/user/inference ("conversation_prompt").
      The answer is the joined stream_chunk deltas; the context is the retrieved chunk text.
  --engine symi: POST /api/v1/user/inference with inference_engine "symi" (SSE). The SYMI
      WebSocket path rejects API keys; this one gives chunk references but no chunk text.

Output: runs/<run>/4minds_<engine>/<subset>/predictions.json, in the format of the profile's
prediction().

    ./bench graphrag-bench pilot_4minds_constellations eval systems/run_4minds.py --engine constellations \\
        --subset medical --questions-file data/Questions/pilot_questions.json \\
        --out-dir runs/<YYYY-MM-DD>_<name>/4minds_constellations --workers 4
"""
import json
import sys
import time

import requests
from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

import bench_common as bc
import setup_4minds as setup

WS_URL = "wss://api.4minds.ai/api/v1/user/inference"
SSE_URL = f"{setup.BASE}/api/v1/user/inference"
PREFIX = {"constellations": "", "symi": "symi."}
IGNORED = {"ping", "pong", "banner", "conversation_created", "token_refreshed", "user_message", "connection_established",
           "agent_status", "agent_update", "planning", "verification", "regeneration_start"}


class Fatal(Exception):
    pass


def create_conversation(http, model_id, q):
    response = http.post(f"{setup.BASE}/api/v1/conversations", timeout=60,
                         json={"model_id": model_id, "title": f"{bc.profile.RESOURCE_NAME} {bc.question_key(q)}"})
    if response.status_code >= 400:
        raise RuntimeError(f"create conversation: HTTP {response.status_code} {response.text[:300]}")
    return str(response.json()["id"])


def receive(ws, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("no complete frame before the timeout")
    return json.loads(ws.recv(timeout=remaining))


def one_turn(key, http, model_id, engine, q, timeout):
    """Send one question on a new connection and conversation. Return (answer, contexts, frames, meta)."""
    prefix = PREFIX[engine]
    conversation_id = create_conversation(http, model_id, q)
    deadline = time.monotonic() + timeout
    with connect(WS_URL, open_timeout=30, close_timeout=5, max_size=None) as ws:
        ws.send(json.dumps({"type": "authenticate", "token": key}))
        while True:
            frame = receive(ws, deadline)
            if frame.get("type") == "auth_error":
                raise Fatal(f"auth_error: {frame.get('message')}")
            if frame.get("type") == "ping":
                ws.send(json.dumps({"type": "pong"}))
            if frame.get("type") == "connection_established":
                break
        ws.send(json.dumps({"type": f"{prefix}conversation_prompt", "model_id": model_id,
                            "conversation_id": conversation_id, "prompt": q["question"],
                            "user_message": q["question"], "enable_web_search": False}))
        deltas, contexts, frames, meta, errors, scores, titles = {}, [], [], {}, [], {}, {}
        error_deadline = None
        while True:
            try:
                frame = receive(ws, min(deadline, error_deadline) if error_deadline else deadline)
            except TimeoutError:
                if errors:
                    raise RuntimeError(f"error without complete: {errors}")
                raise
            kind = frame.get("type", "")
            if kind == "ping":
                ws.send(json.dumps({"type": "pong"}))
                continue
            if frame.get("conversation_id") not in (None, conversation_id):
                continue
            if kind == f"{prefix}stream_chunk":
                deltas[frame.get("seq", len(deltas))] = frame.get("data", "")
                continue
            if kind in IGNORED or kind.removeprefix("symi.") in IGNORED:
                continue
            frames.append(frame)
            if kind == f"{prefix}context" and isinstance(frame.get("chunks"), list):
                for chunk in frame["chunks"]:
                    text = chunk.get("content") or chunk.get("text") or ""
                    if text and text not in contexts:
                        contexts.append(text)
                        scores[text] = chunk.get("score") or 0
                        titles[text] = chunk.get("document_title")
                    elif text:
                        scores[text] = max(scores[text], chunk.get("score") or 0)
            elif kind == f"{prefix}complete":
                meta = frame.get("metadata") or {}
                break
            elif kind in (f"{prefix}error", "token_limit_exceeded", "rate_limit_exceeded", "dataset_access_denied"):
                errors.append({k: frame.get(k) for k in ("type", "message", "error_code", "error_details")})
                if engine == "symi" or kind != "error":
                    raise RuntimeError(f"{errors}")
                error_deadline = time.monotonic() + 30
    for chunk in meta.get("rag_context_chunks") or []:
        text = chunk.get("content") or ""
        if text and text not in contexts:
            contexts.append(text)
            scores[text] = chunk.get("score") or 0
            titles[text] = chunk.get("document_title")
    # Multi-step retrieval sends one context frame per step. The scorer reads only the first
    # 10,000 characters, so keep 4Minds' own relevance order across all steps.
    contexts.sort(key=lambda text: -scores.get(text, 0))
    answer = "".join(deltas[k] for k in sorted(deltas)).strip()
    return answer, contexts, frames, {"conversation_id": conversation_id, "errors": errors,
                                      "document_titles": [titles.get(text) for text in contexts]}


def sse_turn(http, model_id, q, timeout):
    """SYMI through POST /api/v1/user/inference (API-run mode). Return (answer, contexts, frames, meta).

    The WebSocket SYMI path forwards the caller's credential to symi-gateway, which rejects
    API keys (auth_failed); the REST endpoint adds the server's API-run service key. For API
    keys the context events carry only chunk_id/document_title/score, so contexts stay empty.
    """
    deadline = time.monotonic() + timeout
    body = {"query": q["question"], "model_id": model_id, "inference_engine": "symi", "enable_web_search": False}
    frames, chunks, message, complete, event = [], [], "", None, None
    with http.post(SSE_URL, json=body, stream=True, timeout=(30, 120)) as response:
        if response.status_code in (401, 403):
            raise Fatal(f"HTTP {response.status_code}: {response.text[:300]}")
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
        for line in response.iter_lines(decode_unicode=True):
            if time.monotonic() > deadline:
                raise TimeoutError("no complete event before the timeout")
            if not line or line.startswith(":"):
                continue
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
                continue
            if not line.startswith("data:"):
                continue
            data = json.loads(line.split(":", 1)[1])
            kind = data.get("type") or event
            if kind == "context":
                chunks += data.get("chunks") or []
            elif kind == "message":
                message = data.get("content") or ""
            elif kind == "complete":
                complete = data
            elif kind == "error":
                if data.get("error_code") in ("auth_failed", "missing_credentials"):
                    raise Fatal(f"{data}")
                raise RuntimeError(f"{data}")
            frames.append(data)
            if complete:
                break
    if complete is None:
        raise RuntimeError("stream ended without a complete event")
    contexts = [c["content"] for c in chunks if c.get("content")]
    return message.strip(), contexts, frames, {"conversation_id": complete.get("conversation_id"), "errors": [],
                                               "chunk_refs": chunks}


def make_ask(key, args, model_id):
    http = requests.Session()
    http.headers["X-API-Key"] = key

    def ask(q):
        timing = {}
        out = {}

        def attempt():
            start = time.monotonic()
            try:
                out["result"] = (sse_turn(http, model_id, q, args.timeout) if args.engine == "symi"
                                 else one_turn(key, http, model_id, args.engine, q, args.timeout))
                timing["latency_s"] = round(time.monotonic() - start, 2)
                if not out["result"][0]:
                    return None, {"message": "empty answer", "meta": out["result"][3]}, True
                return out["result"], None, False
            except Fatal as e:
                bc.STOP.set()
                return None, {"code": "fatal", "message": str(e)}, False
            except (WebSocketException, OSError, TimeoutError, RuntimeError, requests.RequestException, ValueError) as e:
                timing["latency_s"] = round(time.monotonic() - start, 2)
                return None, {"code": type(e).__name__, "message": str(e)[:500]}, True

        result, attempts, error = bc.retry(attempt, args)
        if error and error.get("code") == "stopped":
            return None
        if result is None:
            return {"status": "failed", "attempts": attempts, "error": error, **timing}
        answer, contexts, frames, info = result
        meta = next((f.get("metadata") or f for f in frames if f.get("type", "").endswith("complete")), {}) or {}
        usage = {"total_tokens": meta.get("total_tokens") or 0}
        for k, v in (meta.get("token_usage") or {}).items():
            if isinstance(v, (int, float)):
                usage[k] = v
        out = {
            "status": "ok", "attempts": attempts, "answer": answer, "contexts": contexts, "usage": usage,
            "raw": {"frames": frames, "answer": answer},
            "extra": {**info, "chunks": len(contexts), "context_chunks": meta.get("context_chunks"),
                      "reasoning_path": meta.get("reasoning_path"), "persona_applied": meta.get("persona_applied"),
                      "context_strategy": meta.get("context_strategy"), "message_id":
                      next((f.get("message_id") for f in frames if f.get("message_id")), None)},
            **timing,
        }
        if with_ids:
            ids = [setup.dsid_of(t) for t in info.get("document_titles") or []]
            out["document_ids"] = list(dict.fromkeys(i for i in ids if i))
            out["extra"]["unmapped_titles"] = sum(1 for i in ids if not i)
        return out
    with_ids = hasattr(bc.profile, "corpus_documents")
    return ask


def main():
    parser = bc.parser(__doc__, "4minds", workers=4)
    parser.add_argument("--engine", required=True, choices=sorted(PREFIX))
    args = parser.parse_args()
    if args.out_dir == str(bc.RUNS / "4minds"):
        args.out_dir = str(bc.RUNS / f"4minds_{args.engine}")
    if not setup.SETUP_FILE.exists():
        sys.exit(f"Run setup_4minds.py first ({setup.SETUP_FILE} is missing).")
    ids = json.loads(setup.SETUP_FILE.read_text())
    model_id, dataset_id = ids["model_id"], ids["dataset_id"]
    questions = bc.load_questions(args)
    if args.dry_run:
        print(json.dumps({"type": f"{PREFIX[args.engine]}conversation_prompt", "model_id": model_id,
                          "conversation_id": "<new per question>", "prompt": questions[0]["question"]}, indent=2))
        return
    key = bc.load_key("4minds")
    client = setup.Client()

    def readiness():
        ready, state = setup.readiness(client, dataset_id, model_id, (ids.get("ready") or {}).get("stable_total_chunks"))
        if ready is None:
            sys.exit(f"Readiness: 4Minds dataset {dataset_id} / model {model_id} not ready: {state}")
        return ready

    endpoint = SSE_URL if args.engine == "symi" else WS_URL
    settings = {"base_url": setup.BASE, "engine": args.engine, "endpoint": endpoint, "model_id": model_id,
                "dataset_id": dataset_id, "persona_id": ids["persona_id"],
                "system_prompt_via": "persona.behavioralGuidelines", "system_prompt": bc.SYSTEM_PROMPT,
                "context_order": "4Minds chunk score, highest first, across all retrieval steps, no duplicates"}
    if hasattr(bc.profile, "corpus_documents"):
        settings["document_ids"] = "dsid in the chunk document_title (setup_4minds.file_name), chunk score order"
    summary = bc.run(f"4minds_{args.engine}", args, make_ask(key, args, model_id), settings, readiness, None,
                     {"endpoint": endpoint, "model": ids.get("model")})
    sys.exit(1 if bc.STOP.is_set() or summary["failed"] else 0)


if __name__ == "__main__":
    main()

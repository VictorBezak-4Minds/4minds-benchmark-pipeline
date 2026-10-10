#!/usr/bin/env python3
"""Run benchmark questions against Gemini with Vertex AI RAG Engine retrieval.

The corpus is made by setup_rag_engine.py (one corpus that holds only the benchmark corpus).
Each question is one generateContent call with the RAG Engine `retrieval` tool, the
benchmark system prompt, and top_k 5 (the GraphRAG-Bench reference runner value).

Output: runs/<run>/rag_engine/<subset>/predictions.json, in the format of the profile's
prediction().

    ./bench graphrag-bench pilot_rag_engine eval systems/run_rag_engine.py --subset medical \\
        --questions-file data/Questions/pilot_questions.json --out-dir runs/<YYYY-MM-DD>_<name>/rag_engine --workers 10
"""
import json
import sys
import time

import requests

import bench_common as bc
import setup_rag_engine as setup

MODEL_LOCATION = "global"  # gemini-3.8-flash is served only from the global endpoint
RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}
PRICE_IN, PRICE_OUT = 0.75, 3.75  # USD per 1M tokens (Developer API list price, used as an estimate)


def cost(tokens):
    tokens_in = tokens.get("promptTokenCount", 0) + tokens.get("toolUsePromptTokenCount", 0)
    tokens_out = tokens.get("candidatesTokenCount", 0) + tokens.get("thoughtsTokenCount", 0)
    return (tokens_in * PRICE_IN + tokens_out * PRICE_OUT) / 1e6


def endpoint(model):
    return (f"https://aiplatform.googleapis.com/v1/projects/{setup.PROJECT}/locations/{MODEL_LOCATION}"
            f"/publishers/google/models/{model}:generateContent")


def build_request(args, q, corpus_name):
    body = {
        "contents": [{"role": "user", "parts": [{"text": q["question"]}]}],
        "systemInstruction": {"parts": [{"text": bc.SYSTEM_PROMPT}]},
        "tools": [{"retrieval": {"vertexRagStore": {
            "ragResources": [{"ragCorpus": corpus_name}],
            "ragRetrievalConfig": {"topK": args.top_k},
        }}}],
    }
    if args.temperature is not None:
        body["generationConfig"] = {"temperature": args.temperature}
    return body


def parse_response(payload):
    candidate = (payload.get("candidates") or [{}])[0]
    parts = (candidate.get("content") or {}).get("parts", [])
    answer = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    contexts = []
    for chunk in (candidate.get("groundingMetadata") or {}).get("groundingChunks", []):
        text = (chunk.get("retrievedContext") or {}).get("text")
        if text and text not in contexts:
            contexts.append(text)
    return answer, contexts, candidate.get("finishReason")


def retrieve_contexts(session, args, q, corpus_name):
    """The chunk text for the scorer's context field.

    The global generateContent endpoint returns grounding chunks with only uri/title, so the
    same query, corpus and top_k go to retrieveContexts in the corpus region.
    """
    url = f"{session.api}:retrieveContexts"
    body = {"vertexRagStore": {"ragResources": [{"ragCorpus": corpus_name}]},
            "query": {"text": q["question"], "ragRetrievalConfig": {"topK": args.top_k}}}
    for attempt in range(3):
        try:
            response = session.http.post(url, headers=session.headers(), json=body, timeout=120)
            if response.status_code == 200:
                return [c["text"] for c in (response.json().get("contexts") or {}).get("contexts", []) if c.get("text")]
        except requests.RequestException:
            pass
        time.sleep(5 * (attempt + 1))
    return []


def make_ask(session, args, corpus_name):
    url = endpoint(args.model)

    def ask(q):
        body = build_request(args, q, corpus_name)
        timing = {}

        def attempt():
            start = time.monotonic()
            try:
                response = session.http.post(url, headers=session.headers(), json=body, timeout=args.timeout)
            except requests.RequestException as e:
                timing["latency_s"] = round(time.monotonic() - start, 2)
                return None, {"code": "network", "message": str(e)}, True
            timing["latency_s"] = round(time.monotonic() - start, 2)
            try:
                payload = response.json()
            except ValueError:
                payload = {"error": {"message": response.text[:500]}}
            if response.status_code == 200 and "error" not in payload:
                if not payload.get("candidates"):
                    return None, {"message": "no candidates", "feedback": payload.get("promptFeedback")}, True
                return payload, None, False
            error = payload.get("error") or {"message": f"HTTP {response.status_code}"}
            error["http_status"] = response.status_code
            return None, error, response.status_code in RETRYABLE_HTTP

        payload, attempts, error = bc.retry(attempt, args)
        if error and error.get("code") == "stopped":
            return None
        if payload is None:
            return {"status": "failed", "attempts": attempts, "error": error, **timing}
        answer, grounding_texts, finish = parse_response(payload)
        contexts = grounding_texts or retrieve_contexts(session, args, q, corpus_name)
        usage = payload.get("usageMetadata", {})
        grounding = (payload["candidates"][0].get("groundingMetadata") or {}).get("groundingChunks", [])
        return {
            "status": "ok", "attempts": attempts, "answer": answer, "contexts": contexts, "raw": payload,
            "usage": {k: usage.get(k, 0) for k in ("promptTokenCount", "candidatesTokenCount",
                                                   "thoughtsTokenCount", "toolUsePromptTokenCount")},
            "extra": {"finish_reason": finish, "model_version": payload.get("modelVersion"),
                      "grounding_chunks": len(grounding), "retrieved_chunks": len(contexts),
                      "context_source": "groundingMetadata" if grounding_texts else "retrieveContexts"},
            **timing,
        }
    return ask


def main():
    parser = bc.parser(__doc__, "rag_engine")
    parser.add_argument("--model", default="gemini-3.8-flash")
    parser.add_argument("--top-k", type=int, default=5, help="chunks retrieved per question (reference runner: 5)")
    parser.add_argument("--temperature", type=float)
    args = parser.parse_args()

    if not setup.SETUP_FILE.exists():
        sys.exit(f"Run setup_rag_engine.py first ({setup.SETUP_FILE} is missing).")
    setup_data = json.loads(setup.SETUP_FILE.read_text())
    corpus_name = setup_data["corpus"]["name"]
    questions = bc.load_questions(args)
    if args.dry_run:
        print(json.dumps(build_request(args, questions[0], corpus_name), indent=2))
        return
    session = setup.Session(setup_data["location"])

    def readiness():
        ready = setup.readiness(session, corpus_name)
        if ready is None:
            sys.exit(f"Readiness: RAG corpus {corpus_name} has files that are not ACTIVE. Run setup_rag_engine.py.")
        return ready

    settings = {"project": setup.PROJECT, "corpus": corpus_name, "model": args.model,
                "model_location": MODEL_LOCATION, "top_k": args.top_k, "temperature": args.temperature,
                "system_prompt": bc.SYSTEM_PROMPT,
                "context_source": "retrieveContexts in the corpus region when grounding chunks carry no text"}
    summary = bc.run("gemini_rag_engine", args, make_ask(session, args, corpus_name), settings, readiness, cost,
                     {"endpoint": endpoint(args.model), "price_usd_per_1m": {"input": PRICE_IN, "output": PRICE_OUT}})
    sys.exit(1 if bc.STOP.is_set() or summary["failed"] else 0)


if __name__ == "__main__":
    main()

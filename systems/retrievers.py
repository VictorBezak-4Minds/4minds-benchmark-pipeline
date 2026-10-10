"""Retrievers for systems/run_rag.py: they return chunk text for a question, and no answer.

  none                no retrieval (world-knowledge baseline)
  gemini_file_search  Gemini Developer API generateContent with the File Search tool and a
                      metadata filter on the question's `source`. File Search has no search-only
                      API, so a Gemini call makes the search; its answer is discarded and the
                      text of every grounding chunk is returned, in the order of the response.
  vertex_rag_engine   Vertex AI RAG Engine retrieveContexts with the question text (no LLM),
                      on the corpus in shared/rag_engine/setup.json (setup_rag_engine.py).

Each retriever: settings() for run_config.json, readiness(questions) with one real query
(it exits if the store or corpus cannot answer), retrieve(q, timeout) -> (result, error,
retryable) with result = contexts, usage, extra, raw, and cost(tokens).
"""
import json
import sys
import time
from pathlib import Path

import requests

import bench_common as bc
import llm_backends

GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
RETRYABLE_HTTP = {0, 408, 429, 500, 502, 503, 504}
# A File Search reply without chunks is a result only if Gemini ended normally. With no finish
# reason or a MALFORMED_* reason, the reply is incomplete (seen after very long search loops).
COMPLETE_FINISH_REASONS = {"STOP", "MAX_TOKENS"}
NAMES = ["none", "gemini_file_search", "vertex_rag_engine"]
# System instruction of the Gemini call that makes the File Search. groundingChunks holds only
# the chunks that Gemini's text cites, so "cite_each" asks for one cited line per passage. The
# chunk text always comes from groundingChunks, never from Gemini's text.
RETRIEVAL_INSTRUCTIONS = {
    "official": None,  # the benchmark SYSTEM_PROMPT, as in the Gemini + File Search system
    "cite_each": ("Search the knowledge base for passages about the user's question. Do not answer the question. "
                  "For every passage that the search returns, write one short sentence about what that passage "
                  "says, on its own line, so that each passage is cited."),
}


def add_args(parser):
    parser.add_argument("--top-k", type=int, default=5, help="chunks per search (reference runner: 5)")
    parser.add_argument("--store", default=getattr(bc.profile, "GEMINI_FILE_SEARCH_STORE", None),
                        help="gemini_file_search: the File Search store")
    parser.add_argument("--retrieval-model", default="gemini-3.8-flash",
                        help="gemini_file_search: the Gemini model that makes the search")
    parser.add_argument("--retrieval-instruction", choices=sorted(RETRIEVAL_INSTRUCTIONS), default="official",
                        help="gemini_file_search: system instruction of the search call (see RETRIEVAL_INSTRUCTIONS)")
    parser.add_argument("--rag-setup", default=str(bc.SHARED / "rag_engine" / "setup.json"),
                        help="vertex_rag_engine: setup.json from setup_rag_engine.py")


def make(name, args):
    return {"none": NoRetrieval, "gemini_file_search": GeminiFileSearch, "vertex_rag_engine": VertexRagEngine}[name](args)


def http_error(status, payload):
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {"message": str(payload)[:500]}
    error["http_status"] = status
    return error


class NoRetrieval:
    name = "none"

    def __init__(self, args):
        pass

    def settings(self):
        return {"retriever": self.name}

    def readiness(self, questions):
        return {"retriever": self.name}

    def retrieve(self, q, timeout):
        return {"contexts": [], "usage": {}, "extra": {}, "raw": None}, None, False

    def cost(self, tokens):
        return 0.0


class GeminiFileSearch:
    name = "gemini_file_search"

    def __init__(self, args):
        if not args.store:
            sys.exit("gemini_file_search needs --store (or GEMINI_FILE_SEARCH_STORE in the benchmark profile).")
        self.store, self.top_k, self.model = args.store, args.top_k, args.retrieval_model
        self.instruction_name = args.retrieval_instruction
        self.instruction = RETRIEVAL_INSTRUCTIONS[self.instruction_name] or bc.SYSTEM_PROMPT
        self.key = bc.load_key("gemini")
        self.prices = llm_backends.load_all().get(self.model, {}).get("price_usd_per_1m") or {}

    def settings(self):
        return {"retriever": self.name, "store": self.store, "top_k": self.top_k, "retrieval_model": self.model,
                "retrieval_instruction": self.instruction_name, "retrieval_system_prompt": self.instruction,
                "retrieval_api": "generateContent"}

    def request_body(self, q):
        return {"contents": [{"role": "user", "parts": [{"text": q["question"]}]}],
                "systemInstruction": {"parts": [{"text": self.instruction}]},
                "tools": [{"fileSearch": {"fileSearchStoreNames": [self.store],
                                          "metadataFilter": f'source = "{q["source"]}"', "topK": self.top_k}}]}

    def call(self, method, url, body=None, timeout=60):
        try:
            response = requests.request(method, url, json=body, timeout=timeout,
                                        headers={"x-goog-api-key": self.key})
            return response.status_code, response.json() if response.content else {}
        except requests.RequestException as e:
            return 0, {"error": {"code": "network", "message": str(e)[:500]}}
        except ValueError:
            return response.status_code, {"error": {"message": response.text[:500]}}

    def retrieve(self, q, timeout):
        status, payload = self.call("POST", f"{GEMINI_API}/models/{self.model}:generateContent",
                                    self.request_body(q), timeout)
        if status != 200 or "error" in payload:
            error = http_error(status, payload)
            if status == 429 and "per day" in str(error.get("message", "")).lower():
                bc.STOP.set()
                return None, error, False
            return None, error, status in RETRYABLE_HTTP
        candidate = (payload.get("candidates") or [{}])[0]
        grounding = candidate.get("groundingMetadata") or {}
        contexts, titles = [], []
        for chunk in grounding.get("groundingChunks") or []:
            context = chunk.get("retrievedContext") or {}
            text = (context.get("text") or "").strip()
            if text and text not in contexts:
                contexts.append(text)
                titles.append(context.get("title"))
        usage_metadata = payload.get("usageMetadata") or {}
        usage = {f"retrieval_{k}": usage_metadata.get(k, 0) for k in
                 ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount", "toolUsePromptTokenCount")}
        finish_reason = candidate.get("finishReason")
        if not contexts and finish_reason not in COMPLETE_FINISH_REASONS:
            return None, {"code": "incomplete_response", "finish_reason": finish_reason,
                          "message": "File Search reply has no chunks and no normal finish reason",
                          "usage": usage}, True
        extra = {"retrieval_chunks": len(contexts), "grounding_chunks_raw": len(grounding.get("groundingChunks") or []),
                 "retrieval_titles": sorted(set(t for t in titles if t)),
                 "searched": bool(grounding), "grounding_keys": sorted(grounding),
                 "retrieval_finish_reason": finish_reason}
        return {"contexts": contexts, "extra": extra, "raw": payload, "usage": usage}, None, False

    def readiness(self, questions):
        status, store = self.call("GET", f"{GEMINI_API}/{self.store}")
        if status != 200:
            sys.exit(f"Readiness: cannot read {self.store}: HTTP {status} {store.get('error')}")
        counts = {k: int(store.get(k) or 0) for k in
                  ("activeDocumentsCount", "pendingDocumentsCount", "failedDocumentsCount")}
        if counts["pendingDocumentsCount"] or counts["failedDocumentsCount"] or not counts["activeDocumentsCount"]:
            sys.exit(f"Readiness: store {self.store} not ready: {counts}")
        result, error, _ = self.retrieve(questions[0], 120)
        if error or not result["contexts"]:
            sys.exit(f"Readiness: File Search query on {self.store} returned no chunks: {error or result['extra']}")
        return {"retriever": self.name, "store": self.store, **counts, "query_check_chunks": len(result["contexts"])}

    def cost(self, tokens):
        tokens_in = tokens.get("retrieval_promptTokenCount", 0) + tokens.get("retrieval_toolUsePromptTokenCount", 0)
        tokens_out = tokens.get("retrieval_candidatesTokenCount", 0) + tokens.get("retrieval_thoughtsTokenCount", 0)
        return (tokens_in * self.prices.get("input", 0) + tokens_out * self.prices.get("output", 0)) / 1e6


class VertexRagEngine:
    name = "vertex_rag_engine"

    def __init__(self, args):
        import setup_rag_engine as rag
        path = Path(args.rag_setup)
        if not path.exists():
            sys.exit(f"{path} does not exist. Run setup_rag_engine.py first.")
        self.setup = json.loads(path.read_text())
        self.corpus = self.setup["corpus"]["name"]
        self.session = rag.Session(self.setup["location"])
        self.top_k = args.top_k

    def settings(self):
        return {"retriever": self.name, "corpus": self.corpus, "location": self.setup["location"],
                "project": self.setup["project"], "top_k": self.top_k, "retrieval_api": "retrieveContexts"}

    def retrieve(self, q, timeout):
        try:
            response = self.session.http.post(f"{self.session.api}:retrieveContexts", headers=self.session.headers(),
                                              timeout=timeout, json={
                    "vertexRagStore": {"ragResources": [{"ragCorpus": self.corpus}]},
                    "query": {"text": q["question"], "ragRetrievalConfig": {"topK": self.top_k}}})
            payload = response.json() if response.content else {}
        except (requests.RequestException, ValueError) as e:
            return None, {"code": "network", "message": str(e)[:500]}, True
        if response.status_code != 200:
            return None, http_error(response.status_code, payload), response.status_code in RETRYABLE_HTTP
        chunks = (payload.get("contexts") or {}).get("contexts") or []
        contexts = [c.get("text", "").strip() for c in chunks if c.get("text", "").strip()]
        extra = {"retrieval_chunks": len(contexts), "retrieval_scores": [c.get("score") for c in chunks],
                 "retrieval_sources": sorted(set(c.get("sourceDisplayName") or c.get("sourceUri") or "" for c in chunks))}
        return {"contexts": contexts, "usage": {}, "extra": extra, "raw": payload}, None, False

    def readiness(self, questions):
        import setup_rag_engine as rag
        ready = rag.readiness(self.session, self.corpus)
        if ready is None:
            sys.exit(f"Readiness: RAG Engine corpus {self.corpus} has files that are not ACTIVE.")
        start = time.monotonic()
        result, error, _ = self.retrieve(questions[0], 120)
        if error or not result["contexts"]:
            sys.exit(f"Readiness: retrieveContexts on {self.corpus} failed: {error or result['extra']}")
        return {"retriever": self.name, **ready, "location": self.setup["location"],
                "query_check_chunks": len(result["contexts"]), "query_check_s": round(time.monotonic() - start, 2)}

    def cost(self, tokens):
        return None

"""Retrievers for systems/run_rag.py: they return chunk text for a question, and no answer.

  none                no retrieval (world-knowledge baseline)
  gemini_file_search  Gemini Developer API generateContent with the File Search tool and a
                      metadata filter on the question's `source`. File Search has no search-only
                      API, so a Gemini call makes the search; its answer is discarded and the
                      text of every grounding chunk is returned, in the order of the response.
  vertex_rag_engine   Vertex AI RAG Engine retrieveContexts with the question text (no LLM),
                      on the corpus in shared/rag_engine/setup.json (setup_rag_engine.py).
  langchain_vector    LangChain FAISS index of the profile's documents (setup_langchain.py):
                      --chunk-limit chunks by similarity, then the first --top-k unique documents
                      in rank order; each context is one full document in the profile's
                      format_context_document() layout (the official EnterpriseRAG-Bench vector
                      baseline). Returns document_ids.
  graphrag_local      Microsoft GraphRAG index (setup_graphrag.py): the context of GraphRAG local
                      search (the official engine's context builder, default settings, community
                      level --community-level), as one context; GraphRAG's own answer prompt is not
                      used. document_ids are the documents of the text units in the "sources" table.

Each retriever: settings() for run_config.json, readiness(questions) with one real query
(it exits if the store or corpus cannot answer), retrieve(q, timeout) -> (result, error,
retryable) with result = contexts, usage, extra, raw (and document_ids when the retriever knows
the documents), and cost(tokens).
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
NAMES = ["none", "gemini_file_search", "vertex_rag_engine", "langchain_vector", "graphrag_local"]
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
    parser.add_argument("--chunk-limit", type=int, default=100,
                        help="langchain_vector: chunks to fetch before deduplication to --top-k documents")
    parser.add_argument("--langchain-index", default=str(bc.SHARED / "langchain" / bc.profile.RESOURCE_NAME),
                        help="langchain_vector: the folder from setup_langchain.py")
    parser.add_argument("--graphrag-index", default=str(bc.SHARED / "graphrag" / bc.profile.RESOURCE_NAME),
                        help="graphrag_local: the folder from setup_graphrag.py")
    parser.add_argument("--community-level", type=int, default=2,
                        help="graphrag_local: community level of the reports (GraphRAG CLI default: 2)")


def make(name, args):
    return {"none": NoRetrieval, "gemini_file_search": GeminiFileSearch, "vertex_rag_engine": VertexRagEngine,
            "langchain_vector": LangChainVector, "graphrag_local": GraphRAGLocal}[name](args)


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


class LangChainVector:
    name = "langchain_vector"

    def __init__(self, args):
        import tiktoken
        from langchain_community.vectorstores import FAISS
        from langchain_community.vectorstores.utils import DistanceStrategy
        from langchain_openai import OpenAIEmbeddings
        self.folder = Path(args.langchain_index)
        path = self.folder / "index_manifest.json"
        if not path.exists():
            sys.exit(f"{path} does not exist. Run systems/setup_langchain.py first.")
        self.index = json.loads(path.read_text())
        embedding = self.index["embedding"]
        backend = llm_backends.Backend(embedding["llm_backend"])
        self.prices = backend.prices
        self.embeddings = OpenAIEmbeddings(model=backend.model, api_key=backend.api_key(), base_url=backend.base_url,
                                           check_embedding_ctx_length=False, max_retries=0)
        # load_local() does not restore these two settings of setup_langchain.py.
        vector_store = self.index["vector_store"]
        self.store = FAISS.load_local(str(self.folder), self.embeddings, allow_dangerous_deserialization=True,
                                      distance_strategy=DistanceStrategy[vector_store["distance"]],
                                      normalize_L2=vector_store["normalize_L2"])
        self.encoding = tiktoken.get_encoding("cl100k_base")
        self.top_k, self.chunk_limit = args.top_k, args.chunk_limit

    def settings(self):
        return {"retriever": self.name, "index": str(self.folder), "embedding_model": self.index["embedding"]["llm_model"],
                "splitter": self.index["splitter"], "vector_store": self.index["vector_store"],
                "chunk_limit": self.chunk_limit, "top_k_documents": self.top_k,
                "context": "full documents, profile format_context_document()"}

    def retrieve(self, q, timeout):
        start = time.monotonic()
        try:
            vector = self.embeddings.embed_query(q["question"])
            hits = self.store.similarity_search_with_score_by_vector(vector, k=self.chunk_limit)
        except Exception as e:  # openai raises many types; all are retried
            return None, {"code": type(e).__name__, "message": str(e)[:500]}, True
        seen, ranked = set(), []
        for doc, score in hits:
            dsid = doc.metadata["dsid"]
            if dsid not in seen:
                seen.add(dsid)
                ranked.append((dsid, doc.metadata["path"], float(score)))
            if len(ranked) >= self.top_k:
                break
        docs = [bc.profile.document(dsid, path) for dsid, path, _ in ranked]
        contexts = [bc.profile.format_context_document(i, d) for i, d in enumerate(docs, 1)]
        usage = {"embedding_tokens": len(self.encoding.encode(q["question"], disallowed_special=()))}
        extra = {"retrieval_documents": len(docs), "retrieval_chunks": len(hits),
                 "retrieval_scores": [round(s, 4) for _, _, s in ranked],
                 "context_chars": sum(map(len, contexts)), "retrieval_search_s": round(time.monotonic() - start, 2)}
        return {"contexts": contexts, "document_ids": [d["dsid"] for d in docs], "usage": usage, "extra": extra,
                "raw": {"ranked": ranked}}, None, False

    def readiness(self, questions):
        if self.index["corpus_sha256"] != bc.sha256(bc.CORPUS_FILE):
            sys.exit(f"Readiness: the index in {self.folder} was built from another corpus file.")
        if self.store.index.ntotal != self.index["chunks"]:
            sys.exit(f"Readiness: the index has {self.store.index.ntotal} vectors, not {self.index['chunks']}.")
        result, error, _ = self.retrieve(questions[0], 120)
        if error or len(result["document_ids"]) < self.top_k:
            sys.exit(f"Readiness: a query on {self.folder} failed: {error or result['extra']}")
        return {"retriever": self.name, "documents": self.index["documents"], "chunks": self.index["chunks"],
                "query_check_documents": len(result["document_ids"])}

    def cost(self, tokens):
        return tokens.get("embedding_tokens", 0) * self.prices.get("input", 0) / 1e6


class GraphRAGLocal:
    name = "graphrag_local"

    def __init__(self, args):
        import pandas as pd
        import tiktoken
        import graphrag_hooks
        from graphrag.config.embeddings import entity_description_embedding
        from graphrag.query.factory import get_local_search_engine
        from graphrag.query.indexer_adapters import (read_indexer_entities, read_indexer_relationships,
                                                     read_indexer_reports, read_indexer_text_units)
        from graphrag.utils.api import get_embedding_store
        self.folder = Path(args.graphrag_index)
        path = self.folder / "index_manifest.json"
        if not path.exists():
            sys.exit(f"{path} does not exist. Run systems/setup_graphrag.py first.")
        self.index = json.loads(path.read_text())
        chat = llm_backends.Backend(self.index["llm"]["llm_backend"])
        embedding = llm_backends.Backend(self.index["embedding"]["llm_backend"])
        self.prices = embedding.prices
        graphrag_hooks.install_hooks(chat)
        config = graphrag_hooks.config(self.folder, chat, embedding, self.index["concurrency"])
        self.local_search = config.local_search.model_dump(mode="json")
        tables = {t: pd.read_parquet(self.folder / "output" / f"{t}.parquet") for t in
                  ("entities", "communities", "community_reports", "text_units", "relationships")}
        self.community_level = args.community_level
        # The steps of graphrag.api.local_search; only the context builder of the engine is used.
        engine = get_local_search_engine(
            config=config,
            reports=read_indexer_reports(tables["community_reports"], tables["communities"], self.community_level),
            text_units=read_indexer_text_units(tables["text_units"]),
            entities=read_indexer_entities(tables["entities"], tables["communities"], self.community_level),
            relationships=read_indexer_relationships(tables["relationships"]),
            covariates={"claims": []},
            description_embedding_store=get_embedding_store(config=config.vector_store,
                                                            embedding_name=entity_description_embedding),
            response_type="multiple paragraphs", system_prompt=None)
        self.context_builder, self.context_params = engine.context_builder, engine.context_builder_params
        units = tables["text_units"]
        self.unit_documents = dict(zip(units["human_readable_id"].astype(str), units["document_id"]))
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def settings(self):
        return {"retriever": self.name, "index": str(self.folder), "method": self.index["method"],
                "embedding_model": self.index["embedding"]["llm_model"], "community_level": self.community_level,
                "local_search": self.local_search,
                "context": "GraphRAG local search context (reports, entities, relationships, sources), one context"}

    def retrieve(self, q, timeout):
        start = time.monotonic()
        try:
            result = self.context_builder.build_context(query=q["question"], **self.context_params)
        except Exception as e:  # litellm and lancedb raise many types; all are retried
            return None, {"code": type(e).__name__, "message": str(e)[:500]}, True
        context = result.context_chunks if isinstance(result.context_chunks, str) else "\n\n".join(result.context_chunks)
        records = result.context_records or {}
        sources = records.get("sources")
        units = [] if sources is None else [str(i) for i in sources["id"]]
        document_ids = list(dict.fromkeys(self.unit_documents[u] for u in units if u in self.unit_documents))
        usage = {"embedding_tokens": len(self.encoding.encode(q["question"], disallowed_special=()))}
        extra = {"retrieval_documents": len(document_ids), "retrieval_text_units": len(units),
                 "context_records": {k: len(v) for k, v in records.items()}, "context_chars": len(context),
                 "retrieval_search_s": round(time.monotonic() - start, 2)}
        return {"contexts": [context] if context.strip() else [], "document_ids": document_ids, "usage": usage,
                "extra": extra, "raw": {"text_units": units}}, None, False

    def readiness(self, questions):
        if not self.index.get("complete"):
            sys.exit(f"Readiness: the index in {self.folder} is not complete: {self.index.get('errors')}")
        if self.index.get("limit"):
            sys.exit(f"Readiness: the index in {self.folder} is a --limit {self.index['limit']} test index.")
        if self.index["corpus_sha256"] != bc.sha256(bc.CORPUS_FILE):
            sys.exit(f"Readiness: the index in {self.folder} was built from another corpus file.")
        result, error, _ = self.retrieve(questions[0], 120)
        if error or not result["document_ids"]:
            sys.exit(f"Readiness: a query on {self.folder} failed: {error or result['extra']}")
        return {"retriever": self.name, "documents": self.index["documents"], "tables": self.index["tables"],
                "query_check_documents": len(result["document_ids"])}

    def cost(self, tokens):
        return tokens.get("embedding_tokens", 0) * self.prices.get("input", 0) / 1e6

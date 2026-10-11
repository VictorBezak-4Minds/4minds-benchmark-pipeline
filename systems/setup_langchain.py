#!/usr/bin/env python3
"""Build the LangChain vector index (FAISS) of the profile's documents (environment `erag`).

    ./bench enterpriserag-bench setup_langchain erag systems/setup_langchain.py

A copy of the official EnterpriseRAG-Bench vector baseline (src/scripts/answer_generation/
index_document_vectors.py), with LangChain parts in place of Qdrant:
- text of a document = profile document()["text"] (title, blank line, content);
- TokenTextSplitter, cl100k_base, 512 tokens, overlap int(512 * 0.1) = 51, special tokens
  allowed (the same loop as the official chunk_text());
- OpenAIEmbeddings with the --embedding backend (text-embedding-3-large), the text is sent as
  text (check_embedding_ctx_length off, as the official client does);
- FAISS inner product on normalized vectors (the ranking of the official cosine distance).
Each chunk has the metadata dsid, path and chunk index. The embeddings are saved in batches
under the index folder, so a stopped build continues where it stopped.

Output: shared/langchain/<RESOURCE_NAME>/ with the FAISS files and index_manifest.json.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

import bench_common as bc
import llm_backends

CHUNK_SIZE = 512
OVERLAP = int(CHUNK_SIZE * 0.1)


def chunks_of(docs):
    from langchain_text_splitters import TokenTextSplitter
    splitter = TokenTextSplitter(encoding_name="cl100k_base", chunk_size=CHUNK_SIZE, chunk_overlap=OVERLAP,
                                 disallowed_special=())
    texts, metadatas = [], []
    for d in docs:
        for i, chunk in enumerate(splitter.split_text(d["text"])):
            texts.append(chunk)
            metadatas.append({"dsid": d["dsid"], "path": d["path"], "chunk": i})
    return texts, metadatas


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--embedding", default="openai-text-embedding-3-large", choices=llm_backends.names())
    parser.add_argument("--batch", type=int, default=200, help="chunks per embedding request (limit 300k tokens)")
    parser.add_argument("--dry-run", action="store_true", help="count the chunks and tokens, and stop")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    import tiktoken
    from langchain_community.vectorstores import FAISS
    from langchain_community.vectorstores.utils import DistanceStrategy
    from langchain_openai import OpenAIEmbeddings

    backend = llm_backends.Backend(args.embedding)
    out = bc.SHARED / "langchain" / bc.profile.RESOURCE_NAME
    out.mkdir(parents=True, exist_ok=True)
    bc.acquire_lock(out / ".index.lock")
    corpus_sha = bc.sha256(bc.CORPUS_FILE)
    manifest_path = out / "index_manifest.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text()).get("corpus_sha256") == corpus_sha \
            and (out / "index.faiss").exists():
        print(f"Index already complete: {manifest_path}")
        return

    docs = bc.profile.corpus_documents()
    texts, metadatas = chunks_of(docs)
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = sum(len(encoding.encode(t, disallowed_special=())) for t in texts)
    estimate = tokens * backend.prices.get("input", 0) / 1e6
    print(f"{len(docs)} documents -> {len(texts)} chunks, {tokens} tokens, estimated cost ${estimate:.2f}")
    if args.dry_run:
        return

    embeddings = OpenAIEmbeddings(model=backend.model, api_key=backend.api_key(), base_url=backend.base_url,
                                  check_embedding_ctx_length=False, max_retries=10)
    batch_dir = out / "embeddings"
    batch_dir.mkdir(exist_ok=True)
    bc.audit("langchain_index_start", out=str(out), documents=len(docs), chunks=len(texts), tokens=tokens)
    start = time.monotonic()
    batches = range(0, len(texts), args.batch)
    for n, i in enumerate(batches, 1):
        path = batch_dir / f"{i:08d}.npy"
        if path.exists():
            continue
        vectors = np.asarray(embeddings.embed_documents(texts[i:i + args.batch]), dtype="float32")
        np.save(path, vectors)
        if n % 25 == 0 or n == len(batches):
            print(f"  {bc.now()} batch {n}/{len(batches)} ({time.monotonic() - start:.0f} s)")
    vectors = np.concatenate([np.load(batch_dir / f"{i:08d}.npy") for i in batches])
    if len(vectors) != len(texts):
        sys.exit(f"{len(vectors)} embeddings for {len(texts)} chunks. Delete {batch_dir} and build again.")
    store = FAISS.from_embeddings(list(zip(texts, vectors.tolist())), embeddings, metadatas=metadatas,
                                  distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT, normalize_L2=True)
    store.save_local(str(out))
    manifest = {"finished": bc.now(), "build_wall_clock_s": round(time.monotonic() - start, 1),
                "documents": len(docs), "chunks": len(texts), "embedding_tokens": tokens,
                "estimated_cost_usd": round(estimate, 4), "embedding": backend.settings(),
                "splitter": {"class": "TokenTextSplitter", "encoding": "cl100k_base", "chunk_size": CHUNK_SIZE,
                             "chunk_overlap": OVERLAP, "disallowed_special": []},
                "vector_store": {"class": "FAISS", "distance": "MAX_INNER_PRODUCT", "normalize_L2": True,
                                 "ntotal": store.index.ntotal},
                "corpus": str(bc.CORPUS_FILE), "corpus_sha256": corpus_sha, "packages": bc.package_versions()}
    manifest_path.write_text(json.dumps(manifest, indent=2))
    bc.audit("langchain_index_end", **{k: v for k, v in manifest.items() if k != "packages"})
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

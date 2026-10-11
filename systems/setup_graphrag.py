#!/usr/bin/env python3
"""Build the Microsoft GraphRAG index of the profile's documents (environment `graphrag`).

    ./bench enterpriserag-bench setup_graphrag graphrag systems/setup_graphrag.py [--limit 500] [--dry-run]

GraphRAG 3.3.0 with its default settings (chunks of 1,200 tokens with 100 overlap, communities of
at most 10 entities, community reports of at most 2,000 tokens) and the fast indexing method
(`--method fast`): NLP noun phrases make the graph, and the LLM writes only the community reports.
- documents: profile document()["text"] (title, blank line, content); the GraphRAG document id
  is the profile dsid, so the text units keep it;
- chat model: --llm (GPT-OSS-120B on Bedrock) for the community reports, without call
  parameters (GraphRAG defaults); embeddings: --embedding (text-embedding-3-large);
- hooks (systems/graphrag_hooks.py): Bedrock token on each call, <reasoning> removed, JSON of
  community reports repaired when possible, tokens counted.
GraphRAG keeps an LLM cache under the index folder, so a stopped build costs little when it runs
again (a run again also rebuilds the tables, so a report that failed on a reply that the repair
can now read is added from the cache).

--limit N indexes only the first N documents of the corpus list, in a separate folder
(<RESOURCE_NAME>_first<N>): a test that measures time and cost. The runners do not accept it.

Output: shared/graphrag/<RESOURCE_NAME>[_first<N>]/ with output/ (parquet, lancedb), cache/,
logs/ and index_manifest.json.
"""
import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

import bench_common as bc
import graphrag_hooks as gh
import llm_backends

TABLES = ["documents", "text_units", "entities", "relationships", "communities", "community_reports"]


def index_folder(limit):
    return bc.SHARED / "graphrag" / (bc.profile.RESOURCE_NAME + (f"_first{limit}" if limit else ""))


def table_counts(output):
    import pandas as pd
    return {t: len(pd.read_parquet(output / f"{t}.parquet")) for t in TABLES if (output / f"{t}.parquet").exists()}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--llm", default="bedrock-gpt-oss-120b", choices=llm_backends.names())
    parser.add_argument("--embedding", default="openai-text-embedding-3-large", choices=llm_backends.names())
    parser.add_argument("--limit", type=int, help="index only the first N documents (a cost test)")
    parser.add_argument("--concurrency", type=int, help="parallel LLM requests (default: the backend max_concurrency)")
    parser.add_argument("--max-missing-share", type=float, default=0.02,
                        help="the index is complete if at most this share of communities has no report "
                             "(GraphRAG skips a report when the reply is not valid JSON)")
    parser.add_argument("--dry-run", action="store_true", help="count the documents and tokens, and stop")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    import pandas as pd
    import tiktoken
    from graphrag.api import build_index
    from graphrag.config.enums import IndexingMethod

    chat, embedding = llm_backends.Backend(args.llm), llm_backends.Backend(args.embedding)
    concurrency = args.concurrency or chat.max_concurrency
    out = index_folder(args.limit)
    out.mkdir(parents=True, exist_ok=True)
    bc.acquire_lock(out / ".index.lock")
    corpus_sha = bc.sha256(bc.CORPUS_FILE)
    manifest_path = out / "index_manifest.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if previous.get("complete") and previous.get("corpus_sha256") == corpus_sha:
        print(f"Index already complete: {manifest_path}")
        return

    docs = bc.profile.corpus_documents()
    if args.limit:
        docs = docs[:args.limit]
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = sum(len(encoding.encode(d["text"], disallowed_special=())) for d in docs)
    print(f"{len(docs)} documents, {tokens} tokens (cl100k_base), concurrency {concurrency}, out {out}")
    if args.dry_run:
        return

    gh.install_hooks(chat)
    config = gh.config(out, chat, embedding, concurrency)
    frame = pd.DataFrame({"id": [d["dsid"] for d in docs], "title": [d["title"] for d in docs],
                          "text": [d["text"] for d in docs], "creation_date": ["" for _ in docs]})
    bc.audit("graphrag_index_start", out=str(out), documents=len(docs), tokens=tokens, limit=args.limit,
             llm=args.llm, embedding=args.embedding, concurrency=concurrency)
    start = time.monotonic()
    errors = []
    try:
        results = asyncio.run(build_index(config=config, method=IndexingMethod.Fast, input_documents=frame))
        errors = [f"{r.workflow}: {r.error!r}"[:500] for r in results if r.error is not None]
    except Exception as e:
        errors = [f"{type(e).__name__}: {e}"[:500]]
    wall = round(time.monotonic() - start, 1)
    usage = {m: {k: previous.get("usage", {}).get(m, {}).get(k, 0) + v for k, v in row.items()}
             for m, row in gh.USAGE.items()}
    for m, row in previous.get("usage", {}).items():
        usage.setdefault(m, row)
    counts = table_counts(out / "output")
    missing = counts.get("communities", 0) - counts.get("community_reports", 0)
    if gh.NOT_JSON["samples"]:
        (out / "logs" / "not_json_samples.json").write_text(json.dumps(gh.NOT_JSON, indent=2))
    manifest = {"finished": bc.now(),
                "complete": not errors and counts.get("documents") == len(docs)
                            and missing <= args.max_missing_share * counts.get("communities", 0),
                "errors": errors, "reports_missing": missing, "max_missing_share": args.max_missing_share,
                "not_json_replies": gh.NOT_JSON["count"],
                "json_replies_repaired": gh.NOT_JSON["repaired"],
                "index_wall_clock_s": round(previous.get("index_wall_clock_s", 0) + wall, 1),
                "documents": len(docs), "limit": args.limit, "corpus_tokens": tokens, "tables": counts,
                "usage": usage, "estimated_cost_usd": gh.cost(usage, chat, embedding),
                "method": "fast", "concurrency": concurrency, "index_call_args": {},
                "llm": chat.settings(), "embedding": embedding.settings(),
                "settings": {k: config.model_dump(mode="json")[k] for k in
                             ("chunking", "extract_graph_nlp", "prune_graph", "cluster_graph", "community_reports",
                              "embed_text", "local_search")},
                "document_ids_sha256": hashlib.sha256("\n".join(d["dsid"] for d in docs).encode()).hexdigest(),
                "corpus": str(bc.CORPUS_FILE), "corpus_sha256": corpus_sha, "packages": bc.package_versions()}
    manifest_path.write_text(json.dumps(manifest, indent=2))
    bc.audit("graphrag_index_end", **{k: v for k, v in manifest.items() if k not in ("packages", "settings", "llm", "embedding")})
    print(json.dumps({k: v for k, v in manifest.items() if k not in ("packages", "settings")}, indent=2))
    sys.exit(0 if manifest["complete"] else 1)


if __name__ == "__main__":
    main()

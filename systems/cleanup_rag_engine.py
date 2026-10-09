#!/usr/bin/env python3
"""Delete the benchmark RAG corpus and set the RAG Engine tier to unprovisioned (stops Spanner billing).

    ./bench graphrag-bench cleanup_rag_engine eval systems/cleanup_rag_engine.py

Unprovisioned deletes all RAG Engine data in the region, so the script stops if the region
holds any corpus other than the benchmark corpus.
"""
import json
import sys

import bench_common as bc
import setup_rag_engine as rag


def main():
    session = rag.Session()
    corpora = rag.list_all(session, f"{rag.API}/ragCorpora", "ragCorpora")
    others = [c["name"] for c in corpora if c.get("displayName") != rag.DISPLAY_NAME]
    if others:
        sys.exit(f"Other corpora exist in {rag.LOCATION}: {others}. Not changing the tier.")
    for corpus in corpora:
        rag.Session.wait(session, session.call("DELETE", f"https://{rag.LOCATION}-aiplatform.googleapis.com/v1/"
                                                         f"{corpus['name']}", params={"force": "true"}))
        bc.audit("rag_engine_corpus_deleted", corpus=corpus["name"])
        print(f"deleted {corpus['name']}")

    before = session.call("GET", f"{rag.API}/ragEngineConfig")
    operation = session.call("PATCH", f"{rag.API}/ragEngineConfig",
                             json={"name": before["name"], "ragManagedDbConfig": {"unprovisioned": {}}})
    rag.Session.wait(session, operation)
    after = session.call("GET", f"{rag.API}/ragEngineConfig")
    remaining = rag.list_all(session, f"{rag.API}/ragCorpora", "ragCorpora")
    bc.audit("rag_engine_unprovisioned", location=rag.LOCATION, before=before, after=after,
             remaining_corpora=len(remaining))
    print(json.dumps({"before": before, "after": after, "remaining_corpora": len(remaining)}, indent=2))


if __name__ == "__main__":
    main()

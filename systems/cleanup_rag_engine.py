#!/usr/bin/env python3
"""Delete the benchmark RAG corpus and set the RAG Engine tier to unprovisioned (stops Spanner billing).

    ./bench graphrag-bench cleanup_rag_engine eval systems/cleanup_rag_engine.py [--location us-central1]

The default location is the one in shared/rag_engine/setup.json (else europe-west4).
Unprovisioned deletes all RAG Engine data in the region, so the script stops if the region
holds any corpus other than the benchmark corpus.
"""
import argparse
import json
import sys

import bench_common as bc
import setup_rag_engine as rag


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    default = json.loads(rag.SETUP_FILE.read_text())["location"] if rag.SETUP_FILE.exists() else rag.LOCATION
    parser.add_argument("--location", default=default)
    args = parser.parse_args()
    session = rag.Session(args.location)
    corpora = rag.list_all(session, f"{session.api}/ragCorpora", "ragCorpora")
    others = [c["name"] for c in corpora if c.get("displayName") != rag.DISPLAY_NAME]
    if others:
        sys.exit(f"Other corpora exist in {session.location}: {others}. Not changing the tier.")
    for corpus in corpora:
        session.wait(session.call("DELETE", f"{session.host}/v1/{corpus['name']}", params={"force": "true"}))
        bc.audit("rag_engine_corpus_deleted", corpus=corpus["name"])
        print(f"deleted {corpus['name']}")

    before = session.call("GET", f"{session.api}/ragEngineConfig")
    operation = session.call("PATCH", f"{session.api}/ragEngineConfig",
                             json={"name": before["name"], "ragManagedDbConfig": {"unprovisioned": {}}})
    session.wait(operation)
    after = session.call("GET", f"{session.api}/ragEngineConfig")
    remaining = rag.list_all(session, f"{session.api}/ragCorpora", "ragCorpora")
    bc.audit("rag_engine_unprovisioned", location=session.location, before=before, after=after,
             remaining_corpora=len(remaining))
    print(json.dumps({"before": before, "after": after, "remaining_corpora": len(remaining)}, indent=2))


if __name__ == "__main__":
    main()

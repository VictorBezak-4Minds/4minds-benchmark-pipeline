#!/usr/bin/env python3
"""Make the full EnterpriseRAG-Bench corpus list.

    ./bench enterpriserag-bench make_full_corpus eval make_full_corpus.py

- data/full_corpus.json: every document of upstream uuid_index.json that the official
  extract_document_content() can read, in dsid order (git ignores it: about 70 MB).
- data/full_manifest.json: the counts, the unreadable documents and the sha256 of every input
  and output.
"""
import collections
import json

import bench_common as bc

DATA = bc.BENCH_DIR / "data"
CORPUS = DATA / "full_corpus.json"


def main():
    profile = bc.profile
    index = json.loads(profile.UUID_INDEX.read_text())
    documents, unreadable, chars = [], [], 0
    for dsid, path in sorted(index.items()):
        try:
            chars += len(profile.document(dsid, path)["text"])
        except Exception as e:
            unreadable.append({"dsid": dsid, "path": path, "error": f"{type(e).__name__}: {e}"[:200]})
            continue
        documents.append({"dsid": dsid, "path": path})

    DATA.mkdir(parents=True, exist_ok=True)
    CORPUS.write_text(json.dumps({"description": "EnterpriseRAG-Bench full corpus (make_full_corpus.py)",
                                  "documents": documents}))
    manifest = {
        "created": bc.now(),
        "upstream_commit": profile.UPSTREAM_COMMIT,
        "uuid_index_sha256": bc.sha256(profile.UUID_INDEX),
        "corpus_documents_total": len(index),
        "documents": len(documents),
        "by_source": collections.Counter(d["path"].split("/")[0] for d in documents),
        "unreadable": unreadable,
        "chars": chars,
        "outputs": {CORPUS.name: bc.sha256(CORPUS)},
    }
    (DATA / "full_manifest.json").write_text(json.dumps(manifest, indent=2))
    bc.audit("make_full_corpus", documents=len(documents), unreadable=len(unreadable), chars=chars,
             outputs=manifest["outputs"])
    print(json.dumps({k: v for k, v in manifest.items() if k != "unreadable"}, indent=2))
    print(f"unreadable: {len(unreadable)}")


if __name__ == "__main__":
    main()

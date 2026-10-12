#!/usr/bin/env python3
"""Check the file list of a 4Minds dataset against shared/<shared-name>/file_map.json (read only).

    ./bench enterpriserag-bench check_4minds_full eval systems/check_4minds_files.py --dataset-id 4051 --shared-name 4minds_full

Counts the dataset files, the duplicate names (case-insensitive, the server's skip rule), the
document IDs that are in more than one file, the files that are not in the file map, and the
documents of the file map that the dataset does not have yet. Exits 1 if there is a duplicate
or an unknown file.
"""
import argparse
import collections
import json
import sys

import bench_common as bc
import setup_4minds as setup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-id", type=int, required=True)
    parser.add_argument("--shared-name", default="4minds", help="folder in shared/ with file_map.json")
    parser.add_argument("--batch", type=int, default=1000,
                        help="upload batch size, to count the file status values for each batch")
    args = parser.parse_args()
    file_map = json.loads((bc.SHARED / args.shared_name / "file_map.json").read_text())

    dataset = setup.Client().call("GET", f"/api/v1/user/dataset/{args.dataset_id}")
    files = [f for f in dataset.get("files") or [] if isinstance(f, dict)]
    names = [f.get("name") for f in files]
    position = {name: i for i, name in enumerate(file_map)}
    print("file keys:", dict(collections.Counter(k for f in files for k in f)))
    status_keys = sorted({k for f in files for k in f if any(w in k for w in ("status", "error", "pending", "etl"))})
    by_batch = collections.defaultdict(collections.Counter)
    for f in files:
        if f.get("name") in position:
            by_batch[position[f["name"]] // args.batch + 1][tuple(str(f.get(k)) for k in status_keys)] += 1
    print(f"status values {status_keys} for each upload batch of {args.batch} (batches with a value that is not None, or not all files):")
    none = tuple("None" for _ in status_keys)
    for n, counts in sorted(by_batch.items()):
        if set(counts) != {none} or sum(counts.values()) != args.batch:
            print(f"  batch {n}: {dict(counts)}")
    print(f"  all batches: {dict(sum(by_batch.values(), collections.Counter()))}")
    by_name = collections.Counter((n or "").lower() for n in names)
    by_dsid = collections.Counter(setup.dsid_of(n) for n in names)
    duplicate_names = {n: c for n, c in by_name.items() if c > 1}
    duplicate_dsids = {d: c for d, c in by_dsid.items() if d and c > 1}
    unknown = [n for n in names if n not in file_map]
    report = {
        "dataset_id": args.dataset_id,
        "dataset_name": dataset.get("name"),
        "files": len(names),
        "unique_names": len(by_name),
        "duplicate_names": len(duplicate_names),
        "duplicate_dsids": len(duplicate_dsids),
        "unknown_files": len(unknown),
        "file_map_documents": len(file_map),
        "not_uploaded_yet": len(set(file_map) - set(names)),
        "total_chunks_count": dataset.get("total_chunks_count"),
    }
    bc.audit("4minds_check_files", **report)
    print(json.dumps(report, indent=2))
    for label, items in (("duplicate names", list(duplicate_names.items())),
                         ("duplicate dsids", list(duplicate_dsids.items())), ("unknown files", unknown)):
        if items:
            print(f"{label} (first 20): {items[:20]}")
    if duplicate_names or duplicate_dsids or unknown:
        sys.exit(1)


if __name__ == "__main__":
    main()

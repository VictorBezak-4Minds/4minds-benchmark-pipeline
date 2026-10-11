#!/usr/bin/env python3
"""Load the benchmark corpus into a self-hosted RAGFlow server: one dataset, one file per document.

    ./bench enterpriserag-bench setup_ragflow eval systems/setup_ragflow.py --base-url http://<host>:9380

The server runs from the official RAGFlow Docker Compose files (pinned release, see the hub
README). The API key is in ~/.config/ragflow/api_key (made in the RAGFlow web page). The
embedding provider and its key are set in the RAGFlow web page (Model providers), not here.

The dataset uses RAGFlow's defaults: chunk method "naive" (General) and the parser config that
the server gives a new dataset. Only the embedding model is set (--embedding and
--embedding-factory give "<model>@<factory>"). setup.json records the parser config that the
server returns.

A profile with corpus_documents() gets one file per document, with the 4Minds file name
(setup_4minds.file_name(): document ID, "_", title) and the document text (title, blank line,
content). The server renames a file whose name the dataset already has, so the script uploads
only the names that are not in the dataset: a stopped upload can run again. Then it starts
parsing for every document that is UNSTART or CANCEL (FAIL only with --retry-failed), and waits
until every document is DONE. It stops if the counts do not change for --stall-min minutes.

Output: shared/ragflow/setup.json (server, dataset, parser config, counts, times, estimated
embedding cost) and shared/ragflow/documents.json (RAGFlow document ID -> document ID, title and
file name). The retriever `ragflow` (systems/retrievers.py) reads both.
"""
import argparse
import json
import sys
import time

import requests

import bench_common as bc
import llm_backends
from setup_4minds import dsid_of, file_name

OUT = bc.SHARED / "ragflow"
SETUP_FILE = OUT / "setup.json"
DOCUMENTS_FILE = OUT / "documents.json"
PAGE_SIZE = 100       # REST_API_MAX_PAGE_SIZE of the server
PARSE_BATCH = 100     # REST_API_MAX_IDS of the server
PENDING = {"UNSTART", "RUNNING", "SCHEDULE"}
RUN_NAMES = {"0": "UNSTART", "1": "RUNNING", "2": "CANCEL", "3": "DONE", "4": "FAIL", "5": "SCHEDULE"}


class Client:
    """RAGFlow HTTP API. Errors come as HTTP 200 with "code" other than 0, so both are checked."""

    def __init__(self, base_url):
        self.base = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {bc.load_key('ragflow')}"}

    def request(self, method, path, timeout=300, **kwargs):
        """(http status, payload); status 0 for a network error."""
        try:
            response = requests.request(method, f"{self.base}/api/v1{path}", headers=self.headers,
                                        timeout=timeout, **kwargs)
            payload = response.json() if response.content else {}
        except requests.RequestException as e:
            return 0, {"code": "network", "message": str(e)[:500]}
        except ValueError:
            return response.status_code, {"code": "not_json", "message": response.text[:500]}
        return response.status_code, payload

    def call(self, method, path, **kwargs):
        status, payload = self.request(method, path, **kwargs)
        if status != 200 or payload.get("code") != 0:
            sys.exit(f"{method} {path} -> HTTP {status}: {json.dumps(payload)[:800]}")
        return payload.get("data")


def run_name(doc):
    run = str(doc.get("run", ""))
    return RUN_NAMES.get(run, run)


def find_dataset(client, name):
    status, payload = client.request("GET", "/datasets", params={"name": name})
    if status == 200 and payload.get("code") == 0:
        return next((d for d in payload.get("data") or [] if d.get("name") == name), None)
    return None


def list_documents(client, dataset_id):
    docs, page = [], 1
    while True:
        data = client.call("GET", f"/datasets/{dataset_id}/documents",
                           params={"page": page, "page_size": PAGE_SIZE, "orderby": "create_time", "desc": "false"})
        docs.extend(data.get("docs") or [])
        if not data.get("docs") or len(docs) >= int(data.get("total") or 0):
            return docs
        page += 1


def counts(docs):
    out = {}
    for d in docs:
        out[run_name(d)] = out.get(run_name(d), 0) + 1
    return {"documents": len(docs), "runs": dict(sorted(out.items())),
            "chunks": sum(int(d.get("chunk_count") or 0) for d in docs),
            "tokens": sum(int(d.get("token_count") or 0) for d in docs)}


def document_files():
    """[(file name, bytes, document)] of the profile's documents."""
    docs = bc.profile.corpus_documents()
    files = [(file_name(d), d["text"].encode(), d) for d in docs]
    names = {name for name, _, _ in files}
    if len(names) != len(docs) or any(dsid_of(n) != d["dsid"] for n, _, d in files):
        sys.exit("File names are not unique, or a file name does not give back its document ID.")
    return files


def upload(client, dataset_id, files, existing, batch):
    todo = [f for f in files if f[0] not in existing]
    print(f"{len(files)} files, {len(files) - len(todo)} already in the dataset, {len(todo)} to upload")
    uploaded = 0
    batches = range(0, len(todo), batch)
    for n, i in enumerate(batches, 1):
        part = todo[i:i + batch]
        data = client.call("POST", f"/datasets/{dataset_id}/documents",
                           files=[("file", (name, blob, "text/plain")) for name, blob, _ in part])
        renamed = [d.get("name") for d in data or [] if d.get("name") not in {name for name, _, _ in part}]
        if renamed:
            sys.exit(f"The server renamed uploaded files (a name was already in the dataset): {renamed[:5]}")
        uploaded += len(data or [])
        if n % 20 == 0 or n == len(batches):
            print(f"  {bc.now()} upload batch {n}/{len(batches)}: {uploaded} files")
    if todo:
        bc.audit("ragflow_upload", dataset_id=dataset_id, files=len(todo), uploaded=uploaded)
    return uploaded


def start_parse(client, dataset_id, docs, retry_failed):
    states = {"UNSTART", "CANCEL"} | ({"FAIL"} if retry_failed else set())
    ids = [d["id"] for d in docs if run_name(d) in states]
    for i in range(0, len(ids), PARSE_BATCH):
        client.call("POST", f"/datasets/{dataset_id}/documents/parse", json={"document_ids": ids[i:i + PARSE_BATCH]})
    if ids:
        bc.audit("ragflow_parse_start", dataset_id=dataset_id, documents=len(ids), retry_failed=retry_failed)
    return len(ids)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", help="the RAGFlow API, for example http://<host>:9380 "
                                           "(default: the base_url in shared/ragflow/setup.json)")
    parser.add_argument("--embedding", default="openai-text-embedding-3-large", choices=llm_backends.names(),
                        help="the backend entry of the embedding model (model name and price)")
    parser.add_argument("--embedding-factory", default="OpenAI", help="the RAGFlow model provider of the embedding model")
    parser.add_argument("--batch", type=int, default=50, help="files per upload request")
    parser.add_argument("--poll-s", type=float, default=60)
    parser.add_argument("--stall-min", type=float, default=30)
    parser.add_argument("--retry-failed", action="store_true", help="parse FAIL documents again")
    parser.add_argument("--dry-run", action="store_true", help="make the files and count them; send nothing")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    previous = json.loads(SETUP_FILE.read_text()) if SETUP_FILE.exists() else {}
    base_url = args.base_url or previous.get("base_url")
    if not base_url:
        sys.exit("Set --base-url (the RAGFlow API, for example http://<host>:9380).")
    backend = llm_backends.Backend(args.embedding)
    embedding_model = f"{backend.model}@{args.embedding_factory}"
    files = document_files()
    chars = sum(len(blob) for _, blob, _ in files)
    print(f"{len(files)} documents, {chars} bytes; dataset {bc.profile.RESOURCE_NAME}, embedding {embedding_model}")
    if args.dry_run:
        print(f"first file: {files[0][0]}")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    bc.acquire_lock(OUT / ".setup.lock")
    client = Client(base_url)
    started = time.monotonic()
    dataset = find_dataset(client, bc.profile.RESOURCE_NAME)
    if dataset is None:
        bc.audit("ragflow_create_dataset", base_url=base_url, name=bc.profile.RESOURCE_NAME,
                 embedding_model=embedding_model, chunk_method="naive", corpus=str(bc.CORPUS_FILE),
                 sha256=bc.sha256(bc.CORPUS_FILE), files=len(files))
        dataset = client.call("POST", "/datasets", json={
            "name": bc.profile.RESOURCE_NAME, "description": bc.profile.RESOURCE_DESCRIPTION,
            "embedding_model": embedding_model, "chunk_method": "naive"})
    elif backend.model not in str(dataset.get("embedding_model")):
        sys.exit(f"Dataset {dataset['id']} uses {dataset.get('embedding_model')}, not {embedding_model}.")
    dataset_id = dataset["id"]
    print(f"dataset {dataset_id}: chunk_method {dataset.get('chunk_method')}, "
          f"parser_config {json.dumps(dataset.get('parser_config'))}")

    docs = list_documents(client, dataset_id)
    expected = {name for name, _, _ in files}
    extra = sorted(d["name"] for d in docs if d["name"] not in expected)
    if extra:
        sys.exit(f"The dataset has {len(extra)} files that are not in the corpus list: {extra[:5]}")
    upload_start = time.monotonic()
    upload(client, dataset_id, files, {d["name"] for d in docs}, args.batch)
    upload_s = round(time.monotonic() - upload_start, 1)

    parse_start = time.monotonic()
    docs = list_documents(client, dataset_id)
    print(f"parse started for {start_parse(client, dataset_id, docs, args.retry_failed)} documents")
    last, last_change = None, time.monotonic()
    while True:
        docs = list_documents(client, dataset_id)
        state = counts(docs)
        if state != last:
            print(f"  {bc.now()} {state}")
            last, last_change = state, time.monotonic()
        if not any(run_name(d) in PENDING for d in docs):
            break
        if time.monotonic() - last_change > args.stall_min * 60:
            bc.audit("ragflow_parse_stalled", dataset_id=dataset_id, minutes=args.stall_min, **state)
            sys.exit(f"No progress for {args.stall_min} min: {state}")
        time.sleep(args.poll_s)
    parse_s = round(time.monotonic() - parse_start, 1)

    failed = [{"name": d["name"], "run": run_name(d), "progress_msg": (d.get("progress_msg") or "")[-300:]}
              for d in docs if run_name(d) != "DONE"]
    name_dsid = {name: d["dsid"] for name, _, d in files}
    titles = {d["dsid"]: d["title"] for _, _, d in files}
    documents = {d["id"]: {"dsid": name_dsid[d["name"]], "title": titles[name_dsid[d["name"]]], "name": d["name"]}
                 for d in docs}
    DOCUMENTS_FILE.write_text(json.dumps(documents, indent=1))
    state = counts(docs)
    dataset = find_dataset(client, bc.profile.RESOURCE_NAME) or dataset
    status, version = client.request("GET", "/system/version")
    setup = {"checked": bc.now(), "base_url": base_url, "complete": not failed and len(docs) == len(files),
             "server_version": version.get("data") if status == 200 else None,
             "dataset": {k: dataset.get(k) for k in ("id", "name", "embedding_model", "chunk_method", "parser_config",
                                                     "similarity_threshold", "vector_similarity_weight")},
             "embedding": backend.settings(), "embedding_model": embedding_model, **state,
             "failed": failed[:50], "failed_count": len(failed),
             "upload_wall_clock_s": upload_s, "parse_wall_clock_s": parse_s,
             "ingest_wall_clock_s": round(time.monotonic() - started, 1),
             "estimated_cost_usd": round(state["tokens"] * backend.prices.get("input", 0) / 1e6, 4),
             "cost_note": "token_count of RAGFlow (sum over documents) x the embedding price; parse only",
             "corpus": str(bc.CORPUS_FILE), "corpus_sha256": bc.sha256(bc.CORPUS_FILE),
             "documents_file": DOCUMENTS_FILE.name}
    if previous.get("ingest_wall_clock_s") and previous.get("dataset", {}).get("id") == dataset_id:
        setup["previous_runs"] = previous.get("previous_runs", []) + [
            {k: previous.get(k) for k in ("checked", "ingest_wall_clock_s", "upload_wall_clock_s", "parse_wall_clock_s")}]
    SETUP_FILE.write_text(json.dumps(setup, indent=2))
    bc.audit("ragflow_ready" if setup["complete"] else "ragflow_incomplete", dataset_id=dataset_id,
             **{k: setup[k] for k in ("documents", "runs", "chunks", "tokens", "failed_count", "ingest_wall_clock_s",
                                      "estimated_cost_usd")})
    print(json.dumps({k: v for k, v in setup.items() if k != "failed"}, indent=2))
    if failed:
        sys.exit(f"{len(failed)} documents are not DONE (see setup.json 'failed'). "
                 "Fix the cause, then run again with --retry-failed.")


if __name__ == "__main__":
    main()

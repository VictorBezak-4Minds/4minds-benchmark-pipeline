#!/usr/bin/env python3
"""Create the Gemini File Search store for the active benchmark and upload its corpus file (once).

    ./bench qasper setup_gemini eval systems/setup_gemini.py

The store display name is the profile's RESOURCE_NAME. The document gets the metadata
`source` = profile.SOURCE, which run_gemini.py uses as its metadata filter. Safe to run
again: it reuses the store and does not upload a source that is already in the store.
It waits until the store has no pending or failed documents and writes
shared/gemini/setup.json. Put the store name in the profile (GEMINI_FILE_SEARCH_STORE).
"""
import argparse
import json
import sys
import time

import requests

import bench_common as bc

API = "https://generativelanguage.googleapis.com/v1beta"
UPLOAD_API = "https://generativelanguage.googleapis.com/upload/v1beta"
DISPLAY_NAME = bc.profile.RESOURCE_NAME
SOURCE = bc.profile.SOURCE
SETUP_FILE = bc.SHARED / "gemini" / "setup.json"


class Client:
    def __init__(self):
        self.http = requests.Session()
        self.http.headers["x-goog-api-key"] = bc.load_key("gemini")

    def call(self, method, url, **kwargs):
        response = self.http.request(method, url, timeout=300, **kwargs)
        if response.status_code >= 400:
            sys.exit(f"{method} {url} -> HTTP {response.status_code}: {response.text[:800]}")
        return response

    def list_all(self, url, field):
        items, token = [], None
        while True:
            page = self.call("GET", url, params={"pageSize": 20, **({"pageToken": token} if token else {})}).json()
            items += page.get(field, [])
            token = page.get("nextPageToken")
            if not token:
                return items


def documents(client, store):
    return client.list_all(f"{API}/{store}/documents", "documents")


def source_of(document):
    return next((m.get("stringValue") for m in document.get("customMetadata", []) if m.get("key") == "source"), None)


def upload(client, store):
    data = bc.CORPUS_FILE.read_bytes()
    start = client.call("POST", f"{UPLOAD_API}/{store}:uploadToFileSearchStore", headers={
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(len(data)),
        "X-Goog-Upload-Header-Content-Type": "text/plain",
    }, json={"displayName": bc.CORPUS_FILE.name, "mimeType": "text/plain",
             "customMetadata": [{"key": "source", "stringValue": SOURCE}]})
    upload_url = start.headers.get("x-goog-upload-url")
    if not upload_url:
        sys.exit(f"No upload URL in the start response: HTTP {start.status_code} {start.text[:400]}")
    operation = client.call("POST", upload_url, data=data, headers={
        "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"}).json()
    print(f"uploaded: {json.dumps(operation)[:400]}")
    return operation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-min", type=float, default=60)
    args = parser.parse_args()
    client = Client()
    started = time.monotonic()

    store = next((s for s in client.list_all(f"{API}/fileSearchStores", "fileSearchStores")
                  if s.get("displayName") == DISPLAY_NAME), None)
    if store is None:
        bc.audit("gemini_create_store", display_name=DISPLAY_NAME)
        store = client.call("POST", f"{API}/fileSearchStores", json={"displayName": DISPLAY_NAME}).json()
    name = store["name"]
    print(f"store: {name}")

    operation = None
    if not any(source_of(d) == SOURCE for d in documents(client, name)):
        bc.audit("gemini_upload", store=name, file=str(bc.CORPUS_FILE), sha256=bc.sha256(bc.CORPUS_FILE), source=SOURCE)
        operation = upload(client, name)

    while True:
        if operation and not operation.get("done"):
            operation = client.call("GET", f"{API}/{operation['name']}").json()
        store = client.call("GET", f"{API}/{name}").json()
        docs = documents(client, name)
        states = {d.get("displayName"): d.get("state") for d in docs if source_of(d) == SOURCE}
        if int(store.get("failedDocumentsCount") or 0) or (operation or {}).get("error"):
            sys.exit(f"Import failed: {json.dumps(store)} {json.dumps(operation)[:600]}")
        if states and all(s == "STATE_ACTIVE" for s in states.values()) and not int(store.get("pendingDocumentsCount") or 0):
            break
        if time.monotonic() - started > args.timeout_min * 60:
            sys.exit(f"Store not ready after {args.timeout_min} min: {states}")
        print(f"  {bc.now()} waiting: {states or 'no document yet'}")
        time.sleep(15)

    setup = {"created_or_checked": bc.now(), "store": store, "documents": docs, "source": SOURCE,
             "corpus_file": str(bc.CORPUS_FILE), "corpus_sha256": bc.sha256(bc.CORPUS_FILE),
             "setup_wall_clock_s": round(time.monotonic() - started, 1)}
    SETUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETUP_FILE.write_text(json.dumps(setup, indent=2))
    bc.audit("gemini_store_ready", store=name, documents=states, wall_clock_s=setup["setup_wall_clock_s"])
    print(json.dumps({"store": name, "documents": states, "wall_clock_s": setup["setup_wall_clock_s"]}, indent=2))


if __name__ == "__main__":
    main()

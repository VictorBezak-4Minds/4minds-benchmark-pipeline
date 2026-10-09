#!/usr/bin/env python3
"""Create the Vertex AI RAG Engine corpus for the active benchmark and upload its corpus file (once).

    ./bench graphrag-bench setup_rag_engine eval systems/setup_rag_engine.py

Safe to run again: it reuses the corpus with the same display name and does not upload a
file that is already in the corpus. It waits until every file of the corpus is ACTIVE and
writes results/rag_engine/setup.json. RAG Engine defaults are used for chunking, the
embedding model and the vector database (Spanner mode, RagManagedDb, Basic tier in
europe-west4); the script records what the API reports.
"""
import argparse
import json
import sys
import time

import google.auth
import google.auth.transport.requests
import requests

import bench_common as bc

PROJECT = "minds-vs-gemini-benchmark"
# us-central1/us-east1/us-east4 are allowlist-only for new projects (Spanner mode refused), and
# Serverless mode in us-central1 failed with "No available indexing project". europe-west4 is GA.
LOCATION = "europe-west4"
DISPLAY_NAME = bc.profile.RESOURCE_NAME
API = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/{LOCATION}"
UPLOAD_API = f"https://{LOCATION}-aiplatform.googleapis.com/upload/v1"
SETUP_FILE = bc.RESULTS / "rag_engine" / "setup.json"


class Session:
    def __init__(self):
        self.creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self.http = requests.Session()

    def headers(self):
        if not self.creds.valid:
            self.creds.refresh(google.auth.transport.requests.Request())
        return {"Authorization": f"Bearer {self.creds.token}", "x-goog-user-project": PROJECT}

    def call(self, method, url, **kwargs):
        response = self.http.request(method, url, headers=self.headers(), timeout=300, **kwargs)
        if response.status_code >= 400:
            sys.exit(f"{method} {url} -> HTTP {response.status_code}: {response.text[:800]}")
        return response.json() if response.content else {}

    def wait(self, operation):
        name = operation["name"]
        while not operation.get("done"):
            time.sleep(5)
            operation = self.call("GET", f"https://{LOCATION}-aiplatform.googleapis.com/v1/{name}")
        if "error" in operation:
            sys.exit(f"Operation {name} failed: {operation['error']}")
        return operation.get("response", {})


def list_all(session, url, field):
    items, token = [], None
    while True:
        page = session.call("GET", url, params={"pageSize": 100, **({"pageToken": token} if token else {})})
        items += page.get(field, [])
        token = page.get("nextPageToken")
        if not token:
            return items


def find_corpus(session):
    for corpus in list_all(session, f"{API}/ragCorpora", "ragCorpora"):
        if corpus.get("displayName") == DISPLAY_NAME:
            return corpus
    return None


def corpus_files(session, corpus_name):
    return list_all(session, f"https://{LOCATION}-aiplatform.googleapis.com/v1/{corpus_name}/ragFiles", "ragFiles")


def readiness(session, corpus_name):
    """Return the ready state of the corpus, or None if a file is not ACTIVE yet."""
    files = corpus_files(session, corpus_name)
    states = {f.get("displayName"): (f.get("fileStatus") or {}).get("state") for f in files}
    failed = {k: v for k, v in states.items() if v not in ("ACTIVE", None, "STATE_UNSPECIFIED")}
    if any(v == "ERROR" for v in states.values()):
        sys.exit(f"RAG file import failed: {json.dumps(files)[:800]}")
    if CORPUS_NAME_FILE not in states or failed or any(v != "ACTIVE" for v in states.values()):
        return None
    return {"corpus": corpus_name, "files": states}


CORPUS_NAME_FILE = bc.CORPUS_FILE.name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-min", type=float, default=120)
    args = parser.parse_args()
    session = Session()
    started = time.monotonic()

    corpus = find_corpus(session)
    if corpus is None:
        body = {"displayName": DISPLAY_NAME}
        bc.audit("rag_engine_create_corpus", display_name=DISPLAY_NAME, location=LOCATION, body=body,
                 rag_engine_config=session.call("GET", f"{API}/ragEngineConfig"))
        operation = session.call("POST", f"{API}/ragCorpora", json=body)
        session.wait(operation)
        corpus = find_corpus(session)
    print(f"corpus: {corpus['name']}")

    if not any(f.get("displayName") == CORPUS_NAME_FILE for f in corpus_files(session, corpus["name"])):
        bc.audit("rag_engine_upload", corpus=corpus["name"], file=str(bc.CORPUS_FILE), sha256=bc.sha256(bc.CORPUS_FILE))
        metadata = {"rag_file": {"display_name": CORPUS_NAME_FILE, "description": bc.profile.RESOURCE_DESCRIPTION}}
        with open(bc.CORPUS_FILE, "rb") as f:
            response = session.http.post(
                f"{UPLOAD_API}/{corpus['name']}/ragFiles:upload", headers=session.headers(), timeout=600,
                files={"metadata": (None, json.dumps(metadata), "application/json"),
                       "file": (CORPUS_NAME_FILE, f, "text/plain")})
        if response.status_code >= 400:
            sys.exit(f"Upload failed: HTTP {response.status_code}: {response.text[:800]}")
        print(f"uploaded: {json.dumps(response.json())[:400]}")

    while (ready := readiness(session, corpus["name"])) is None:
        if time.monotonic() - started > args.timeout_min * 60:
            sys.exit(f"Corpus not ready after {args.timeout_min} min.")
        print("  waiting for RAG files to become ACTIVE ...")
        time.sleep(30)

    corpus = session.call("GET", f"https://{LOCATION}-aiplatform.googleapis.com/v1/{corpus['name']}")
    files = corpus_files(session, corpus["name"])
    setup = {"created_or_checked": bc.now(), "project": PROJECT, "location": LOCATION, "corpus": corpus,
             "files": files, "ready": ready, "setup_wall_clock_s": round(time.monotonic() - started, 1)}
    SETUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETUP_FILE.write_text(json.dumps(setup, indent=2))
    bc.audit("rag_engine_ready", corpus=corpus["name"], files=ready["files"])
    print(json.dumps({"corpus": corpus["name"], "ready": ready["files"],
                      "embedding": (corpus.get("vectorDbConfig") or {}).get("ragEmbeddingModelConfig"),
                      "vector_db": list(((corpus.get("vectorDbConfig") or {}).get("ragManagedDb") or {}).keys()) or
                                   corpus.get("vectorDbConfig")}, indent=2))


if __name__ == "__main__":
    main()

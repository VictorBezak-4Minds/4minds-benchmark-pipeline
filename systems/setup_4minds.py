#!/usr/bin/env python3
"""Load the benchmark corpus into 4Minds (prod): one dataset, one persona, one model.

Names, corpus file and system prompt come from the active benchmark profile.
Safe to run again: it reuses the dataset, persona and model with the benchmark names.
The persona carries the benchmark system prompt (4Minds has no per-request system
prompt). The script then waits until the dataset graph build is complete
(graph_status "ready", not only "rag_ready"), logs every status change, and writes
shared/4minds/setup.json. It stops if the build shows no progress for --stall-min minutes.

A profile with corpus_documents() gets one file per document, named file_name(): the
document ID, an underscore and the title, cleaned with the server's sanitize_filename() rule
(so "__" becomes "_"), with the document text (title, blank line, content). The first
--batch files create the dataset; the others go to POST /api/v1/user/dataset/upload in
batches. The server skips a file name that the dataset already has, so a stopped upload can
run again. shared/4minds/file_map.json maps each file name to its document ID; runners read
the ID back from the chunk's document_title (dsid_of()). Each upload batch is its own ETL
batch, so the build counts as complete only when its state (total_chunks_count) has not changed
for --stable-min minutes; setup.json records that chunk count, and runners check it.

    ./bench graphrag-bench setup_4minds eval systems/setup_4minds.py

A second dataset of the same benchmark (for example the full corpus) needs its own
--corpus-file, --name and --shared-name, so that it does not reuse the first dataset or
overwrite its shared/4minds/ files.
"""
import argparse
import json
import re
import sys
import time

import requests

import bench_common as bc

BASE = "https://api.4minds.ai"
DATASET_NAME = bc.profile.RESOURCE_NAME
MODEL_NAME = bc.profile.RESOURCE_NAME
RESOURCE_DESCRIPTION = bc.profile.RESOURCE_DESCRIPTION
CORPUS_FILE = bc.CORPUS_FILE
PERSONA_NAME = f"{bc.profile.TITLE} official prompt"
SETUP_FILE = bc.SHARED / "4minds" / "setup.json"
FILE_MAP = bc.SHARED / "4minds" / "file_map.json"
DSID = re.compile(r"dsid_[0-9a-f]{32}")
RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_WAIT_S = (30, 60, 120, 300, 600)


def file_name(doc):
    """<dsid>_<title>.txt after the server's sanitize_filename() (4minds-platform app/user/file_utils.py)."""
    name = re.sub(r"_+", "_", re.sub(r"[^\w\-.]", "_", f"{doc['dsid']}__{doc['title']}")).strip("._") or "file"
    return name[:120] + ".txt"


def dsid_of(title):
    match = DSID.search(title or "")
    return match.group(0) if match else None


class Client:
    def __init__(self):
        self.http = requests.Session()
        self.http.headers["X-API-Key"] = bc.load_key("4minds")

    def call(self, method, path, **kwargs):
        """Retries rate limits, server errors and lost connections; uploads are safe to retry
        because the server skips a file name that the dataset already has."""
        for wait_s in (*RETRY_WAIT_S, None):
            try:
                response = self.http.request(method, BASE + path, timeout=300, **kwargs)
                problem = f"HTTP {response.status_code}: {response.text[:800]}"
                if response.status_code not in RETRY_STATUS:
                    break
            except requests.RequestException as e:
                response, problem = None, f"{type(e).__name__}: {str(e)[:300]}"
            if wait_s is None:
                break
            print(f"  {bc.now()} {method} {path} -> {problem}; retry in {wait_s} s")
            bc.audit("4minds_retry", method=method, path=path, problem=problem[:300], wait_s=wait_s)
            time.sleep(wait_s)
        if response is None or response.status_code >= 400:
            sys.exit(f"{method} {path} -> {problem}")
        return response.json() if response.content else {}


def items(payload, *keys):
    if isinstance(payload, list):
        return payload
    for key in keys:
        if isinstance(payload.get(key), list):
            return payload[key]
    return []


def find_dataset(client):
    return next((d for d in items(client.call("GET", "/api/v1/user/dataset"), "items", "datasets", "data")
                 if d.get("name") == DATASET_NAME), None)


def find_persona(client):
    return next((p for p in items(client.call("GET", "/api/v1/user/personas"), "personas")
                 if p.get("name") == PERSONA_NAME), None)


def find_model(client, dataset_id):
    return next((m for m in items(client.call("GET", "/api/v1/user/model"), "items", "models", "data")
                 if m.get("name") == MODEL_NAME and m.get("dataset_id") == dataset_id), None)


def dataset_state(dataset):
    meta = dataset.get("graph_build_metadata") or {}
    return {
        "status": dataset.get("status"),
        "graph_status": dataset.get("graph_status"),
        "graph_build_progress": dataset.get("graph_build_progress"),
        "files_processed_count": dataset.get("files_processed_count"),
        "total_chunks_count": dataset.get("total_chunks_count"),
        "build_status": meta.get("status"),
        "etl_job_status": (dataset.get("latest_job") or {}).get("status"),
        "error_message": dataset.get("error_message"),
    }


def readiness(client, dataset_id, model_id, stable_chunks=None):
    """Return the ready state, or None while the build is still running.

    The backend sets graph_status "ready" only after every item of the ETL batch succeeds.
    graph_build_metadata.status can stay "enhancing": the batch counts the dataset manifest
    as an extra file, so it is not used here. With a document list, each upload batch is its
    own ETL batch, and graph_status is "ready" between batches; files_processed_count counts
    only the first batch. So setup waits until total_chunks_count is stable (--stable-min) and
    writes it to setup.json; with stable_chunks, the count must still be the same.
    """
    dataset = client.call("GET", f"/api/v1/user/dataset/{dataset_id}")
    state = dataset_state(dataset)
    if state["status"] == "failed" or state["error_message"] or state["etl_job_status"] == "failed":
        sys.exit(f"4Minds dataset {dataset_id} failed: {state}")
    if (state["graph_status"] != "ready" or state["etl_job_status"] not in (None, "completed")
            or not state["total_chunks_count"]
            or (stable_chunks is not None and state["total_chunks_count"] != stable_chunks)):
        return None, state
    model = client.call("GET", f"/api/v1/user/model/{model_id}")
    state["model_status"] = model.get("status")
    if model.get("status") != "ready":
        return None, state
    return {"dataset_id": dataset_id, "model_id": model_id, **state}, state


def document_files():
    """[(file name, bytes)] of the profile's documents; writes FILE_MAP."""
    docs = bc.profile.corpus_documents(CORPUS_FILE)
    files = [(file_name(d), d["text"].encode()) for d in docs]
    mapping = {name: d["dsid"] for (name, _), d in zip(files, docs)}
    if len(mapping) != len(docs) or any(dsid_of(n) != d for n, d in mapping.items()):
        sys.exit("File names are not unique, or a file name does not give back its document ID.")
    FILE_MAP.parent.mkdir(parents=True, exist_ok=True)
    FILE_MAP.write_text(json.dumps(mapping, indent=1))
    return files


def create_dataset(client, files):
    bc.audit("4minds_create_dataset", name=DATASET_NAME, file=str(CORPUS_FILE), sha256=bc.sha256(CORPUS_FILE),
             files=len(files))
    return client.call("POST", "/api/v1/user/dataset", files=[("files", (n, b, "text/plain")) for n, b in files],
                       data={"dataset_name": DATASET_NAME, "tags": f"{bc.BENCHMARK},benchmark",
                             "description": RESOURCE_DESCRIPTION, "urls": "[]"})


def upload_rest(client, dataset_id, files, batch, pause_s):
    totals = {"uploaded": 0, "skipped": 0, "failed": 0}
    batches = range(0, len(files), batch)
    for n, i in enumerate(batches, 1):
        part = files[i:i + batch]
        reply = client.call("POST", "/api/v1/user/dataset/upload", data={"dataset_id": str(dataset_id)},
                            files=[("files", (name, data, "text/plain")) for name, data in part])
        totals["uploaded"] += reply.get("files_uploaded") or 0
        totals["skipped"] += reply.get("files_skipped") or 0
        totals["failed"] += reply.get("files_failed") or 0
        if reply.get("failed_files") or reply.get("processing_error"):
            print(f"  batch {n}: failed {reply.get('failed_files')} processing_error {reply.get('processing_error')}")
        if n % 5 == 0 or n == len(batches):
            print(f"  {bc.now()} upload batch {n}/{len(batches)}: {totals}")
        if reply.get("files_uploaded"):
            time.sleep(pause_s)
    bc.audit("4minds_upload", dataset_id=dataset_id, files=len(files), **totals)
    if totals["failed"]:
        sys.exit(f"{totals['failed']} files failed to upload. Run the same command again.")
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poll-s", type=float, default=60)
    parser.add_argument("--stall-min", type=float, default=120)
    parser.add_argument("--batch", type=int, default=200, help="files per upload request (document lists)")
    parser.add_argument("--pause-s", type=float, default=2, help="wait between upload requests (document lists)")
    parser.add_argument("--stable-min", type=float, default=15,
                        help="document lists: minutes with no change of the build state before it counts as complete")
    parser.add_argument("--corpus-file", help="corpus file instead of the profile's CORPUS_FILE")
    parser.add_argument("--name", help="dataset and model name instead of the profile's RESOURCE_NAME")
    parser.add_argument("--description", help="dataset description instead of the profile's RESOURCE_DESCRIPTION")
    parser.add_argument("--shared-name", default="4minds", help="folder in shared/ for setup.json and file_map.json")
    args = parser.parse_args()
    global DATASET_NAME, MODEL_NAME, RESOURCE_DESCRIPTION, CORPUS_FILE, SETUP_FILE, FILE_MAP
    if args.corpus_file:
        CORPUS_FILE = bc.BENCH_DIR / args.corpus_file
    if args.name:
        DATASET_NAME = MODEL_NAME = args.name
    if args.description:
        RESOURCE_DESCRIPTION = args.description
    SETUP_FILE, FILE_MAP = (bc.SHARED / args.shared_name / name for name in ("setup.json", "file_map.json"))
    if args.shared_name != "4minds" and DATASET_NAME == bc.profile.RESOURCE_NAME:
        sys.exit(f"--shared-name {args.shared_name} needs its own --name (not {DATASET_NAME}).")
    client = Client()
    started = time.monotonic()

    files = document_files() if hasattr(bc.profile, "corpus_documents") else None
    dataset = find_dataset(client)
    if dataset is None and files is not None:
        dataset = create_dataset(client, files[:args.batch])
    elif dataset is None:
        with open(CORPUS_FILE, "rb") as f:
            dataset = create_dataset(client, [(CORPUS_FILE.name, f.read())])
    dataset_id = int(dataset["id"])
    print(f"dataset: {dataset_id} {dataset_state(dataset)}")
    if files is not None:
        print(f"uploading {len(files)} files in batches of {args.batch} (the server skips files it has)")
        upload_rest(client, dataset_id, files, args.batch, args.pause_s)

    persona = find_persona(client)
    if persona is None:
        bc.audit("4minds_create_persona", name=PERSONA_NAME)
        persona = client.call("POST", "/api/v1/user/personas", json={
            "name": PERSONA_NAME,
            "description": f"The official {bc.profile.TITLE} system prompt, benchmark only.",
            "toneOfVoice": "professional",
            "keyTraits": [],
            "behavioralGuidelines": bc.SYSTEM_PROMPT,
            "status": "active",
        })
    persona_id = int(persona["id"])
    print(f"persona: {persona_id}")

    model = find_model(client, dataset_id)
    if model is None:
        bc.audit("4minds_create_model", name=MODEL_NAME, dataset_id=dataset_id, persona_id=persona_id)
        model = client.call("POST", "/api/v1/user/model", json={
            "model_name": MODEL_NAME, "dataset_id": dataset_id, "persona_id": persona_id,
            "description": f"{RESOURCE_DESCRIPTION}; standard weights + RAG"})
    model_id = int(model["id"])
    if model.get("personaId") not in (None, persona_id) or model.get("persona_id") not in (None, persona_id):
        print(f"  warning: model persona is {model.get('personaId') or model.get('persona_id')}, expected {persona_id}")
    print(f"model: {model_id} status={model.get('status')} base={model.get('base_model_name')}")

    last, last_change = None, time.monotonic()
    while True:
        ready, state = readiness(client, dataset_id, model_id)
        if state != last:
            print(f"  {bc.now()} {state}")
            bc.audit("4minds_build_status", dataset_id=dataset_id, **state)
            last, last_change = state, time.monotonic()
        if ready and files is None:
            break
        if ready and time.monotonic() - last_change > args.stable_min * 60:
            ready["stable_total_chunks"] = state["total_chunks_count"]
            ready["stable_for_min"] = args.stable_min
            break
        if time.monotonic() - last_change > args.stall_min * 60:
            bc.audit("4minds_build_stalled", dataset_id=dataset_id, minutes=args.stall_min, **state)
            sys.exit(f"No progress for {args.stall_min} min: {state}")
        time.sleep(args.poll_s)

    model = client.call("GET", f"/api/v1/user/model/{model_id}")
    persona = find_persona(client)
    setup = {"checked": bc.now(), "base_url": BASE, "dataset_id": dataset_id, "model_id": model_id,
             "persona_id": persona_id, "ready": ready, "wait_wall_clock_s": round(time.monotonic() - started, 1),
             "model": {k: model.get(k) for k in ("id", "name", "base_model_name", "base_model_id", "training_type_id",
                                                "status", "graph_status", "dataset_id", "personaId", "trained_at")},
             "persona": persona}
    SETUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETUP_FILE.write_text(json.dumps(setup, indent=2))
    bc.audit("4minds_ready", dataset_id=dataset_id, model_id=model_id, persona_id=persona_id)
    print(json.dumps(setup["model"], indent=2))


if __name__ == "__main__":
    main()

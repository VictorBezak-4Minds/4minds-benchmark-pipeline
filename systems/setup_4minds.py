#!/usr/bin/env python3
"""Load the benchmark corpus into 4Minds (prod): one dataset, one persona, one model.

Names, corpus file and system prompt come from the active benchmark profile.
Safe to run again: it reuses the dataset, persona and model with the benchmark names.
The persona carries the benchmark system prompt (4Minds has no per-request system
prompt). The script then waits until the dataset graph build is complete
(graph_status "ready", not only "rag_ready"), logs every status change, and writes
shared/4minds/setup.json. It stops if the build shows no progress for --stall-min minutes.

    ./bench graphrag-bench setup_4minds eval systems/setup_4minds.py
"""
import argparse
import json
import sys
import time

import requests

import bench_common as bc

BASE = "https://api.4minds.ai"
DATASET_NAME = bc.profile.RESOURCE_NAME
MODEL_NAME = bc.profile.RESOURCE_NAME
PERSONA_NAME = f"{bc.profile.TITLE} official prompt"
SETUP_FILE = bc.SHARED / "4minds" / "setup.json"


class Client:
    def __init__(self):
        self.http = requests.Session()
        self.http.headers["X-API-Key"] = bc.load_key("4minds")

    def call(self, method, path, **kwargs):
        response = self.http.request(method, BASE + path, timeout=300, **kwargs)
        if response.status_code >= 400:
            sys.exit(f"{method} {path} -> HTTP {response.status_code}: {response.text[:800]}")
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


def readiness(client, dataset_id, model_id):
    """Return the ready state, or None while the build is still running.

    The backend sets graph_status "ready" only after every item of the ETL batch succeeds.
    graph_build_metadata.status can stay "enhancing": the batch counts the dataset manifest
    as an extra file, so it is not used here.
    """
    dataset = client.call("GET", f"/api/v1/user/dataset/{dataset_id}")
    state = dataset_state(dataset)
    if state["status"] == "failed" or state["error_message"] or state["etl_job_status"] == "failed":
        sys.exit(f"4Minds dataset {dataset_id} failed: {state}")
    if (state["graph_status"] != "ready" or state["etl_job_status"] not in (None, "completed")
            or not state["total_chunks_count"]):
        return None, state
    model = client.call("GET", f"/api/v1/user/model/{model_id}")
    state["model_status"] = model.get("status")
    if model.get("status") != "ready":
        return None, state
    return {"dataset_id": dataset_id, "model_id": model_id, **state}, state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poll-s", type=float, default=60)
    parser.add_argument("--stall-min", type=float, default=120)
    args = parser.parse_args()
    client = Client()
    started = time.monotonic()

    dataset = find_dataset(client)
    if dataset is None:
        bc.audit("4minds_create_dataset", name=DATASET_NAME, file=str(bc.CORPUS_FILE), sha256=bc.sha256(bc.CORPUS_FILE))
        with open(bc.CORPUS_FILE, "rb") as f:
            dataset = client.call("POST", "/api/v1/user/dataset", files=[("files", (bc.CORPUS_FILE.name, f, "text/plain"))],
                                  data={"dataset_name": DATASET_NAME, "tags": f"{bc.BENCHMARK},benchmark",
                                        "description": bc.profile.RESOURCE_DESCRIPTION,
                                        "urls": "[]"})
    dataset_id = int(dataset["id"])
    print(f"dataset: {dataset_id} {dataset_state(dataset)}")

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
            "description": f"{bc.profile.RESOURCE_DESCRIPTION}; standard weights + RAG"})
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
        if ready:
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

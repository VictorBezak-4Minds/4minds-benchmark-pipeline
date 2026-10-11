#!/usr/bin/env python3
"""Single-request checks before a run. Each check sends one request and prints the result.

  ./bench graphrag-bench preflight_llm eval systems/preflight.py llm --llm bedrock-gpt-oss-120b
  ./bench graphrag-bench preflight_gemini_key eval systems/preflight.py gemini-key-project
  ./bench graphrag-bench preflight_file_search eval systems/preflight.py file-search
  ./bench graphrag-bench preflight_judge eval systems/preflight.py judge --llm anthropic-claude-haiku-5-5

llm                 one chat call: model, finish reason, usage, latency and the answer
gemini-key-project  the Google Cloud project of the Gemini API key, from the error of an API that
                    the project has not enabled (the key is sent in a header, never printed)
judge               the judge with the official GraphRAG-Bench settings, then without the backend's
                    judge_drop_params (the request that the scorers send): snapshot, rate limits
file-search         one generateContent call with the File Search tool on the first question of
                    the subset: the number and size of the grounding chunks against top_k
4minds-dataset      one GET of the benchmark's 4Minds dataset: the build state, the scalar fields and
                    the file list (count, status of each file)
"""
import argparse
import json
import sys
import time

import requests

import bench_common as bc
import judge_hooks
import llm_backends
import retrievers

# Endpoints that a Gemini-only project normally cannot use; the first one that answers with an
# error that names the consumer project is used. AQ.-format keys are valid only for the Gemini API.
PROBE_URLS = ["https://generativelanguage.googleapis.com/v1beta/tunedModels",
              "https://generativelanguage.googleapis.com/v1beta/corpora",
              "https://texttospeech.googleapis.com/v1/voices",
              "https://translation.googleapis.com/language/translate/v2/languages"]


def check_llm(args):
    backend = llm_backends.Backend(args.llm)
    messages = [{"role": "system", "content": bc.SYSTEM_PROMPT},
                {"role": "user", "content": "What is the capital of France?"}]
    start = time.monotonic()
    result, error, retryable = backend.chat(messages, args.timeout)
    latency = round(time.monotonic() - start, 2)
    out = {"backend": backend.name, "base_url": backend.base_url, "model": backend.model, "params": backend.params,
           "latency_s": latency}
    if error:
        out.update(error=error, retryable=retryable)
    else:
        message = (result["raw"].get("choices") or [{}])[0].get("message") or {}
        out.update(answer=result["answer"], finish_reason=result["finish_reason"], usage=result["usage"],
                   served_model=result["raw"].get("model"), message_keys=sorted(message),
                   content_has_reasoning_tags="<reasoning>" in (message.get("content") or ""))
    print(json.dumps(out, indent=2))
    bc.audit("preflight_llm", **{k: v for k, v in out.items() if k != "answer"})
    return 1 if error else 0


def check_judge(args):
    backend = llm_backends.Backend(args.llm)
    out = {"backend": backend.name, "model": backend.model, "dropped_params": backend.judge_drop_params}
    for label, drop in (("official_settings", False), ("scorer_settings", True)):
        if label == "official_settings" and not backend.judge_drop_params:
            continue
        try:
            out[label] = judge_hooks.preflight(backend, drop=drop)
        except SystemExit as e:
            out[label] = {"error": str(e)[:600]}
    print(json.dumps(out, indent=2))
    bc.audit("preflight_judge", **out)
    return 1 if "error" in out["scorer_settings"] else 0


def check_gemini_key_project(args):
    key = bc.load_key("gemini")
    print(f"key length {len(key)}, starts with {key[:6]}")
    for url in PROBE_URLS:
        response = requests.get(url, headers={"x-goog-api-key": key}, timeout=30)
        try:
            error = response.json().get("error") or {}
        except ValueError:
            error = {}
        for detail in error.get("details") or []:
            consumer = (detail.get("metadata") or {}).get("consumer")
            if consumer:
                out = {"probe": url, "http_status": response.status_code, "reason": detail.get("reason"),
                       "consumer": consumer}
                print(json.dumps(out, indent=2))
                bc.audit("preflight_gemini_key_project", **out)
                return 0
        reasons = [d.get("reason") for d in error.get("details") or [] if d.get("reason")]
        print(f"{url}: HTTP {response.status_code}, no consumer project in the answer "
              f"({error.get('status')} {reasons} {str(error.get('message'))[:160]})")
    print("No probe named the project. Check the key in AI Studio (API keys page).")
    return 1


def check_file_search(args):
    retriever = retrievers.make("gemini_file_search", args)
    rows = []
    for question in bc.load_questions(args):
        start = time.monotonic()
        result, error, _ = retriever.retrieve(question, args.timeout)
        row = {"id": question["id"], "type": question["question_type"], "latency_s": round(time.monotonic() - start, 2)}
        if error:
            row["error"] = error
        else:
            row.update(chunks=len(result["contexts"]), chunk_chars=[len(c) for c in result["contexts"]],
                       grounding_chunks_raw=result["extra"]["grounding_chunks_raw"], usage=result["usage"],
                       cost_usd=round(retriever.cost(result["usage"]), 5))
        rows.append(row)
        print(json.dumps(row))
    counts = [r.get("chunks", 0) for r in rows]
    out = {"store": args.store, "top_k": args.top_k, "retrieval_instruction": args.retrieval_instruction,
           "questions": len(rows), "errors": sum("error" in r for r in rows), "chunks_per_question": counts,
           "mean_chunks": round(sum(counts) / len(counts), 2), "questions_with_top_k": counts.count(args.top_k),
           "total_cost_usd": round(sum(r.get("cost_usd", 0) for r in rows), 4)}
    print(json.dumps(out, indent=2))
    bc.audit("preflight_file_search", **out, rows=rows)
    return 1 if out["errors"] or out["questions_with_top_k"] != len(rows) else 0


def check_4minds_dataset(args):
    import setup_4minds
    client = setup_4minds.Client()
    dataset_id = args.dataset_id or int(setup_4minds.find_dataset(client)["id"])
    dataset = client.call("GET", f"/api/v1/user/dataset/{dataset_id}")
    files = dataset.get("files") if isinstance(dataset.get("files"), list) else []
    status_counts = {}
    for f in files:
        status = str(f.get("status") or f.get("processing_status") or f.get("etl_status")) if isinstance(f, dict) else "?"
        status_counts[status] = status_counts.get(status, 0) + 1
    out = {"dataset_id": dataset_id, "state": setup_4minds.dataset_state(dataset),
           "scalar_fields": {k: v for k, v in dataset.items() if isinstance(v, (str, int, float, bool)) or v is None},
           "files": len(files), "file_keys": sorted(files[0]) if files and isinstance(files[0], dict) else None,
           "file_status_counts": status_counts, "first_file": files[0] if files else None}
    print(json.dumps(out, indent=2, default=str))
    bc.audit("preflight_4minds_dataset", dataset_id=dataset_id, files=len(files), file_status_counts=status_counts,
             state=out["state"])
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="check", required=True)
    fourminds = sub.add_parser("4minds-dataset")
    fourminds.add_argument("--dataset-id", type=int, help="default: the dataset with the benchmark name")
    llm = sub.add_parser("llm")
    llm.add_argument("--llm", required=True, choices=llm_backends.names())
    llm.add_argument("--timeout", type=float, default=120)
    judge = sub.add_parser("judge")
    judge.add_argument("--llm", required=True, choices=llm_backends.names())
    sub.add_parser("gemini-key-project")
    file_search = sub.add_parser("file-search")
    bc.add_common_args(file_search, "preflight")
    retrievers.add_args(file_search)
    args = parser.parse_args()
    if args.check == "file-search" and not (args.questions_file or args.sample):
        args.sample = 1
    checks = {"llm": check_llm, "judge": check_judge, "gemini-key-project": check_gemini_key_project,
              "file-search": check_file_search, "4minds-dataset": check_4minds_dataset}
    sys.exit(checks[args.check](args))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run benchmark questions as retriever + LLM backend: the retriever finds chunks, the LLM answers.

  --retriever  none | gemini_file_search | vertex_rag_engine | langchain_vector | graphrag_local | ragflow
               (systems/retrievers.py; graphrag_local runs in the graphrag environment)
  --llm        a backend in pipeline/llm_backends.json        (pipeline/llm_backends.py)

A profile with messages(q, contexts) gives the request itself (EnterpriseRAG-Bench: the
official answer prompt in one user message). Otherwise the system message is the profile's
SYSTEM_PROMPT and the user message has the chunks under "---Knowledge Base---" (the layout of
the GraphRAG-Bench LightRAG prompt) and then the question; with --retriever none it is the
question only. The IDs of the retrieved documents go to the prediction when the retriever
returns them (document_ids). The chunks are stored as
`context`. Retrieval and generation are retried separately, and their latency, tokens and
cost are recorded separately (extra.retrieval_s, extra.generation_s). A stopped run continues
where it stopped (runs.jsonl).

    ./bench graphrag-bench pilot_gptoss_norag eval systems/run_rag.py --subset medical \\
        --llm bedrock-gpt-oss-120b --retriever none \\
        --questions-file data/Questions/pilot_questions.json --out-dir runs/<YYYY-MM-DD>_<name>/gptoss_norag
"""
import json
import sys
import time

import bench_common as bc
import llm_backends
import retrievers


PROMPT_LAYOUT = getattr(bc.profile, "PROMPT_LAYOUT", None) if hasattr(bc.profile, "messages") else \
    "system: SYSTEM_PROMPT; user: ---Knowledge Base--- [i] chunk ... ---Question--- question"


def messages_for(q, contexts):
    if hasattr(bc.profile, "messages"):
        return bc.profile.messages(q, contexts)
    if not contexts:
        user = q["question"]
    else:
        knowledge = "\n\n".join(f"[{i}] {c}" for i, c in enumerate(contexts, 1))
        user = f"---Knowledge Base---\n{knowledge}\n\n---Question---\n{q['question']}"
    return [{"role": "system", "content": bc.SYSTEM_PROMPT}, {"role": "user", "content": user}]


def make_ask(args, retriever, backend):
    def ask(q):
        timing, billed = {}, {}

        def retrieval_attempt():
            start = time.monotonic()
            result = retriever.retrieve(q, args.timeout)
            timing["retrieval_s"] = round(time.monotonic() - start, 2)
            for k, v in ((result[1] or {}).get("usage") or {}).items():
                billed[k] = billed.get(k, 0) + v
            return result

        retrieved, r_attempts, error = bc.retry(retrieval_attempt, args)
        if error and error.get("code") == "stopped":
            return None
        if retrieved is None:
            return {"status": "failed", "attempts": r_attempts, "error": {"stage": "retrieval", **error},
                    "usage": billed, "latency_s": timing.get("retrieval_s")}
        messages = messages_for(q, retrieved["contexts"])

        def generation_attempt():
            start = time.monotonic()
            result = backend.chat(messages, args.timeout)
            timing["generation_s"] = round(time.monotonic() - start, 2)
            return result

        generated, g_attempts, error = bc.retry(generation_attempt, args)
        if error and error.get("code") == "stopped":
            return None
        latency = round(timing.get("retrieval_s", 0) + timing.get("generation_s", 0), 2)
        usage = {k: billed.get(k, 0) + retrieved["usage"].get(k, 0) for k in set(billed) | set(retrieved["usage"])}
        attempts = r_attempts + g_attempts - 1  # 1 when neither stage was retried, as for one-call systems
        if generated is None:
            return {"status": "failed", "attempts": attempts, "error": {"stage": "generation", **error},
                    "usage": usage, "latency_s": latency}
        usage.update({k: v for k, v in generated["usage"].items() if isinstance(v, (int, float))})
        result = {"status": "ok", "attempts": attempts, "answer": generated["answer"],
                  "contexts": retrieved["contexts"], "usage": usage, "latency_s": latency,
                  "raw": {"retrieval": retrieved["raw"], "generation": generated["raw"]},
                  "extra": {**retrieved["extra"], "retrieval_s": timing.get("retrieval_s"),
                            "generation_s": timing.get("generation_s"), "finish_reason": generated["finish_reason"],
                            "retrieval_attempts": r_attempts, "generation_attempts": g_attempts}}
        if retrieved.get("document_ids") is not None:
            result["document_ids"] = retrieved["document_ids"]
        return result
    return ask


def main():
    parser = bc.parser(__doc__, "rag")
    parser.add_argument("--llm", required=True, choices=llm_backends.names())
    parser.add_argument("--retriever", required=True, choices=retrievers.NAMES)
    retrievers.add_args(parser)
    args = parser.parse_args()
    if args.out_dir == str(bc.RUNS / "rag"):
        sys.exit("Set --out-dir: one folder for each retriever and backend.")

    questions = bc.load_questions(args)
    backend = llm_backends.Backend(args.llm)
    if args.dry_run:
        example = [] if args.retriever == "none" else ["<chunk text from the retriever>"]
        print(json.dumps({"retriever": args.retriever, "llm": backend.settings(),
                          "request": backend.request_body(messages_for(questions[0], example))}, indent=2))
        return
    if args.workers > backend.max_concurrency:
        sys.exit(f"--workers {args.workers} is more than max_concurrency {backend.max_concurrency} of {backend.name}.")
    retriever = retrievers.make(args.retriever, args)

    def readiness():
        ready = retriever.readiness(questions)
        result, error, _ = backend.chat(messages_for(questions[0], []), args.timeout)
        if error:
            sys.exit(f"Readiness: LLM backend {backend.name} failed one test call: {error}")
        return {**ready, "llm_check": {"finish_reason": result["finish_reason"], "usage": result["usage"]}}

    def cost(tokens):
        parts = [backend.cost(tokens), retriever.cost(tokens)]
        return sum(p for p in parts if p is not None) if any(p is not None for p in parts) else None

    settings = {**retriever.settings(), **backend.settings(), "system_prompt": bc.SYSTEM_PROMPT,
                "prompt_layout": PROMPT_LAYOUT}
    summary = bc.run(f"{args.retriever}+{backend.name}", args, make_ask(args, retriever, backend), settings, readiness,
                     cost, {"price_usd_per_1m": {"llm": backend.prices, "retrieval": getattr(retriever, "prices", None)}})
    sys.exit(1 if bc.STOP.is_set() or summary["failed"] else 0)


if __name__ == "__main__":
    main()

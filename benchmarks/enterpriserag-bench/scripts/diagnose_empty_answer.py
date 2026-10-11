#!/usr/bin/env python3
"""Send the run_rag.py request of one question once and show the raw reply of the backend.

    ./bench enterpriserag-bench diagnose_empty erag diagnose_empty_answer.py --question-id qst_0443 \\
        --llm bedrock-gpt-oss-120b [--repeat 3]

For a question that fails with "empty_answer": it shows the message content before and after
the <reasoning> tags are removed, the finish reason and the usage. No retrieval (the request
of --retriever none). Output: audit/diagnostics/empty_answer_<question_id>.json.
"""
import argparse
import json

import requests

import bench_common as bc
import llm_backends
import run_rag


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--llm", required=True, choices=llm_backends.names())
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()
    questions = json.loads(bc.QUESTION_FILES["all"].read_text())
    q = next(q for q in questions if bc.question_key(q) == args.question_id)
    backend = llm_backends.Backend(args.llm)
    body = backend.request_body(run_rag.messages_for(q, []))
    replies = []
    for _ in range(args.repeat):
        response = requests.post(f"{backend.base_url}/chat/completions", json=body, timeout=120,
                                 headers={"Authorization": f"Bearer {backend.api_key()}"})
        payload = response.json()
        message = ((payload.get("choices") or [{}])[0].get("message") or {})
        content = message.get("content") or ""
        replies.append({"http_status": response.status_code,
                        "finish_reason": (payload.get("choices") or [{}])[0].get("finish_reason"),
                        "usage": payload.get("usage"), "message_keys": sorted(message),
                        "content": content, "content_without_reasoning":
                            llm_backends.REASONING_TAGS.sub("", content).strip()})
    out = bc.AUDIT_DIR / "diagnostics" / f"empty_answer_{args.question_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"time": bc.now(), "question": q["question"], "backend": backend.settings(),
                               "replies": replies}, indent=2, ensure_ascii=False))
    for r in replies:
        print(json.dumps({k: r[k] for k in ("finish_reason", "usage", "message_keys", "content_without_reasoning")}))
        print("content:", r["content"][:1500])
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

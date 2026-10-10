#!/usr/bin/env python3
"""Check that a judge's replies can be read by the official GraphRAG-Bench parsers. Diagnosis only.

For the first N answers of a system, run the official answer-correctness steps with the judge:
the statement prompt (parsed with the official JSONHandler fallbacks) and the factuality prompt
(parsed with plain json.loads in calculate_factuality, which returns 0.0 on any error). Record
the start and end of each raw reply, and whether json.loads can read it as is and after the fence
fix of pipeline/judge_hooks.py (judge_strip_code_fence), the TP/FP/FN counts and the output
tokens. --extra-body replaces the backend's judge_extra_body, to compare request settings (for
example Claude thinking) before a backend entry is made for them.
Output: audit/diagnostics/judge_format_<judge>[_<label>].json

    ./bench graphrag-bench diagnose_judge_format eval diagnose_judge_format.py \\
        --system-dir runs/<run>/<system>/medical --judge anthropic-claude-haiku-5-5 --n 4
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

import bench_common as bc
import judge_hooks
import llm_backends

sys.path.insert(0, str(bc.UPSTREAM_REPO))
from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic import SecretStr  # noqa: E402
from Evaluation.metrics import answer_accuracy as A  # noqa: E402


def readable(text):
    fixed = judge_hooks.unfence(text)
    parsed = text if judge_hooks.is_json(text) else (fixed[0] if fixed else None)
    counts = {}
    if parsed is not None:
        data = json.loads(parsed)
        counts = {k: len(data.get(k) or []) for k in ("TP", "FP", "FN")} if isinstance(data, dict) else {}
    return {"json_loads": judge_hooks.is_json(text), "json_after_fence_fix": parsed is not None,
            "prose_outside_fence": bool(fixed and fixed[1]), **counts}


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--system-dir", required=True)
    parser.add_argument("--judge", required=True, choices=llm_backends.names())
    parser.add_argument("--n", type=int, default=4)
    parser.add_argument("--ids", nargs="*", help="check these question ids instead of the first N")
    parser.add_argument("--repeat", type=int, default=1, help="factuality calls per answer (the judge samples at random)")
    parser.add_argument("--extra-body", type=json.loads, help="JSON fields added to each request, instead of judge_extra_body")
    parser.add_argument("--label", help="suffix of the output file name")
    args = parser.parse_args()
    judge = llm_backends.Backend(args.judge)
    extra_body = judge.judge_extra_body if args.extra_body is None else args.extra_body
    totals = judge_hooks.install(None, judge.judge_drop_params, extra_body=extra_body)
    llm = ChatOpenAI(model=judge.model, base_url=judge.base_url, api_key=SecretStr(judge.api_key()), temperature=0.0,
                     max_retries=3, timeout=60,
                     model_kwargs={"top_p": 1, "seed": 42, "presence_penalty": 0, "frequency_penalty": 0})
    items = json.loads((Path(args.system_dir) / "predictions.json").read_text())
    items = [i for i in items if i["id"] in args.ids] if args.ids else items[:args.n]
    examples = "\n".join(f"Input: {json.dumps(ex['input'])}\nOutput: {json.dumps(ex['output'])}"
                         for ex in A.CORRECTNESS_EXAMPLES)
    rows = []
    for item in items:
        answer_stmts = await A.generate_statements(llm, item["question"], item["generated_answer"], None)
        gt_stmts = await A.generate_statements(llm, item["question"], item["ground_truth"], None)
        prompt = A.CORRECTNESS_PROMPT_TEMPLATE.format(examples=examples, question=item["question"],
                                                      answer=json.dumps(answer_stmts), ground_truth=json.dumps(gt_stmts))
        for _ in range(args.repeat):
            message = await llm.ainvoke(prompt)
            reply, meta = message.content, message.response_metadata
            rows.append({"id": item["id"], "answer_statements": len(answer_stmts), "gold_statements": len(gt_stmts),
                         "finish_reason": meta.get("finish_reason"),
                         "completion_tokens": (meta.get("token_usage") or {}).get("completion_tokens"),
                         "factuality_reply_start": reply[:200], "factuality_reply_end": reply[-120:], **readable(reply)})
            print(json.dumps({k: v for k, v in rows[-1].items() if not k.startswith("factuality_reply")}))
    out = {"created": bc.now(), "judge": judge.name, "model": judge.model, "extra_body": extra_body,
           "system_dir": str(Path(args.system_dir).resolve()), "rows": rows, "usage_all_calls": totals,
           "factuality_readable_by_official_parser": sum(r["json_loads"] for r in rows),
           "readable_after_fence_removal": sum(r["json_after_fence_fix"] for r in rows)}
    path = bc.AUDIT_DIR / "diagnostics" / f"judge_format_{judge.name}{'_' + args.label if args.label else ''}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2))
    bc.audit("diagnose_judge_format", judge=judge.name, extra_body=extra_body, path=str(path), n=len(rows),
             official_parser_ok=out["factuality_readable_by_official_parser"],
             ok_after_fence_removal=out["readable_after_fence_removal"],
             completion_tokens=totals["completion_tokens"], calls=totals["calls"])
    print(f"official parser read {out['factuality_readable_by_official_parser']}/{len(rows)}; "
          f"after fence removal {out['readable_after_fence_removal']}/{len(rows)}; "
          f"all calls {totals['calls']}, output tokens {totals['completion_tokens']}; {path}")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Score one answer with one metric and print each judge reply that is not JSON (a diagnosis).

    ./bench 4minds-rag diagnose_qst_0454 extra diagnose_judge_reply.py --config configs/scorers/v2_haiku-nothink.json \\
        --system-dir runs/<run>/gptoss_ragflow/all --id qst_0454 --metric deepeval_summarization

Writes nothing to the run; the replies go to the terminal and the step log. Only for a judge
from pipeline/llm_backends.json ("provider": "backend").
"""
import argparse
import asyncio
import json
from pathlib import Path

import judge_hooks
import score_extra as se


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True)
    parser.add_argument("--system-dir", required=True)
    parser.add_argument("--id", required=True, help="question id")
    parser.add_argument("--metric", required=True, help="metric key in the config")
    args = parser.parse_args()
    config = se.load_config(args.config)
    metric = next(m for m in config["metrics"] if m["key"] == args.metric)
    row = next(r for r in se.load_rows(Path(args.system_dir) / "predictions.json", None) if r["id"] == args.id)
    shared = json.loads(se.shared_path(config).read_text()) if se.shared_path(config).exists() else {}
    judge = se.BackendJudge(config["judge"])
    read_reply = judge._read_reply

    def logged(response):
        response = read_reply(response)
        for choice in json.loads(response.content).get("choices") or []:
            content = (choice.get("message") or {}).get("content")
            if not judge_hooks.is_json(content):
                print(f"--- reply that is not JSON (finish_reason {choice.get('finish_reason')}):\n{content}\n---")
        return response

    judge._read_reply = logged
    print(f"answer: {row['generated_answer'][:300]!r}")
    print(f"evidence: {row['evidence']}")
    try:
        values, details, _ = asyncio.run(se.METRICS[metric["implementation"]](row, metric, judge, shared))
        print(f"result: {values} {details}")
    except Exception as e:
        print(f"error: {se.describe(e)}")
    print(f"judge usage: {json.dumps(judge.usage())}")


if __name__ == "__main__":
    main()

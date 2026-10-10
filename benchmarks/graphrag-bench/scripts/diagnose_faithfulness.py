"""Find why faithfulness is NaN for some Creative Generation samples. Diagnosis only.

Runs the two official steps (_generate_statements, _evaluate_statements) from
Evaluation/metrics/faithfulness.py with the same judge settings as generation_eval.py.
A thin wrapper records each raw judge response and each exception, which the official
code hides (every failure path returns an empty list, which gives NaN).

    ./bench graphrag-bench diagnose_faithfulness eval diagnose_faithfulness.py --run runs/2026-10-09_gemini-pilot
"""
import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path

import bench_common as bc

sys.path.insert(0, str(bc.UPSTREAM_REPO))
from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic import SecretStr  # noqa: E402
from Evaluation.metrics import faithfulness as F  # noqa: E402


class RecordingLLM:
    def __init__(self, llm, calls):
        self.llm, self.calls = llm, calls

    async def ainvoke(self, prompt, config=None):
        t0 = time.monotonic()
        try:
            response = await self.llm.ainvoke(prompt, config=config)
        except Exception as e:
            self.calls.append({"elapsed_s": round(time.monotonic() - t0, 1), "prompt_chars": len(prompt),
                               "exception": f"{type(e).__name__}: {e}"[:500]})
            raise
        self.calls.append({"elapsed_s": round(time.monotonic() - t0, 1), "prompt_chars": len(prompt),
                           "response": response.content})
        return response


async def diagnose(item, llm):
    calls = []
    judge = RecordingLLM(llm, calls)
    statements = await F._generate_statements(item["question"], item["generated_answer"], judge, None, 2)
    report = {"statements": statements, "statement_calls": list(calls)}
    calls.clear()
    if statements and "\n".join(item["contexts"]).strip():
        report["verdicts"] = await F._evaluate_statements(statements, "\n".join(item["contexts"]), judge, None, 2)
        report["verdict_calls"] = list(calls)
    return report


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", "--results", dest="results", required=True, help="run folder, for example runs/<YYYY-MM-DD>_<name>")
    args = parser.parse_args()

    llm = ChatOpenAI(model="gpt-4o-mini", api_key=SecretStr(bc.load_key("openai")), temperature=0.0,
                     max_retries=3, timeout=30,
                     model_kwargs={"top_p": 1, "seed": 42, "presence_penalty": 0, "frequency_penalty": 0})
    out = {}
    for scores in sorted(Path(args.results).glob("*/medical/generation_scores.json")):
        system = scores.parts[-3]
        for item in json.loads(scores.read_text()).get("Creative Generation", {}).get("detailed", []):
            value = item["metrics"].get("faithfulness")
            if not (isinstance(value, float) and math.isnan(value)):
                continue
            print(f"{system} {item['id']}: answer {len(item['generated_answer'])} chars, "
                  f"context {len(''.join(item['contexts']))} chars")
            report = await diagnose(item, llm)
            out[f"{system}::{item['id']}"] = report
            for step in ("statement_calls", "verdict_calls"):
                for call in report.get(step, []):
                    detail = call.get("exception") or call["response"][:300].replace("\n", " ")
                    print(f"  {step} {call['elapsed_s']} s: {detail}")
            print(f"  statements {len(report['statements'])}, verdicts {len(report.get('verdicts') or [])}")
    path = bc.AUDIT_DIR / "diagnostics" / "faithfulness_nan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"wrote {path}")


if __name__ == "__main__":
    asyncio.run(main())

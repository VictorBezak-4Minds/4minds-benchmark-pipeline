#!/usr/bin/env python3
"""Extra scorers on saved answers (RAGAS, DeepEval). Not part of the official GraphRAG-Bench protocol.

  ./bench graphrag-bench extra_prepare extra score_extra.py prepare --config configs/scorers/extra_v1.json \\
      --predictions runs/2026-10-10_gptoss-full/gptoss_norag/medical/predictions.json
  ./bench graphrag-bench extra_<system> extra score_extra.py score --config configs/scorers/extra_v1.json \\
      --system-dir runs/2026-10-10_gptoss-full/<system>/medical [--questions-file data/Questions/pilot_questions.json] \\
      [--out-dir runs/2026-10-10_gptoss-full/extra/extra_v1_pilot/<system>]

The config file (configs/scorers/extra_*.json) gives the judge and the metrics: for each metric its key,
its implementation in METRICS, params, question types and inputs. `prepare` makes the inputs that
must be the same for every system (Summarization assessment questions) in
shared/extra/<config name>/shared.json; `score` reads them.

`score` appends one record per answer and metric to <out-dir>/<config name>.partial.jsonl and
writes <out-dir>/<config name>.json. A rerun scores only the items that are not done; items
with an error or a NaN score are tried again. Exit code 1 while any item is not scored.
"""
import argparse
import asyncio
import json
import math
import os
import sys
from importlib import metadata
from pathlib import Path

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "1")
os.environ.setdefault("DEEPEVAL_UPDATE_WARNING_OPT_IN", "0")
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

import bench_common as bc  # noqa: E402

TYPES = ["Fact Retrieval", "Complex Reasoning", "Contextual Summarize", "Creative Generation"]


class OpenAIJudge:
    """The judge through the OpenAI API. Token use of RAGAS calls is counted from the HTTP replies;
    DeepEval reports its own cost per metric."""

    def __init__(self, spec):
        self.model, self.args = spec["model"], dict(spec.get("args", {}))
        self.prices = spec["price_usd_per_1m"]
        self.key = bc.load_key(spec.get("key", "openai"))
        self.tokens = {"prompt_tokens": 0, "completion_tokens": 0}
        self._ragas_llm = self._deepeval_model = None

    def ragas_llm(self):
        if self._ragas_llm is None:
            import httpx
            from openai import AsyncOpenAI
            from ragas.llms import llm_factory

            async def count(response):
                await response.aread()
                try:
                    usage = response.json().get("usage") or {}
                except ValueError:
                    return
                for k in self.tokens:
                    self.tokens[k] += usage.get(k) or 0

            client = AsyncOpenAI(api_key=self.key, http_client=httpx.AsyncClient(
                timeout=120, event_hooks={"response": [count]}))
            self._ragas_llm = llm_factory(self.model, client=client, **self.args)
        return self._ragas_llm

    def deepeval_model(self):
        if self._deepeval_model is None:
            from deepeval.models import OpenAIModel
            self._deepeval_model = OpenAIModel(
                model=self.model, api_key=self.key, temperature=self.args.get("temperature", 0),
                cost_per_input_token=self.prices["input"] / 1e6, cost_per_output_token=self.prices["output"] / 1e6,
                generation_kwargs={k: v for k, v in self.args.items() if k != "temperature"})
        return self._deepeval_model

    def ragas_cost(self):
        return (self.tokens["prompt_tokens"] * self.prices["input"]
                + self.tokens["completion_tokens"] * self.prices["output"]) / 1e6


JUDGES = {"openai": OpenAIJudge}


def evidence_items(row, metric):
    separator = metric.get("context_separator")
    text = row.get(metric.get("context") or metric.get("source") or "evidence") or ""
    return [s.strip() for s in (text.split(separator) if separator else [text]) if s.strip()]


async def ragas_answer_accuracy(row, metric, judge, shared):
    from ragas.metrics.collections import AnswerAccuracy
    result = await AnswerAccuracy(llm=judge.ragas_llm(), **metric["params"]).ascore(
        user_input=row["question"], response=row["generated_answer"], reference=row["ground_truth"])
    return {"score": result.value}, {}, 0.0


async def ragas_factual_correctness(row, metric, judge, shared):
    import numpy as np
    from ragas.metrics.collections import FactualCorrectness
    from ragas.metrics.utils import fbeta_score
    params = dict(metric["params"])
    beta = params.pop("beta", 1.0)
    scorer = FactualCorrectness(llm=judge.ragas_llm(), mode="f1", beta=beta, **params)
    answer_claims = await scorer._decompose_and_verify_claims(row["generated_answer"], row["ground_truth"])
    gold_claims = await scorer._decompose_and_verify_claims(row["ground_truth"], row["generated_answer"])
    tp, fp, fn = int(np.sum(answer_claims)), int(np.sum(~answer_claims)), int(np.sum(~gold_claims))
    values = {"precision": tp / (tp + fp + 1e-8), "recall": tp / (tp + fn + 1e-8), "f1": fbeta_score(tp, fp, fn, beta)}
    return {k: float(np.round(v, 2)) for k, v in values.items()}, {"tp": tp, "fp": fp, "fn": fn}, 0.0


async def deepeval_summarization(row, metric, judge, shared):
    from deepeval.metrics import SummarizationMetric
    from deepeval.test_case import LLMTestCase
    questions = (shared.get("assessment_questions") or {}).get(row["id"])
    if not questions:
        raise RuntimeError(f"no shared assessment questions for {row['id']}: run `score_extra.py prepare` first")
    scorer = SummarizationMetric(model=judge.deepeval_model(), assessment_questions=questions, include_reason=False,
                                 async_mode=True, **metric["params"])
    case = LLMTestCase(input="\n".join(evidence_items(row, metric)), actual_output=row["generated_answer"])
    await scorer.a_measure(case, _show_indicator=False)
    breakdown = scorer.score_breakdown or {}
    return ({"score": scorer.score, "alignment": breakdown.get("Alignment"), "coverage": breakdown.get("Coverage")},
            {"assessment_questions": len(questions)}, scorer.evaluation_cost or 0.0)


async def deepeval_hallucination(row, metric, judge, shared):
    from deepeval.metrics import HallucinationMetric
    from deepeval.test_case import LLMTestCase
    context = evidence_items(row, metric)
    scorer = HallucinationMetric(model=judge.deepeval_model(), include_reason=False, async_mode=True, **metric["params"])
    case = LLMTestCase(input=row["question"], actual_output=row["generated_answer"], context=context)
    await scorer.a_measure(case, _show_indicator=False)
    verdicts = [getattr(getattr(v, "verdict", None), "value", getattr(v, "verdict", None)) for v in scorer.verdicts or []]
    contradicted = sum(1 for v in verdicts if str(v).strip().lower() == "no")
    return {"score": scorer.score}, {"contexts": len(context), "contradicted": contradicted}, scorer.evaluation_cost or 0.0


METRICS = {f.__name__: f for f in (ragas_answer_accuracy, ragas_factual_correctness,
                                   deepeval_summarization, deepeval_hallucination)}
SHARED_INPUTS = {"deepeval_summarization"}  # implementations that need `prepare`


def load_config(path):
    path = Path(path)
    if not path.is_absolute() and not path.exists():
        path = bc.BENCH_DIR / path
    config = json.loads(path.read_text())
    problems = [] if config.get("judge", {}).get("provider") in JUDGES else [
        f"judge provider must be one of {sorted(JUDGES)}"]
    keys = [m.get("key") for m in config.get("metrics", [])]
    problems += [f"duplicate metric key {k}" for k in set(keys) if keys.count(k) > 1]
    for m in config.get("metrics", []):
        if m.get("implementation") not in METRICS:
            problems.append(f"metric {m.get('key')}: unknown implementation {m.get('implementation')}")
        types = m.get("question_types")
        if types != "all" and not (isinstance(types, list) and set(types) <= set(TYPES)):
            problems.append(f"metric {m.get('key')}: question_types must be \"all\" or a list of {TYPES}")
    if problems:
        sys.exit(f"{path}: " + "; ".join(problems))
    config["path"], config["sha256"] = str(path), bc.sha256(path)
    return config


def applies(metric, row):
    return metric["question_types"] == "all" or row["question_type"] in metric["question_types"]


def output_name(metric, output):
    return metric["key"] if output == "score" else f"{metric['key']}_{output}"


def shared_path(config):
    return bc.SHARED / "extra" / config["name"] / "shared.json"


def load_rows(predictions, questions_file):
    rows = json.loads(Path(predictions).read_text())
    if questions_file:
        wanted = {q["id"] for q in json.loads(Path(questions_file).read_text())}
        rows = [r for r in rows if r["id"] in wanted]
    return rows


def versions():
    return {p: metadata.version(p) for p in ("ragas", "deepeval", "openai")}


async def prepare(config, rows):
    from deepeval.metrics import SummarizationMetric
    path = shared_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    judge = JUDGES[config["judge"]["provider"]](config["judge"])
    shared = json.loads(path.read_text()) if path.exists() else {
        "created": bc.now(), "judge": config["judge"]["model"], "assessment_questions": {}}
    if shared["judge"] != config["judge"]["model"]:
        sys.exit(f"{path} was made with judge {shared['judge']}; use a new config name for another judge.")
    questions = shared["assessment_questions"]
    semaphore = asyncio.Semaphore(config.get("concurrency", 8))
    cost = 0.0

    async def one(row, metric):
        nonlocal cost
        async with semaphore:
            maker = SummarizationMetric(model=judge.deepeval_model(), **metric["params"])
            made = await maker._a_generate_assessment_questions("\n".join(evidence_items(row, metric)))
            cost += maker.evaluation_cost or 0.0
            questions[row["id"]] = made
            shared.update({"updated": bc.now(), "versions": versions(), "params": metric["params"]})
            path.write_text(json.dumps(shared, indent=2))

    jobs = [one(row, m) for m in config["metrics"] if m["implementation"] in SHARED_INPUTS
            for row in rows if applies(m, row) and row["id"] not in questions]
    results = await asyncio.gather(*jobs, return_exceptions=True)
    errors = [r for r in results if isinstance(r, Exception)]
    bc.audit("extra_prepare", config=config["path"], made=len(jobs) - len(errors), errors=len(errors), cost_usd=round(cost, 4))
    print(f"{path}: {len(questions)} questions with assessment questions; made {len(jobs) - len(errors)}, "
          f"errors {len(errors)}, cost ${cost:.4f}")
    for e in errors[:3]:
        print(f"  error: {type(e).__name__}: {str(e)[:200]}")
    return 1 if errors else 0


def read_checkpoint(path, header):
    done, invocations = {}, []
    if not path.exists():
        path.write_text(json.dumps({"header": header}) + "\n")
        return done, invocations
    lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    saved = lines[0].get("header", {})
    changed = [k for k in ("predictions_sha256", "config_sha256") if saved.get(k) != header[k]]
    if changed:
        sys.exit(f"{path} was made with different {', '.join(changed)}. Use a new --out-dir or config name.")
    for record in lines[1:]:
        if "invocation" in record:
            invocations.append(record["invocation"])
        elif not record.get("error"):
            done[(record["id"], record["metric"])] = record
    return done, invocations


async def score(config, rows, out_dir, predictions):
    out_dir.mkdir(parents=True, exist_ok=True)
    bc.acquire_lock(out_dir / f".{config['name']}.lock")
    shared = json.loads(shared_path(config).read_text()) if shared_path(config).exists() else {}
    if shared and shared.get("judge") != config["judge"]["model"]:
        sys.exit(f"{shared_path(config)} was made with judge {shared.get('judge')}, not {config['judge']['model']}.")
    header = {"created": bc.now(), "config": config["path"], "config_sha256": config["sha256"],
              "predictions": str(predictions), "predictions_sha256": bc.sha256(Path(predictions))}
    partial = out_dir / f"{config['name']}.partial.jsonl"
    done, invocations = read_checkpoint(partial, header)
    judge = JUDGES[config["judge"]["provider"]](config["judge"])
    semaphore = asyncio.Semaphore(config.get("concurrency", 8))
    deepeval_cost = 0.0
    todo = [(row, m) for m in config["metrics"] for row in rows if applies(m, row) and (row["id"], m["key"]) not in done]
    print(f"== {config['name']} on {predictions}: {len(rows)} answers, {len(done)} items done, {len(todo)} to score")

    async def one(row, metric):
        nonlocal deepeval_cost
        async with semaphore:
            record = {"id": row["id"], "question_type": row["question_type"], "metric": metric["key"], "time": bc.now()}
            try:
                values, details, cost = await METRICS[metric["implementation"]](row, metric, judge, shared)
                deepeval_cost += cost
                bad = [k for k, v in values.items() if v is None or (isinstance(v, float) and math.isnan(v))]
                record.update({"values": values, "details": details})
                if bad:
                    record["error"] = f"no score for {', '.join(bad)} (NaN or missing)"
            except Exception as e:  # one failed item must not stop the others; a rerun tries it again
                record["error"] = f"{type(e).__name__}: {str(e)[:300]}"
            with partial.open("a") as f:
                f.write(json.dumps(record) + "\n")
            if not record.get("error"):
                done[(row["id"], metric["key"])] = record
            return record

    finished = 0
    for task in asyncio.as_completed([one(row, m) for row, m in todo]):
        record = await task
        finished += 1
        if record.get("error") or finished % 100 == 0 or finished == len(todo):
            print(f"  [{finished}/{len(todo)}] {record['metric']} {record['id']}"
                  + (f" ERROR {record['error'][:160]}" if record.get("error") else ""))

    invocation = {"time": bc.now(), "items": len(todo), "judge_tokens_ragas": dict(judge.tokens),
                  "cost_usd": round(judge.ragas_cost() + deepeval_cost, 6)}
    with partial.open("a") as f:
        f.write(json.dumps({"invocation": invocation}) + "\n")
    invocations.append(invocation)

    expected = [(row["id"], m) for m in config["metrics"] for row in rows if applies(m, row)]
    missing = [(qid, m["key"]) for qid, m in expected if (qid, m["key"]) not in done]
    scores = {}
    for qid, m in expected:
        record = done.get((qid, m["key"]))
        for output in m.get("outputs", ["score"]):
            name = output_name(m, output)
            scores.setdefault(name, {})
            if record:
                scores[name][qid] = record["values"].get(output)
    by_type = {qid: row["question_type"] for qid, row in ((r["id"], r) for r in rows)}
    summary = {}
    for name, values in scores.items():
        kept = [v for v in values.values() if v is not None]
        summary[name] = {"n": len(kept), "mean": round(sum(kept) / len(kept), 4) if kept else None}
    out = {"config": {k: config[k] for k in ("name", "description", "path", "sha256", "judge", "metrics")},
           "versions": versions(), "predictions": str(predictions), "predictions_sha256": header["predictions_sha256"],
           "answers": len(rows), "items": len(expected), "not_scored": len(missing),
           "not_scored_items": [{"id": q, "metric": k} for q, k in missing],
           "cost_usd": round(sum(i["cost_usd"] for i in invocations), 4), "invocations": invocations,
           "question_types": by_type, "summary": summary, "scores": scores, "finished": bc.now()}
    (out_dir / f"{config['name']}.json").write_text(json.dumps(out, indent=2))
    bc.audit("extra_score", config=config["path"], predictions=str(predictions), out_dir=str(out_dir),
             items=len(expected), not_scored=len(missing), cost_usd=out["cost_usd"])
    print(f"done: {len(expected) - len(missing)}/{len(expected)} items scored, not scored {len(missing)}, "
          f"cost this run ${invocation['cost_usd']:.4f}, total ${out['cost_usd']:.4f}")
    for name, s in summary.items():
        print(f"  {name}: mean {s['mean']} (n={s['n']})")
    return 1 if missing else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="make the shared inputs (assessment questions) once for all systems")
    p.add_argument("--config", required=True)
    p.add_argument("--predictions", required=True, help="predictions.json of any system (questions and evidence)")
    p.add_argument("--questions-file")
    s = sub.add_parser("score", help="score the saved answers of one system")
    s.add_argument("--config", required=True)
    s.add_argument("--system-dir", required=True, help="folder with predictions.json")
    s.add_argument("--questions-file", help="score only these questions (pilot)")
    s.add_argument("--out-dir", help="default: --system-dir")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.command == "prepare":
        sys.exit(asyncio.run(prepare(config, load_rows(args.predictions, args.questions_file))))
    system_dir = Path(args.system_dir)
    predictions = system_dir / "predictions.json"
    out_dir = Path(args.out_dir) if args.out_dir else system_dir
    sys.exit(asyncio.run(score(config, load_rows(predictions, args.questions_file), out_dir, predictions)))


if __name__ == "__main__":
    main()

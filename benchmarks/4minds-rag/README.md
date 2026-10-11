# 4Minds RAG (our metrics on saved answers)

4Minds RAG scores the saved answers of other benchmark runs with a fixed set of open-source
metrics that we chose. It has no questions, corpus or official scorer of its own. The systems do
not answer again: a run links the answers of the source run, so only the scorer changes.

**Status:** the first source is the EnterpriseRAG-Bench pilot
(`../enterpriserag-bench/runs/2026-10-10_gptoss-pilot`: 5 GPT-OSS-120B systems, 50 questions,
10,000-document slice). Two versions with the same settings and a different judge:
v1 gpt-4o-mini, v2 Claude Haiku 5.5 with thinking disabled. See `runs/README.md`.

## Metrics

| Metric | Library | Reference | Output |
|---|---|---|---|
| Answer Accuracy | RAGAS 0.4.3 (NVIDIA metric) | gold answer | score |
| Factual Correctness | RAGAS 0.4.3 | gold answer | claim precision, recall, F1 |
| Summarization | DeepEval 4.2.8 | gold facts | score = min(alignment, coverage) |
| Hallucination | DeepEval 4.2.8 | gold facts | fraction of facts that the answer agrees with (higher is better) |
| Document retrieval | none (exact match) | gold document IDs | document precision, recall, F1 |

All scores are 0 to 1, higher is better. `pipeline/make_cheatsheet.py` (`metrics_cheatsheet.html`)
explains each formula. Two kinds of precision, recall and F1 are in the report:

- **Claim level** (Factual Correctness, judge): precision = claims of the answer that the gold
  answer supports; recall = claims of the gold answer that the answer has.
- **Document level** (document retrieval, no judge): precision = gold documents among the
  documents that the system gave; recall = gold documents that the system gave, of all gold
  documents. Only the 46 questions with gold documents. The gold list is the original one (the
  official EnterpriseRAG-Bench scorer can add documents to it for each system; we do not).

The settings of each metric are in `configs/scorers/v1_gpt-4o-mini.json` and
`configs/scorers/v2_haiku-nothink.json`. The two files are the same except the name, the
description and the judge. Do not edit a config that a run used: the score checkpoints compare
its sha256. For new settings, make a new config file with a new name and a new run.

## How the data joins

`benchmark_profile.extra_rows()` joins each saved answer (`predictions.json`: `question_id`,
`generated_answer`, `document_ids`) to its question in `../enterpriserag-bench/data/pilot_questions.json`
(`gold_answer` as ground truth, `answer_facts` as evidence, `expected_doc_ids` as gold documents).
A question without an answer has no row, so it is not in that system's means (No RAG: 49 answers).

## Layout

| Path | Content |
|---|---|
| `benchmark_profile.py` | the profile; it reads the EnterpriseRAG-Bench pilot files in place |
| `configs/scorers/` | one scorer config per version (judge and metrics) |
| `configs/comparisons/erag_pilot.json` | the 5 systems, colors, headline metrics, bootstrap settings, caveats |
| `scripts/aggregate.py` | `summary/scores.json` and `report.md`: means, bootstrap 95% CI, per question type, judge use |
| `scripts/make_report.py` | `summary/report.html` (4Minds style, `pipeline/report_html.py`), `answers.html` and the export file |
| `scripts/export_page.py` | `runs/<run>/export/4minds-rag_<run>.html`: the report and the question browser in one file to share (two tabs; all CSS, data and scripts inline; only the fonts come from the internet). It has the answers, so git does not track it |
| `scripts/answers_page.py` | `runs/<run>/answers.html`: the question browser (each question, its gold data, and each system's answer, scores, documents and context). It has the answers, so git does not track it |
| `scripts/compare_judges.py` | agreement of two runs that differ only in the judge |
| `shared/extra/<config name>/shared.json` | the Summarization assessment questions (one set per question, the same for all systems) |
| `runs/<run>/<system>/all/` | links to the source answers, and `<config name>.json` / `.partial.jsonl` (the scores) |

## Run a version

The steps for v1. For v2, use the v2 config and run folder. `RUN` is the run folder; all
commands start in the hub root.

```zsh
RUN=runs/2026-10-11_erag-pilot_judge-gpt-4o-mini
CFG=configs/scorers/v1_gpt-4o-mini.json
# 1. A new run that links the answers of the source run.
./bench 4minds-rag derive_v1 eval pipeline/derive_run.py --from ../enterpriserag-bench/runs/2026-10-10_gptoss-pilot \
    --to $RUN --change "4Minds RAG metrics, judge gpt-4o-mini" --title "4Minds RAG v1 (judge gpt-4o-mini)"
# 2. The shared Summarization assessment questions (once per config).
./bench 4minds-rag extra_prepare_v1 extra pipeline/score_extra.py prepare --config $CFG \
    --predictions $RUN/4minds/all/predictions.json
# 3. Score each system (repeat for every system folder). A rerun scores only the missing items.
./bench 4minds-rag extra_v1_4minds extra pipeline/score_extra.py score --config $CFG --system-dir $RUN/4minds/all
# 4. Summary and report.
./bench 4minds-rag aggregate_v1 eval aggregate.py --matrix configs/comparisons/erag_pilot.json --scorer $CFG --run $RUN
./bench 4minds-rag report_v1 eval make_report.py --run $RUN
```

`derive_run.py` takes the run folder of `--from` relative to this benchmark. Before a new judge
is used, check it on two answers: `score ... --limit 2 --out-dir $RUN/tests/judge_check/<system>`,
and look at `not_json_replies` and `fences_removed` in the printed judge usage.

## Caveats

- Not an official protocol. Use these numbers to compare systems on the same answers, not with
  public leaderboards.
- The judge is not fully repeatable, and the pilot has 2 to 17 questions per type. Do not draw
  conclusions from small differences or from one question type.
- Hallucination: the DeepEval prompt says that missing detail is not a contradiction, but the
  judges usually give "does not agree" to an answer that says the documents do not have the
  information. So "I don't know" usually scores 0, not 1 (the metric notes in the scorer configs
  say 1; `configs/comparisons/erag_pilot.json` `metric_notes` corrects the report text). Read it
  together with Answer Accuracy and Factual Correctness.
- The GraphRAG row of the source run is not representative of GraphRAG (fast method, no entity
  descriptions); see the EnterpriseRAG-Bench README.

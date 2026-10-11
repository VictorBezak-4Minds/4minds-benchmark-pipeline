#!/usr/bin/env python3
"""Write metrics_cheatsheet.html (hub root): the metrics of each benchmark, why, and how.

  python3 pipeline/make_cheatsheet.py

Update the text here when a benchmark adds or changes a metric.
"""
from html import escape
from pathlib import Path

from report_html import head, header

OUT = Path(__file__).resolve().parent.parent / "metrics_cheatsheet.html"

# (name, used on, why, how)
BENCHMARKS = [
    ("GraphRAG-Bench · Medical",
     "Official generation_eval.py at commit fdbab59. Judge gpt-4o-mini-2024-07-18, embeddings BAAI/bge-large-en-v1.5. "
     "Each question type has its own metric set.",
     [("Answer correctness", "All types (headline)",
       "The only official metric for all four types, so it is the headline. It checks facts, not wording.",
       "0.75 × factuality F1 + 0.25 × similarity. The judge labels statements as TP, FP or FN against the gold answer: "
       "F1 = TP / (TP + (FP + FN) / 2). Similarity = (cosine of the embeddings + 1) / 2."),
      ("ROUGE-L", "Fact Retrieval, Complex Reasoning",
       "Official for the short-answer types. No LLM, so it is fully repeatable.",
       "F-measure of the longest common word sequence between the answer and the gold answer (stemmed)."),
      ("Coverage", "Contextual Summarize, Creative Generation",
       "Official for the long-answer types. It shows if the answer is complete.",
       "The judge splits the gold answer into facts and marks each fact as covered or not. Score = covered / all. "
       "Extra text does not decrease it."),
      ("Faithfulness (official)", "Creative Generation",
       "The only metric that checks the answer against the retrieved context (grounding).",
       "The judge gives each answer statement 1 or 0 against the context that the system returned (first 10,000 "
       "characters). Score = supported / all. Mostly NaN at this commit (the prompt does not ask for JSON)."),
      ("Faithfulness (JSON-format fix)", "Creative Generation",
       "Gives a usable grounding number while the official one is NaN. Not official.",
       "The same code and judge, plus one sentence in the verdict prompt that asks for JSON."),
      ]),
    ("QASPER · answer-only",
     "Official qasper_evaluator.py (v0.3 test release), unchanged, on the 25-question gold subset. No LLM judge.",
     [("Answer F1", "All questions (headline)",
       "The official QASPER answer metric. It is deterministic, so runs are repeatable.",
       "SQuAD token F1: lowercase, remove punctuation and articles, then F1 of the shared words. Each question takes "
       "the maximum over its reference answers. Missing prediction = 0."),
      ("Answer F1 by answer type", "Extractive, abstractive, yes/no, unanswerable",
       "Shows where a system is weak. The types behave differently (a yes/no answer is 0 or 1).",
       "The same F1, grouped by the type of the reference answer that gave the maximum."),
      ("Answer length", "All questions",
       "Token F1 gives a low score to long answers. Use length to read F1 differences.",
       "Median and maximum words per answer. Also a count of answers that say \"Unanswerable\"."),
      ("Evidence F1", "Not used",
       "Answer-only pilot: the systems do not return paragraph IDs in the gold format.",
       "Not calculated (the evaluator input has empty evidence)."),
      ]),
    ("EnterpriseRAG-Bench · metrics-based",
     "Official metrics_based_eval.py at commit d36685e, unchanged, default settings. Judge gpt-5.4 (gpt-5-mini only "
     "for JSON recovery). Each system is scored alone; the leaderboard Space's transform_raw_data.py makes the rows.",
     [("Overall score", "All questions (headline, leaderboard column)",
       "One number that needs a correct answer and rewards a complete one. The public leaderboard sorts by it.",
       "Per question: completeness if the answer is correct, else 0. Mean over the scored questions. The official scorer "
       "skips a question with no answer and no documents; the report also shows the score with such a question as 0."),
      ("Correctness", "All questions",
       "Does the answer agree with the gold answer as a whole (no wrong or conflicting claim)?",
       "One judge verdict (true or false) per answer against the question and the gold answer. A judge failure gives "
       "false. A question without a gold answer counts as correct."),
      ("Completeness", "All questions",
       "How much of the needed information the answer has.",
       "The judge checks each gold fact alone against the answer. Score = facts found / all facts. No facts = 100; "
       "a judge failure on any fact gives 0."),
      ("Recall", "Questions with gold documents",
       "Did the system find the documents that have the answer? Needs the document IDs that the system used.",
       "Gold documents in the system's document list / all gold documents."),
      ("Invalid extra docs", "Questions with gold documents",
       "Shows a system that returns many documents to raise its recall. Lower is better; it is a count, not 0–100.",
       "Number of returned documents that are not gold and not marked \"valid\" (relevant) for the question."),
      ("Document correction", "Before scoring (official default)",
       "The gold lists are not perfect. A document that a system found can have the answer too.",
       "Three judges read each returned document that is not gold. When all agree that it has the answer, it becomes "
       "gold for that system and the gold answer can get new facts. The report counts the corrected questions."),
      ]),
    ("4Minds RAG · our metrics on saved answers",
     "pipeline/score_extra.py on the saved EnterpriseRAG-Bench pilot answers (the systems do not answer again). "
     "Two versions with the same settings: judge gpt-4o-mini (v1) and Claude Haiku 5.5, thinking disabled (v2). "
     "References: the EnterpriseRAG-Bench gold answer, gold facts and gold documents.",
     [("Answer Accuracy (RAGAS, NVIDIA)", "All questions (headline)",
       "One overall number for \"does the answer agree with the gold answer\". Two ratings make it less dependent on one judge reply.",
       "The judge rates the answer against the gold answer as 0, 2 or 4, then again with the two roles swapped. "
       "Score = mean of the two ratings / 4."),
      ("Factual Correctness (RAGAS): precision, recall, F1", "All questions (F1 is headline)",
       "Counts claims, so it shows if an answer is wrong (precision) or incomplete (recall).",
       "The judge splits the answer into claims and checks each against the gold answer (TP or FP); then it splits the gold "
       "answer and checks each against the answer (FN if not found). Precision = TP / (TP + FP), recall = TP / (TP + FN), "
       "F1 from the two (atomicity and coverage \"low\")."),
      ("Summarization (DeepEval): score, alignment, coverage", "All questions (score is headline)",
       "Shows if the answer covers the gold facts without statements that the facts do not support.",
       "The original text is the gold facts. Alignment = answer claims that the facts support / all answer claims "
       "(0 if the answer has no claims). Coverage: 5 yes/no questions made from the facts (once per question, the same "
       "for all systems); of the questions that the facts answer \"yes\", the share that the answer also answers \"yes\". "
       "Score = min(alignment, coverage)."),
      ("Hallucination (DeepEval)", "All questions (headline)",
       "Does the answer contradict a gold fact? Higher is better here.",
       "The judge gives \"yes\" (agrees) or \"no\" for each gold fact. Score = \"yes\" / all facts. The prompt says that "
       "missing detail is not a contradiction, but the judges usually give \"no\" to a non-answer (\"the documents do not "
       "have this\"), so \"I don't know\" usually scores 0. Read it with Answer Accuracy."),
      ("Document retrieval: precision, recall, F1", "Questions with gold documents (F1 is headline)",
       "Did the system find the right documents, and how many wrong ones did it give? No judge, so it is repeatable.",
       "Exact match of the document IDs that the system gave against the original gold IDs (no correction). "
       "Precision = hits / documents given (0 if none), recall = hits / gold documents, F1 = 2PR / (P + R)."),
      ]),
]

SHARED = [
    ("95% confidence interval", "Pilot samples are small (10 and 25 questions). The interval shows how sure a mean is.",
     "Bootstrap of the per-question scores: GraphRAG-Bench and EnterpriseRAG-Bench 2,000 resamples (seed 7), "
     "QASPER 10,000 (seed 0). "
     "GraphRAG-Bench also has a paired bootstrap for 4Minds minus each system on the same questions."),
    ("Latency (median, p90)", "Speed is part of the product comparison. The median is not changed by a few slow calls.",
     "Client wall-clock time from request to full answer, per answered question. p90 = the value that 90% of calls are below."),
    ("Answered, failed, \"I don't know\"", "A system that fails or refuses must not look better than it is.",
     "Counts from the run manifest. Failed questions are not in predictions.json, so read these counts next to the "
     "scores. QASPER scoring stops until every question has an answer."),
    ("Tokens and estimated cost", "Cost per question for systems with per-token prices.",
     "Token counts from the API response × list prices. 4Minds is a subscription, so no cost."),
]


def table(rows, header_cells):
    out = ["<div class='card'><table><tr>" + "".join(f"<th>{escape(h)}</th>" for h in header_cells) + "</tr>"]
    for name, *cells in rows:
        out.append(f"<tr><td><strong>{escape(name)}</strong></td>" + "".join(f"<td>{escape(c)}</td>" for c in cells) + "</tr>")
    return "".join(out) + "</table></div>"


def main():
    h = head("Benchmark metrics cheat sheet · 4Minds")
    h.append(header("Benchmark hub"))
    h.append("<div class='label'>Cheat sheet</div><h1>Benchmark metrics</h1>"
             "<p class='lead'>For each benchmark: the metrics, why we use them, and how the scorer calculates them. "
             "All scores are 0–100.</p>")
    for name, scorer, metrics in BENCHMARKS:
        h.append(f"<section><div class='label'>Benchmark</div><h2>{escape(name)}</h2><p class='sub'>{escape(scorer)}</p>")
        h.append(table([(m, f"{used}", why, how) for m, used, why, how in metrics], ["Metric", "Used on", "Why", "How"]))
        h.append("</section>")
    h.append("<section><div class='label'>All benchmarks</div><h2>Statistics and run data</h2>"
             "<p class='sub'>The same for every benchmark. From the aggregator and the run manifests.</p>")
    h.append(table(SHARED, ["Item", "Why", "How"]))
    h.append("</section></div></body></html>")
    OUT.write_text("\n".join(h))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

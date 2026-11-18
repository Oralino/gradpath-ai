# EVALUATION.md
What is measured, with which datasets, and the measured results. Only real results go here, with the
date, the configuration and the dataset version. Design is in `ARCHITECTURE.md`.

## Datasets (in `evaluation/`, not created yet)
| File | Contents | Size |
|---|---|---|
| `retrieval_questions.jsonl` | Questions with expected relevant documents or chunks | 30–50 |
| `route_cases.jsonl` | Requests labelled `traditional_rag` or `agentic_workflow` | TBD |
| `workflow_cases.jsonl` | JD + sample profile cases with expected outputs | TBD |

Datasets may also be uploaded to LangSmith for side-by-side experiment views; the files here are the
source.

## Metrics
- **Retrieval:** Recall@K, Precision@K, MRR, latency.
- **Answers:** faithfulness to evidence, relevance, citation accuracy, unsupported-claim rate, correct
  abstention.
- **Routing:** accuracy, precision and recall for `agentic_workflow`, simple queries over-routed,
  complex queries under-routed, latency and cost per route, fallback rate and success.
- **Workflow:** valid structured outputs, all steps completed, missing-information handling, recovery
  from tool errors, revision-loop termination.

## Experiments
1. Chunk size and overlap.
2. Semantic vs hybrid retrieval.
3. With and without reranking.
4. Adaptive routing vs always-RAG vs always-agentic.
5. Prompt and structured-output variants.

## Results

### Threshold probe (informal, 2026-11-17)
Not a formal evaluation (8 hand-picked questions, no labels); used to set a provisional
`retrieval_min_score` until the labelled set exists (Milestone 2).

Config: `voyage-4`, chunk 1200 / overlap 150, semantic search, 956 chunks, top-3.

| Group | Questions | Best cosine score per question | Right source ranked first |
|---|---|---|---|
| Covered by the corpus | 5 (index, HTTP 404, merge conflict, behavioural interviews, config/API keys) | 0.591 – 0.681 | 5 / 5 |
| Not covered | 3 (sourdough, capital of Australia, security clearance) | 0.271 – 0.392 | n/a |

Decision: `retrieval_min_score = 0.45` (0.06 above the highest uncovered score, 0.14 below the
lowest covered one). Re-check with the labelled set.

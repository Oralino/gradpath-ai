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
None yet.

# EVALUATION.md
What is measured, with which datasets, and the measured results. Only real results go here, with the
date, the configuration and the dataset version. Design is in `ARCHITECTURE.md`.

## Datasets (in `evaluation/`)
| File | Contents | Size |
|---|---|---|
| `retrieval_questions.jsonl` | Questions with their relevant pages or sections (v1, 2026-11-18) | 40 (30 covered, 10 uncovered) |
| `route_cases.jsonl` | Requests labelled `traditional_rag` or `agentic_workflow` | TBD |
| `workflow_cases.jsonl` | JD + sample profile cases with expected outputs | TBD |

Datasets may also be uploaded to LangSmith for side-by-side experiment views; the files here are the
source.

## Retrieval dataset format (`retrieval_questions.jsonl`, v1)
One JSON object per line:

| Field | Meaning |
|---|---|
| `id` | `q-001` ... stable, never reused |
| `question` | What a user would type |
| `covered` | `true` if the corpus answers it; `false` means search should return `insufficient` |
| `relevant` | Targets: `{document_id, page, section?}`. `page` is the chunk's `source_url`; `section` is one heading from the chunk's section path. Empty for uncovered questions |
| `tags` | For slicing results: `exact_term`, `acronym`, `number`, `paraphrase`, `multi_source`, `how_to`, `concept`, `interview`, `career`, `security`, `job_requirement`, `near_domain`, `off_domain` |
| `notes` | Why the question is there, when it matters |

**Matching rule:** a retrieved chunk is relevant if its `document_id` and `source_url` match a
target and, when the target names a `section`, that heading is one of the components of the
chunk's `section` path (split on ` > `). Labels name pages and headings, never chunk ids: chunk
ids (`doc:page:n`) change when chunk size changes, and chunk size is a Milestone 5 experiment.
Sections are needed because two sources are single huge pages (System Design Primer, 168
chunks; Azure REST guidelines, 117 chunks), where a page-level label would count almost
anything as relevant.

**Metric definitions** (per covered question, then averaged):
- **Recall@K:** share of the question's targets with at least one matching chunk in the top K.
- **Precision@K:** share of the top K chunks that match any target.
- **MRR:** 1 / rank of the first matching chunk (0 if none in the top K).
- **Abstention:** for uncovered questions, the share that come back `insufficient`; for covered
  ones, the share that wrongly do.

All 34 targets were checked against `knowledge_base/processed/` when v1 was written: each matches
1–35 chunks.

## Cases noted for the labelled set
- "What is a database index and when should I use one?" -> should also retrieve
  `db-postgres-indexes` page `indexes-multicolumn` (missed from the top 5 on 2026-11-17).
  In v1 as `q-001`.

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

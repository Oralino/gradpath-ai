# EVALUATION.md
What is measured, with which datasets, and the measured results. Only real results go here, with the
date, the configuration and the dataset version. Design is in `ARCHITECTURE.md`.

## Datasets (in `evaluation/`)
| File | Contents | Size |
|---|---|---|
| `retrieval_questions.jsonl` | Questions with their relevant pages or sections (v1.1, 2026-11-18) | 40 (31 covered, 9 uncovered) |
| `route_cases.jsonl` | Requests labelled `traditional_rag` or `agentic_workflow` | TBD |
| `workflow_cases.jsonl` | JD + sample profile cases with expected outputs | TBD |

Datasets may also be uploaded to LangSmith for side-by-side experiment views; the files here are the
source.

## Retrieval dataset format (`retrieval_questions.jsonl`, v1.1)
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

All targets were checked against `knowledge_base/processed/` when v1 was written: each matches
1–35 chunks. The loader refuses unknown fields, empty sections and duplicate targets, so a label
typo can't silently widen a target to the whole page.

**Versions:** v1 (2026-11-18): 30 covered, 10 uncovered. v1.1 (same day): `q-035` (CORS) relabelled
covered after the first run showed MDN's "Relaxing the origin constraint" paragraph answers it in
part; tag `partial`. A factual labelling error, fixed before any baseline was recorded.

**Runner:** `uv run python -m gradpath.evaluation.retrieval_eval` (from `backend/`, API stopped).
Embeds all questions in one Voyage call, searches the raw top-K with no threshold (ranking metrics
are threshold-independent), then judges the threshold from each question's best score. Prints
markdown tables and saves the full per-question JSON to `evaluation/results/`.

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
lowest covered one). Re-checked with the labelled set below.

### Retrieval baseline (2026-11-18, dataset v1.1)
Config: `voyage-4`, chunk 1200 / overlap 150, semantic search (cosine), 956 chunks, no per-document
cap, threshold 0.45. Full results: `evaluation/results/retrieval-20261118-051615.json`.
31 covered + 9 uncovered questions.

| K | Recall@K | Precision@K | MRR@K | Recall@K after threshold |
|---|---|---|---|---|
| 1 | 0.903 | 0.968 | 0.968 | 0.903 |
| 3 | 0.952 | 0.753 | 0.984 | 0.952 |
| 5 | 0.968 | 0.645 | 0.984 | 0.968 |
| 10 | 1.000 | 0.494 | 0.984 | 1.000 |

Latency: 0.66 s to embed all 40 questions (one Voyage call); 3.3 ms per question for the vector
search (local Qdrant).

**Threshold re-check:**

| Threshold | Covered kept | Uncovered rejected |
|---|---|---|
| 0.40 | 100% | 89% |
| **0.45** | **100%** | **100%** |
| 0.50 | 100% | 100% |
| 0.55 | 94% | 100% |
| 0.60 | 81% | 100% |

Lowest covered best score 0.526 (`q-011`, retrying a POST without saying "idempotency"); highest
uncovered 0.401. 0.45 keeps every covered question and rejects every uncovered one, so it stays.
The gap is narrower than the probe suggested (0.13, not 0.20): near-domain questions score higher
than off-topic ones.

**Misses at K = 5** (both found their first target at rank 1):
- `q-001` database index: the PostgreSQL multicolumn page is at rank 7; SQLite query-planner
  chunks take ranks 3, 5, 6. Same miss as Milestone 1; a reranking candidate.
- `q-027` what a developer does: BLS chunks fill the top 5; O\*NET "Tasks" is at ranks 8–9.
  O\*NET's summary chunk (rank 4) also describes the job but isn't labelled; a judgement call,
  left as is rather than relabelled after seeing results.

**How to read this:** recall is high partly because the questions were written while reading
the source headings, so their wording is close to the sources (a known bias of hand-written sets).
Precision@5 of 0.65 mostly reflects single-target questions whose top 5 includes neighbouring
pages. With 31 covered questions, one question is about 3 recall points: differences smaller than
that are noise. The weakest slices are `multi_source` (0.75) and `career` (0.83).

# EVALUATION.md
What is measured, with which datasets, and the measured results. Only real results go here, with the
date, the configuration and the dataset version. Design is in `ARCHITECTURE.md`.

## Datasets (in `evaluation/`)
| File | Contents | Size |
|---|---|---|
| `retrieval_questions.jsonl` | Questions with their relevant pages or sections (v1.3, 2026-11-19) | 50 (38 covered, 12 uncovered) |
| `routing_cases.jsonl` | Requests labelled with the expected route and action (run, needs input, unsupported), tagged; owner-approved 2026-11-18 | 30 |
| `workflow_cases.jsonl` | JD + sample profile cases with expected behaviour, scored in code (2026-11-18) | 4 |
| `answer_cases.jsonl` | Questions with must-contain fact groups (any phrasing per group, from the indexed passage named in `source`) or `expect: refuse`; owner-approved 2026-11-21 | 20 (14 answer, 6 refuse) |
| `profiles/sample_*.json` | Fictional profiles: new grad (demos, tests, traces), sparse, injection | 3 |
| `job_descriptions/sample_backend_new_grad.txt` | Fictional new-grad backend posting (the real one stays in `private/`) | 1 |

Datasets may also be uploaded to LangSmith for side-by-side experiment views; the files here are the
source.

## Retrieval dataset format (`retrieval_questions.jsonl`, v1.3)
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
v1.2 (2026-11-19, owner approved, T-009): `q-030` points at the OWASP page's new address
(`api-security.owasp.org`, same page); `q-034` (CI/CD with GitHub Actions) relabelled covered by the
new GitHub Docs pages. `q-031` (Kubernetes liveness probes) stays uncovered: the new pages mention
liveness only in passing.
v1.3 (2026-11-19, owner approved, T-010): 10 questions added so hybrid search can be measured
fairly (the 7 v1.2 `exact_term` questions already scored Recall@5 1.0). Six covered exact-term
questions (`q-041` SQLSTATE 40001, `q-042` BRIN, `q-043` maxSurge/maxUnavailable, `q-044`
basic.nack, `q-045` LLM08, `q-046` tmp_path), each term checked to appear in the labelled
section; four near-topic uncovered questions (`q-047` SKIP LOCKED, `q-048` Dockerfile HEALTHCHECK,
`q-049` workflow_dispatch, `q-050` Kafka consumer-group rebalancing), whose key terms appear in
no chunk while their topics are indexed.

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

### Workflow: first real run (2026-11-18, step 6 of T-003)
One run, not an evaluation: it shows the workflow works end to end on real models and shows what
to measure. Config: `LLM_PROVIDER=claude_code` (Pro plan; Haiku 5.5 fast, Sonnet 5.5 smart),
`WORKFLOW_MAX_REVISIONS=1`, retrieval k=3 (max 2 per document), threshold 0.45, tracing off.
Input: the fictional sample posting and profile (`evaluation/job_descriptions/`,
`evaluation/profiles/`). Full output: `evaluation/results/workflow-20261118-014953.json`.

| Measure | Result |
|---|---|
| Status | `complete` after 1 revision (the first plan was revised once; its critique isn't recorded) |
| Time | 101 s end to end (CLI wall clock) |
| Requirements extracted | 18 (17 studyable, 1 eligibility) |
| Gaps | 7 demonstrated, 4 partially evidenced, 6 not yet evidenced, 1 not applicable |
| Roadmap | 10 items (the cap), 47 h estimated against a 48 h budget (8 h x 6 weeks) |
| Items with sources | 6 of 10; the 4 without are PostgreSQL, Docker, monitoring, cloud |
| Interview questions | 10, each tied to a not-yet or partially evidenced requirement |
| Nodes | job + profile -> retrieve -> gaps -> questions + roadmap -> evaluate -> revise -> evaluate -> finalize |

What it showed:
- **A false "no source" claim:** PostgreSQL (`r-4`) had three relevant chunks retrieved
  (`db-postgres-indexes`, `db-postgres-mvcc`), yet Sonnet cited none and wrote that the knowledge
  base has no source for it. The `no_resources` check flags this kind of item, but the result
  dropped minor issues whenever the critic passed; fixed (minor issues are now kept).
  Docker, monitoring and cloud really aren't covered (known corpus gaps), so those three are right.
- **The same section cited twice** (two chunks of one section in items 7 and 8); fixed by citing
  each section once.
- **Generous "demonstrated" calls:** "Automated testing (unit and integration)" is demonstrated
  although its own reasoning says integration testing isn't shown; data structures counts a
  course plus "search modules". A calibration question for the workflow evaluation.
- Roadmap exercises sometimes tell the student to use official documentation where the corpus
  has nothing: honest, and no URL is invented, but it is outside the cited sources.
- Claude Code under-reports tokens, so no cost figure (API mode needed).

### Workflow evaluation (2026-11-18, cases v1)
Runner: `uv run python -m gradpath.evaluation.workflow_eval` (from `backend/`, API stopped); a
saved run is re-scored for free with `--rescore <file>`. Config as the first real run (Claude Code,
Haiku 5.5 / Sonnet 5.5, 1 revision, k=3, threshold 0.45). Output:
`evaluation/results/workflow-eval-20261118-070716.json` (re-scored with the post-review checks:
same result). About 26 model calls and 4 Voyage requests in total.

Checks per case (all code, no LLM judge): not partial; loop ended within the limit; expected gap
statuses; required gaps all in the roadmap; every citation retrieved for its own requirement;
budget respected or flagged; share of "demonstrated" under a cap.

| Case | What it tests | Passed | Status | Demonstrated | Items | Effort / budget | Time |
|---|---|---|---|---|---|---|---|
| wf-001 | Baseline (sample profile) | yes | complete_with_limitations | 44% | 7 | 44 / 48 h | 72 s |
| wf-002 | Correction "I wrote PostgreSQL queries..." | yes | complete | 25% | 10 | 47 / 48 h | 91 s |
| wf-003 | Sparse profile, 20 h budget | yes | complete | 7% | 10 | 17 / 20 h | 108 s |
| wf-004 | Prompt injection in a project description | yes | complete | 35% | 10 | 48 / 48 h | 92 s |

All 8 checks passed on all 4 cases (11/11 gap expectations). What it shows:
- **Corrections are capped as designed:** in wf-002 PostgreSQL rose to "partially evidenced",
  citing `c-1` only, not to "demonstrated".
- **The injection had no visible effect:** wf-004 rated 35% demonstrated (baseline 44%; run-to-run
  variation is large), Docker stayed "not yet evidenced". One case, so this is a check that held,
  not a robustness rate.
- **Every first plan was revised** (4/4 used their one revision). The critic is doing work, but it
  also means every run costs an extra Sonnet + Haiku call; worth measuring which check fires.
- **wf-001 ended `complete_with_limitations`:** Haiku still found an unsupported item after the
  revision, and the result says so instead of claiming complete.
- **The false "no source" claim recurred:** wf-004 has 2 items without a source although the
  knowledge base had evidence (PostgreSQL basics again, as in the first real run). The
  `no_resources` issue reports it (minor). Candidate fix for later: make it blocking, or tell the
  roadmap prompt to cite listed evidence when it exists.
- **Haiku's critic is chatty:** 3-5 minor `unsupported_item` notes per complete run.
- **Extraction varies:** 16-18 requirements for the same posting across runs (Milestone 1 saw
  20-24 on the real posting).
- Limits: 4 cases, one posting, fictional profiles; behaviour checks, not accuracy numbers.

### Retrieval re-check (2026-11-18, release check for Milestone 3)
Same dataset (v1.1) and index as the baseline: Recall@5 0.968, Precision@5 0.645, MRR 0.984;
threshold 0.45 keeps 100% covered and rejects 100% uncovered; same two misses (`q-001`, `q-027`).
Unchanged, as expected (Milestone 3 didn't touch retrieval; the T-005 index changes apply at the
next ingest). Output: `evaluation/results/retrieval-20261118-070803.json`.

### Routing evaluation (2026-11-18, labels v1, T-006)
30 owner-approved labelled requests (`evaluation/routing_cases.jsonl`), run with
`gradpath.evaluation.routing_eval` on the Pro plan (Haiku 5.5 through Claude Code).
Outputs: `evaluation/results/routing-rules-20261118-211733.json` (rules only, free) and
`routing-20261118-211756.json` (rules + Haiku).

| Metric | Rules only | Rules + Haiku |
|---|---|---|
| Decided | 10 / 30 | 30 / 30 |
| Accuracy (route and action) | 10/10 | 30/30 |
| Workflow precision / recall | 1.0 / 1.0 | 1.0 / 1.0 |
| Simple over-routed / complex under-routed | 0 / 0 | 0 / 0 |
| Injection (3) / borderline (8) / missing input (5) / unsupported (3) | n/a | all correct |
| Mean routing call | 0 s | 2.2 s (Haiku cases only) |

What it shows and what it doesn't:
- The rules took a third of the requests for free and never disagreed with a label; Haiku got
  every case the rules left open, including "Am I ready to apply?", "What is Docker?" with a job
  and profile attached, and the three injection attempts.
- **Bias:** the labels and the router prompt were written in the same session, by the same
  author, with the spec's own examples; 30/30 says the router matches its designer's intent on
  these requests, not that it generalises. Next: labels written by someone else, more
  phrasings per kind, and real requests from the route log once the app is used.
- One run; model decisions can vary between runs.

### Adaptive vs always-RAG vs always-workflow (2026-11-18, T-006)
`gradpath.evaluation.routing_compare` on 4 labelled requests (owner decision: 4, for plan quota):
rt-001 "What is a REST API?", rt-017 "What is Docker?" (job and profile attached), rt-011 the
spec's roadmap request, rt-016 "Am I ready to apply?". Each path ran once per request and was
reused by every strategy that takes it. "Served" is decided in code: a RAG-labelled request needs
a cited answer or an honest "not covered"; a workflow-labelled request needs a complete workflow
result. Output: `evaluation/results/routing-compare-20261118-211849.json`.

| Strategy | Served | Served, strict* | Time (total) | Model calls (total) |
|---|---|---|---|---|
| Adaptive (router) | 4/4 | 3/4 | 177 s | 15 |
| Always RAG | 2/4 | 1/4 | 11 s | 2 |
| Always workflow | 2/4 | 2/4 | 320 s** | 21** |

*strict: an honest "not covered" on a topic a new grad would expect covered (Docker) counts as
not served. **rt-001 couldn't run at all, so these totals leave out its cost; model calls are
chat-model calls through the two model instances (a retry counts twice).

| Request | Adaptive | Always RAG | Always workflow |
|---|---|---|---|
| rt-001 REST API | RAG, 3 citations, 6 s | same | can't run (no job or profile) |
| rt-017 What is Docker? | RAG abstained ("not covered"), 0.1 s, no model call | same | 149 s, 7 calls, a full plan that doesn't answer the question |
| rt-011 roadmap | workflow, complete with limitations, 87 s | abstained after one model call (4 s): the retrieved text didn't answer a personal request | same as adaptive |
| rt-016 ready to apply? | workflow, complete, 84 s | abstained before any model call: nothing above the threshold | same as adaptive |

What it shows:
- Adaptive served every request at about half the time and three quarters of the calls of
  always-workflow, which also failed both simple questions. Always-RAG is cheapest but can't
  answer personal requests: it searches the request text, which isn't about a topic (rt-016 found
  nothing above the threshold; rt-011 found text, and the model said it didn't answer the request).
- All four were decided by the rules (from the routing run; the comparison recorded 0 routing
  calls), so the adaptive column has no routing-call cost; a
  Haiku-routed request adds about 2 s and one call.
- **"What is Docker?" isn't in the knowledge base** (a known corpus gap, TASKS.md); the RAG path
  said so without calling the model. That counts as served (honest), not as strictly served.
- Limits: 4 requests, one run, "served" is a code check of the outcome type, not answer quality.

### Retrieval re-check (2026-11-18, release check for Milestone 4)
Unchanged: Recall@5 0.968, Precision@5 0.645, MRR 0.984; threshold 0.45 keeps 100% covered and
rejects 100% uncovered; same two misses. Milestone 4 didn't touch retrieval (T-008 changes only
prompt text). Output: `evaluation/results/retrieval-20261118-212457.json`.

### Retrieval on corpus v2 (2026-11-19, dataset v1.2, T-009)
After adding 10 sources (1,592 chunks, from 956). Output:
`evaluation/results/retrieval-20261119-024443.json` (an earlier run the same night on labels v1.1,
`retrieval-20261119-013649.json`, showed why the labels had to change: q-030's page had moved and
q-034 was now covered).

| Metric | Corpus v1, labels v1.1 | Corpus v2, labels v1.2 |
|---|---|---|
| Recall@5 | 0.968 | 0.953 |
| Precision@5 | 0.645 | 0.631 |
| MRR | 0.984 | 0.984 |
| Covered kept at 0.45 | 100% | 100% |
| Uncovered rejected at 0.45 | 100% (9/9) | 88% (7/8) |
| Lowest covered / highest uncovered best score | 0.526 / 0.401 | 0.526 / 0.520 |

What it shows:
- The 31 original covered questions score as before (same two misses, `q-001`, `q-027`); the
  recall change is the new `q-034`, which found one of its two labelled pages in the top 5.
- **The threshold's safety margin is gone:** `q-031` (Kubernetes liveness probes, not covered)
  now scores 0.520 against nearby Kubernetes text, just under the lowest covered question
  (0.526). A larger corpus puts near-topic text close to every question; a fixed cosine
  threshold separates "covered" from "nearby" less well. Candidate for Milestone 5: reranking
  scores, or a threshold tuned on more uncovered questions.
- Limits: 40 questions, one run.

### Semantic baseline on labels v1.3 (2026-11-19, T-010)
Semantic-only, the reference for Milestone 5. Same index as above (corpus v2, 1,592 chunks), labels
v1.3 (50 questions: 38 covered, 12 uncovered). Output:
`evaluation/results/retrieval-20261119-062918.json`.

| Metric | Labels v1.2 (40) | Labels v1.3 (50) |
|---|---|---|
| Recall@5 | 0.953 | 0.961 |
| Precision@5 | 0.631 | 0.605 |
| MRR | 0.984 | 0.987 |
| exact_term Recall@5 | 1.000 (7) | 1.000 (13) |
| Covered kept at 0.45 | 100% | 97% (`q-041` 0.393) |
| Uncovered rejected at 0.45 | 88% (7/8) | 67% (8/12) |
| Lowest covered / highest uncovered best score | 0.526 / 0.520 | 0.393 / 0.589 |
| Search per question / batched embedding | 3.4 ms / 2.0 s | 3.6 ms / 0.5 s |

What it shows:
- **All six new exact-term questions rank their labelled section first** (best scores 0.39-0.67):
  Voyage's embeddings handle codes and identifiers here, so there is little ranking left for keyword
  search to win. The same three misses as v1.2 remain (`q-001`, `q-027`, `q-034`, each with one of
  two targets outside the top 5).
- **The threshold is the real weakness.** Three of the four new near-topic uncovered questions
  clear 0.45 (`q-049` workflow_dispatch 0.589, `q-050` Kafka consumer groups 0.538, `q-047` SKIP
  LOCKED 0.488; `q-048` HEALTHCHECK is rejected at 0.415), and `q-041` (SQLSTATE 40001) is found at
  rank 1 but scores 0.393, so it would be answered "not covered". No cosine threshold separates the
  two groups (the sweep: 0.55 keeps 92% and rejects 92%). Milestone 5's main test is therefore
  whether a reranker score is a better abstention signal.
- Limits: 50 questions, one run; labels written by the same author as the system.

### Experiment 3: reranking (2026-11-19, labels v1.3, T-010)
Local cross-encoders (fastembed, ONNX on the owner's CPU, no API) rerank the semantic top 10 or 20;
ranking and abstention are then judged on the reranker's score (sigmoid of its logit, 0..1). One
Voyage call per run; semantic column from the same call. Outputs:
`evaluation/results/retrieval-rerank-20261119-063851.json` (MiniLM) and
`retrieval-rerank-20261119-064221.json` (bge).

| Metric | Semantic | MiniLM-L-6 @10 | MiniLM-L-6 @20 | bge-reranker-base @10 | bge @20 |
|---|---|---|---|---|---|
| Recall@5 | 0.961 | 0.921 | 0.921 | 0.961 | 0.961 |
| Precision@5 | 0.605 | 0.547 | 0.542 | 0.542 | 0.495 |
| MRR@5 | 0.987 | 0.904 | 0.873 | 0.921 | 0.899 |
| Threshold | 0.45 | 0.5 | 0.5 | 0.5 | 0.5 |
| Covered kept / uncovered rejected | 97% / 67% | 95% / 75% | 95% / 75% | 79% / 83% | 79% / 83% |
| Best trade-off in the sweep | 92% / 92% at 0.55 | 95% / 75% at 0.5 | 95% / 75% at 0.5 | 89% / 83% at 0.2 | similar |
| Rerank ms per question p50 / p95 | - | 94 / 198 | 266 / 414 | 660 / 986 | 1503 / 2344 |

What it shows:
- **Neither reranker helps.** Both lower MRR and precision; MiniLM also loses recall (`q-014`
  12-factor config and `q-035` CORS fall out of the top 5: their correct chunks score 0.001-0.07).
  bge keeps recall but reorders first-rank hits downwards.
- **Neither fixes abstention.** Both are very confident on near-topic text that doesn't answer the
  question: `q-049` workflow_dispatch 0.999 / 0.996 (a GitHub Actions "Events" chunk that says a
  workflow can be run "manually"), `q-047` SKIP LOCKED 0.985 with MiniLM (a Serializable-isolation
  chunk about locks). bge rejects more uncovered questions only by also rejecting 8 covered ones
  (`q-001`, `q-008`, `q-014`, `q-035` under 0.02). No reranker threshold beats the best cosine
  threshold (0.55: 92% / 92%).
- **Latency:** only MiniLM @10 fits the +300 ms budget; bge is 2-8x over it.
- Why, probably: the MS MARCO models were trained on short web passages and questions; our chunks are
  ~1,200-character Markdown sections with headings, lists and code, and many questions are "how do
  I" questions where a topical chunk looks like an answer. Not tested further.
- Decision (pending the owner): don't add a reranker to the retrieval service. Limits: 50
  questions, one run each, two models.

### Experiment 2: semantic vs hybrid (BM25 + RRF) (2026-11-19, labels v1.3, T-010)
BM25 from fastembed `Qdrant/bm25` (stemmed, stopwords removed, mean chunk length 77.4 kept
tokens), IDF applied by Qdrant, in an in-memory index over the same 1,592 processed chunks (the
real index untouched). Hybrid = our RRF (k=60, equal weights) of the semantic top 20 and the BM25
top 20. Every returned chunk keeps its cosine score (looked up for BM25-only chunks), so the 0.45
threshold means the same in all three columns. One Voyage call. Output:
`evaluation/results/retrieval-hybrid-20261119-065311.json`.

| Metric | Semantic | BM25 only | Hybrid (RRF) |
|---|---|---|---|
| Recall@5 | **0.961** | 0.855 | 0.921 |
| Precision@5 | **0.605** | 0.437 | 0.521 |
| MRR@5 | **0.987** | 0.755 | 0.914 |
| exact_term Recall@5 | 1.000 | 1.000 | 1.000 |
| Covered kept / uncovered rejected at 0.45 | 97% / 67% | 95% / 67% | 97% / 67% |
| Added ms per question p50 / p95 | - | - | 11 / 15 |

What it shows:
- **Hybrid doesn't help on this corpus.** It fixes none of semantic's three misses (`q-001`,
  `q-027`, `q-034`), adds two (`q-002` loses its SQLite target; `q-035` CORS drops to rank 7,
  BM25 finds no labelled chunk for it), and pushes some first hits down (`q-043` to rank 2).
- **Exact terms were never semantic's weakness here:** all 13 exact-term questions rank their
  target first with Voyage embeddings alone; BM25 alone gets them too but ranks `q-045` (LLM08)
  third. The textbook case for hybrid search (codes and identifiers lost by embeddings) doesn't
  show up with `voyage-3.5` on this corpus.
- **Abstention is unchanged,** as designed: hybrid only reorders, and the best cosine score
  among returned chunks stays the same.
- It is cheap (11-15 ms), so cost isn't the reason to drop it; the numbers are. Not tried: RRF
  weights favouring dense, or other k values; tuning them on 38 covered questions would fit noise,
  and the best they could do is match semantic.
- Limits: 50 questions, one run; BM25 parameters fastembed's defaults (k1 1.2, b 0.75).

### Answer-step abstention on near-topic questions (2026-11-19, T-010 follow-up)
Milestone 5 found no retrieval-side fix for the four near-topic uncovered questions that clear the
0.45 threshold, so this checks the next safety net: does the RAG answer (`rag.answer_question`,
Sonnet via Claude Code on the owner's plan) refuse or admit the gap? Plus one covered control.
One run each from the owner's terminal. Output: `evaluation/results/answer-abstention-20261119.json`.

| Question | Best cosine | Status | What the answer did |
|---|---|---|---|
| `q-047` SKIP LOCKED | 0.488 | insufficient_evidence | Refused (model judged evidence insufficient) |
| `q-050` Kafka consumer-group rebalancing | 0.538 | insufficient_evidence | Refused |
| `q-031` Kubernetes liveness probes | 0.521 | answered | Opens with "the evidence doesn't cover how to configure liveness probes, so this is only a partial answer"; gives only cited facts (what a probe is, the three probe actions) and says what is missing |
| `q-049` workflow_dispatch | 0.589 | answered | Says the evidence "doesn't explain how to use `workflow_dispatch`"; gives the cited fact that workflows can be triggered manually, names what is missing, points to the linked reference |
| `q-043` maxSurge / maxUnavailable (covered control) | 0.650 | answered | Full, correct answer with 3 citations |

What it shows:
- **No invented answer in 4/4:** the answer step is a working safety net where the threshold isn't.
  Two refusals, two honest partial answers whose every claim comes from a cited chunk.
- **The gap is in how the result is labelled, not in what it says:** the two partial answers have
  status `answered`, the same as a full answer. A user skimming the UI, or a caller reading only
  `status`, would miss the caveat. Follow-up for Milestone 6 (TASKS.md): show partial answers as
  partial.
- The control still answers fully, so the model isn't refusing everything near the threshold.
- Limits: 5 questions, one run, judged by reading; Sonnet answers can vary between runs.


### Retrieval re-check (2026-11-20, release check for Milestone 6)
Unchanged from the labels v1.3 semantic baseline (same index: corpus v2, 1,592 chunks; dataset
sha `b996e8eb7684`): Recall@5 0.961, Precision@5 0.605, MRR 0.987; at 0.45, 97% of covered
questions kept (`q-041` 0.393) and 67% of uncovered rejected (`q-031`, `q-047`, `q-049`, `q-050`
clear it); the same three partial misses (`q-001`, `q-027`, `q-034`). Milestone 6 changed the
frontend and the API around retrieval, not retrieval itself (T-015 rewrites citation URLs after
search). One batched Voyage call (1.5 s). Output: `evaluation/results/retrieval-20261120-073033.json`.

### Answer eval and grounding check (2026-11-21, cases v1, T-018 step 10)
`answer_eval` runs `rag.answer_question` (Sonnet via Claude Code on the owner's plan) on 20 cases,
then a grounding check (`evaluation/grounding.py`: Haiku splits each shown answer into claims and
marks each supported or not by the chunks it cites; the arithmetic is in code). Scored in code:
an answer case passes when it is `answered` or `partial`, cites something and contains every fact
group (case-insensitive, whole words); a refuse case passes when it refuses, or when it shows a
partial answer whose claims are all supported. One run from the owner's terminal, 24 s per case.
Output: `evaluation/results/answer-eval-20261121-0557.json` (`--rescore` re-scores it for free).

| Measure | Result |
|---|---|
| Answer cases passed | 12/14 (86%) |
| Refuse cases passed | 6/6: all refused (`insufficient_evidence`); none grounded-partial, none invented |
| Claims supported by their cited chunk | 159/166 (96%) |
| Mean latency (answer + grounding) | 24.0 s |

The two failures:
- `a-005` (Read Committed vs Repeatable Read): an honest `partial`. Retrieval brought the
  Repeatable Read section but not the Read Committed one, so the answer said Read Committed was
  only implied, and it never mentioned nonrepeatable reads (the missed fact group). A retrieval
  coverage gap, labelled correctly by the answer step.
- `a-013` (SQLSTATE 40001): refused before the model ran: best score 0.392, under the 0.45
  threshold. The same known retrieval miss as `q-041` in every retrieval run (0.393). The safe
  failure: no answer rather than a wrong one.

The 7 unsupported claims (read one by one; the judge's verdict was right each time): all are true
but not stated by the cited chunks. Three are the model's own advice or general knowledge
("EXPLAIN ANALYZE also runs the query", "use cache-aside when data can tolerate staleness",
"slowing down and retrying fits 429"); three in `a-007` name the Repeatability headers, which are
in the corpus (Microsoft API guidelines) but in a chunk the answer did not cite. So the prompt's
"only the evidence" rule holds for facts but not for advice, and citations can be incomplete.

What it shows:
- **Refusal is solid:** 6/6 near-topic gaps refused, consistent with the 2026-11-19 abstention run.
- **Answers are grounded but add advice:** 96% supported; the gaps are recommendations and
  well-known facts, not invented specifics. Worth a prompt change only if the owner wants
  answers stricter than the docs (follow-up, not done here).
- **The weak spot is retrieval, not the model:** both failures trace to what retrieval returned.
- Limits: 20 cases, one run (Sonnet varies between runs), a model judge that can be wrong both
  ways (spot-checked here only on the unsupported verdicts), fact groups matched as phrases (an
  answer can state a fact in words no group lists).

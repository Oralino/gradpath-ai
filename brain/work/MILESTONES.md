# MILESTONES.md
The project's story, milestone by milestone: what we built, why, and what it does, written so the
owner can retell it. Open to-dos are in `TASKS.md`, finished items in `DONE.md`, details and commits
in `tickets/`. Concepts and interview answers are in `../engineering/WALKTHROUGH.md`.

**Status key:** ✅ done · 🔨 in progress · ⏳ planned

## At a glance

| # | Milestone | Status | Goal | What you can show |
|---|---|---|---|---|
| 0 | Project setup | ✅ | Decide the plan, stack and rules before coding | Public repo, `brain/` docs, licence-checked sources |
| 1 | RAG foundation | ✅ | Load sources, answer with citations, analyse a job description | Cited answers, "not covered" answers, 40+ tests |
| 2 | Retrieval evaluation + tracing | ✅ | Measure search quality | Recall@5 0.97, MRR 0.98, threshold checked, LangSmith traces, CI |
| 3 | Agentic workflow | ✅ | Job + profile -> gaps -> roadmap | A LangGraph workflow with a self-check loop; 4/4 workflow eval cases; `POST /api/career/prepare` |
| 4 | Router + fallback | ✅ | Pick the cheapest path that works | 30/30 routing labels; adaptive served 4/4 (3/4 strict) vs 2/4 for always-RAG or always-workflow; labelled fallback; `POST /api/assist` |
| 5 | Hybrid retrieval + reranking | ✅ | Improve search for exact terms | Measured and rejected: semantic 0.961 Recall@5 beat hybrid (0.921) and both rerankers; stays semantic-only |
| 6 | Frontend | ✅ | Make it usable | Next.js app designed from `DESIGN.md` |
| 7 | Demo and live modes | ⏳ | A public site that costs nothing | Recorded demo runs; live mode with a visitor's key |
| 8 | Deploy | ⏳ | A live link | Vercel + Render + Qdrant Cloud (free tiers) |

## Tech stack at a glance

| Layer | Choice | Why this one |
|---|---|---|
| Language / tooling | Python 3.13, uv | Fast installs, one lockfile with exact versions |
| LLM | Claude Haiku 5.5 (fast) + Sonnet 5.5 (smart) | Cheap where the task is simple, stronger where it reasons |
| LLM access | Claude Code on the Pro plan (local), Anthropic API (live mode) | Zero extra cost in development |
| Framework | LangChain (building blocks) + LangGraph (workflow) | Industry-standard skills; our own code for the core logic |
| Embeddings | Voyage `voyage-4` (free tier) | Anthropic's recommended embeddings partner |
| Vector database | Qdrant (local file, then Qdrant Cloud free) | Runs without Docker; supports hybrid search later |
| API | FastAPI + Pydantic | Typed, validated, async |
| Tracing / eval | LangSmith (free plan) + local logs | Visual traces and experiment comparison |
| Frontend | Next.js + Tailwind | Polished UI once the backend is reliable |
| Hosting | Vercel, Render, Qdrant Cloud | All free tiers (owner rule: zero cost) |

---

## Milestone 0: Project setup ✅
*Finished 2026-11-17*

| What we did | Why |
|---|---|
| Turned the original spec into a decided plan in `brain/` (requirements, architecture, evaluation, walkthrough, tasks); archived the spec | Decisions made up front avoid rewrites, and the reasoning stays visible |
| Chose the stack with the owner (table above) | Each choice balances learning value, industry demand and zero cost |
| Created the public GitHub repo, `.gitignore`, `.env.example` | Employers can follow the work; secrets have a safe template |
| Added a pre-commit hook that refuses to commit `.env` files | A second safety net beyond `.gitignore` |
| Picked and licence-checked 18 knowledge-base sources | The app stores and quotes text, so licences must allow it |

**Result:** a public repo and a plan every later step builds on. The Google SRE book is link-only
because its licence forbids derivatives.

---

## Milestone 1: RAG foundation ✅
*Ticket: `tickets/T-001-rag-foundation.md`*

**Goal:** a backend that loads trusted sources, answers focused questions from them with citations,
and analyses a job description, or says when it doesn't know.

| Step | Status | What we built | Why | Result |
|---|---|---|---|---|
| 1. Backend skeleton | ✅ | `uv` project, pinned versions, typed settings from `.env`, ruff, pytest | Pinned versions stop LangChain changes breaking us; one checked place for config | `uv sync`, `uv run pytest` |
| 2. Provider layer | ✅ | `ChatClaudeCode` (custom LangChain model on the Pro plan), `ChatAnthropic`, fake model, `get_chat_model()`, `with_structure()` | No extra cost locally; provider is a config switch; tests are free | Real Pro-plan call returned text and a validated `SQL / Required` result |
| 3. Ingestion pipeline | ✅ | Polite download + cache, cleaning, heading-aware chunking, Voyage embeddings (rate limiter + cache), safe Qdrant rebuild | Search is only as good as its corpus; free-tier limits shaped the design | 18 sources -> 52 pages -> 956 chunks |
| 4. Retrieval service | ✅ | `RetrievalService.search()` returns scored, citable evidence above a threshold | One search path for every feature; "I don't know" built in | 7 tests; real probe found the right source 5/5; threshold set to 0.45 |
| 5. RAG + `POST /api/chat` | ✅ | FastAPI app; answers only from retrieved evidence; citations verified in code; retrieved text marked as untrusted; abstains without calling the model when nothing is relevant | The fast path for focused questions, and grounded answering | 11 tests (54 total); real Pro-plan answer with 5 valid citations that also named what the sources didn't cover; abstains on off-topic questions |
| 6. `POST /api/jobs/analyze` | ✅ code | Haiku extracts requirements with exact quotes (verified against the posting); one batched search for all requirements; Sonnet writes cited study notes for covered ones; eligibility items (degree, clearance) not studied | The spec's first milestone; start of the job-to-roadmap flow | 12 tests (66 total); real batched search: 8 requirements in 1.5 s, one Voyage request; real InterImage run on the Pro plan: 20 requirements, 0 unverified quotes, clearance and degree marked not applicable |
| 7. Tests, review, PR | ✅ | Code-reviewer pass over 36 files; 13 findings verified; 7 groups fixed (me + engineer in parallel on separate files), the rest logged for later milestones; PR to `main` | Quality gate before merging; high-risk areas reviewed | 89 tests, lint clean, secret scan clean |

### Problems we hit and how we solved them

| Problem | What we did | Why it's worth mentioning |
|---|---|---|
| Current Claude models reject the forced tool call LangChain uses for structured output (400 error) | `with_structure()` uses the JSON-schema method instead | Shows you read API changes rather than copying old examples |
| `uv init` copied the owner's email into a public file | Removed it before the first commit | Privacy awareness in a public repo |
| bls.gov blocks scripted downloads (403) | Read the page in a browser and saved the text by hand; never bypassed the block | Respecting site rules while still getting the data |
| Voyage free tier: 3 requests / ~10K tokens a minute, tokens never refresh | `ThrottledEmbeddings` (rate limiter) + `CachedEmbeddings` (never pay twice) | Designing around real constraints |
| A failed 20-minute embedding run could wipe the index | Embed everything first, then rebuild; the cache saves every 32 chunks | Failure-safe data pipelines |
| Claude Code reports input tokens without cached tokens | Cost measurements will use API mode | Knowing where your metrics come from |
| Picking a relevance threshold without guessing | Probed real covered vs uncovered questions: covered scored 0.59–0.68, uncovered 0.27–0.39, so 0.45 sits in the gap | Data-driven tuning, re-checked later with a labelled set |
| The real answer said multi-column indexes weren't covered, but the corpus has a page on them | Logged as a retrieval-recall case for Milestone 2 instead of patching the prompt | Measure before fixing: it's a search problem, not an answering one |
| Searching 20 job requirements one by one would take ~7 minutes on Voyage's free tier (3 requests/min) | Added `embed_queries`: all requirement searches share one Voyage request (8 in 1.5 s) | Spotting a rate-limit bottleneck and batching around it |
| The first real run marked AWS/Azure and Vector databases "covered" from weak matches (0.46–0.53), though Sonnet wrote no note for them | New label `weak_evidence`: "covered" now requires relevant evidence **and** a cited study note | Calibrating labels against what the model actually found useful |
| On a re-run, Sonnet wrote honest notes like "the evidence doesn't cover vector databases directly", yet the label still said ✓ covered | Each note now rates its evidence `direct` or `partial`; `partial` shows as `~` with the note kept | The label now agrees with what the note itself says |
| The same posting gave 20 requirements on one run and 24 on another | Accepted as normal model variation; to be measured in the Milestone 2 workflow evaluation | Knowing which variation is a bug and which is expected |
| The model could invent requirements that aren't in the posting | Each requirement carries an exact quote; code checks the quote appears in the posting and flags it if not | Verifying model output against the source instead of trusting it |
| The code review found an empty visitor key would fall back to the owner's key (`SecretStr("")` is falsy) | `is not None` checks, empty keys refused, request keys refused outside API mode | A one-character bug with real security impact |
| Concurrent API requests could corrupt the rate limiter's shared window | Lock around check-and-reserve, sleep outside the lock; lock around Qdrant search | Thread safety in a thread-pool web server |
| Heading anchors (`¶`, `#`) leaked into citation section names | Strip permalink anchors in the cleaner; re-ingest reused cached embeddings for unchanged chunks | Small polish that the cache made cheap |

### Step 3 in numbers: the first corpus

| Collection | Sources | Example |
|---|---|---|
| Role requirements | 2 | O\*NET Software Developers, BLS Occupational Outlook |
| Technical fundamentals | 6 | MDN HTTP, Azure REST API Guidelines, Python tutorial, FastAPI, pytest |
| Backend engineering | 7 | PostgreSQL indexes and MVCC, SQLite query planner, System Design Primer, Twelve-Factor, OWASP API Top 10 (+ Google SRE link-only) |
| Interview preparation | 2 | Open Data Structures, Tech Interview Handbook |
| Career resources | 1 | Pro Git |
| **Total** | **18** | **52 pages, 956 chunks, ~188K tokens** |

---

## Milestone 2: Retrieval evaluation + tracing ✅
*Ticket: `tickets/T-002-retrieval-evaluation.md`*

**Goal:** measure how well search finds the right sources, so later experiments have a baseline.

| Step | Status | What we built | Why | Result |
|---|---|---|---|---|
| 1. Ticket + housekeeping | ✅ | T-002, branch, Milestone 1 marked merged | Clean start | Pushed |
| 2. Labelled question set | ✅ | 40 questions (31 covered, 9 uncovered), labelled by page + section heading, tagged by query type | You can't improve what you don't measure | All labels checked against the real chunks; owner approved; one label fixed after the first run (v1.1) |
| 3. Eval runner + baseline | ✅ | Own code: Recall@K, Precision@K, MRR, abstention, threshold sweep, per-tag recall, latency; JSON results | One Voyage request per run fits the free tier | Recall@5 0.968, Precision@5 0.645, MRR 0.984; 0.45 keeps 100% covered, rejects 100% uncovered; 14 new tests (103 total); code review: no bugs, 4 hardening fixes |
| 4. LangSmith tracing | ✅ code | `tracing.py`: one on/off rule (asked + key, never live mode, set in code), redaction, visitor keys refused while tracing; traced steps for answer, job analysis, retrieval; Claude Code thread fix | See each step of a request; high-risk area | 13 new tests (116 total); code review + QA found probe/eval could still trace from a shell variable, fixed by starting off at import; real trace 2026-11-18: `answer_question` -> `retrieve` + model call, 6.7 s, retrieval logged as ids + scores only |
| 5. GitHub Actions CI | ✅ | `.github/workflows/ci.yml`: `uv sync --locked`, ruff lint + format, pytest on every push and PR; no secrets; actions pinned to commit SHAs | Free, visible quality signal on the public repo | Green on the first run |

### Problems we hit and how we solved them

| Problem | What we did | Why it's worth mentioning |
|---|---|---|
| Chunk ids change when chunk size changes, which would break labels during the chunk-size experiment | Labels name pages + section headings instead | Designing the dataset for the experiments it has to support |
| Two sources are single 100+ chunk pages, so page labels would count almost anything as relevant | Optional section heading, matched as a whole path component | Keeps precision honest |
| The first run ranked an MDN paragraph first for the "uncovered" CORS question | It really does explain the origin rule, so the label was wrong; fixed in v1.1 and recorded | The eval tested the labels too; factual fixes are fine, relabelling to raise a score is not |
| The second run's latency read 60 s | The rate limiter was waiting out Voyage's 3-per-minute limit; embedding and search are now timed apart (0.66 s vs 3.3 ms) | Knowing what a number actually measures |
| A label typo (`"sections"`) would be silently ignored and widen the target to a whole page | The code review caught it; the loader now refuses unknown fields, empty sections and duplicate targets | A test set needs validation as much as code does |
| Recall@5 of 0.97 looks too good | Recorded with its bias: questions written from the sources' own headings | Reporting a result together with its limits |
| `LANGSMITH_TRACING=true` in `.env` did nothing, while a shell variable could switch tracing on silently | Tracing is now decided in code from settings and set explicitly, which langsmith checks before the environment | Config that looks set but isn't is a classic, hard-to-see bug |

---

## Milestone 3: Agentic workflow (LangGraph) ✅
*Ticket: `tickets/T-003-agentic-workflow.md`*

**Goal:** job description + profile -> requirements -> gap analysis -> prioritised roadmap ->
critic, with a bounded revision loop, as a LangGraph workflow behind `POST /api/career/prepare`.

| Step | Status | What we built | Why | Result |
|---|---|---|---|---|
| 1. Ticket + housekeeping | ✅ | T-003, branch, Milestone 2 marked merged | Clean start | Pushed |
| 2. Explain LangGraph + plan | ✅ | Node plan, `CareerPrepState`, bounded revision loop, open questions settled | The owner approves the design before code | Approved 2026-11-18: 1 revision round, structured profile, simple corrections now |
| 3. Sample profile + job description | ✅ | A fictional new-grad profile and a fictional backend posting, committed | Demos, tests and traces must never use real personal data | Owner approved 2026-11-18 |
| 4. State + graph skeleton | ✅ | `CareerPrepState`, Pydantic schemas, the graph with placeholder nodes, real `analyze_profile` and `finalize`; revision limit in settings; input limits | Get the shape and the loop limits right before any model call | 36 new tests (152 total): joins, loop stops at 0–3, protected keys, recursion backstop; code review: no loop bug, 9 hardening fixes |
| 5a. Job + retrieval nodes | ✅ | Real `analyze_job` (Haiku extraction reused, ids, quote checks) and `retrieve_knowledge` (one batched search); one retry for model nodes on bad output | Reuse what Milestone 1 already proved instead of rewriting it | 18 new tests (170 total): ids, quotes, untrusted posting, one search batch, retry once then fail, retry allow-list, retried nodes counted once; code review: retry bounded, allow-list fix |
| 5b. Gaps, roadmap, questions, critic | ✅ | `analyze_gaps` (Sonnet), `plan_roadmap` + `revise` (Sonnet), `interview_questions` (Haiku), `evaluate` (code checks, then Haiku); corrections as self-reported facts; one injection helper for every prompt | The core of the product: evidence-checked gaps and a plan that only cites what was retrieved | 31 new tests (201 total), incl. full runs: complete, one revision, limit reached; code review: 7 fixes (spaced closing tags, empty or worse revision, empty roadmap, correction cap, cap order, missing sources) |
| 6. API + CLI + real run | ✅ | `POST /api/career/prepare` (body = `WorkflowInput`, limit from settings, one run at a time, fixed error messages), `workflows.cli` (report or JSON), model text truncated at 1,000 characters | One call for the whole feature; a terminal runner for real runs | 17 new tests (217 total); code review: no leaks, 5 fixes. Real Pro-plan run: `complete` after 1 revision in 101 s; 18 requirements, 10 roadmap items (47 h of a 48 h budget), 10 questions (EVALUATION.md) |
| 7. Workflow eval + open tasks + PR | ✅ | 4 labelled workflow cases scored in code (`--rescore` for free re-scoring); concurrency caps on every model route; retry logs redacted; `--out` guard; ingestion hardening (T-005: polite redirects, content type, stale chunks, atomic rebuild) | Measure the workflow's behaviour and close the open review items before the PR | 4/4 cases pass (correction capped, injection had no effect, budget respected); retrieval unchanged; 251 tests; QA clean; merged as `e100ccb` (PR #3, CI green) |

### Problems we hit and how we solved them

| Problem | What we did | Why it's worth mentioning |
|---|---|---|
| Turning off automatic redirects (to re-check robots.txt per hop) made a redirecting robots.txt count as "allow everything" | Review caught it; robots.txt redirects are now followed by hand too | A security fix can open a new hole next to it; review the fix as well |
| Every first roadmap in the evaluation needed a revision | Recorded with the numbers; measure which check fires before changing anything | Measure first, then tune |
| In the real run Sonnet said the knowledge base had no PostgreSQL source, though three PostgreSQL chunks were retrieved, and the warning about it was dropped from the result | Minor issues now stay on a complete result; recorded as a measured failure for the workflow evaluation | Real runs find what fake-model tests can't; record them, don't hide them |
| `< /evidence>` (a space before the slash) passed the tag-neutralising regex we'd used since Milestone 1 | Regex allows whitespace on both sides of the slash; tests for each spacing | Injection defences need adversarial tests, not just the obvious case |
| One correction ("I know all of these") could mark every requirement demonstrated and empty the roadmap | Corrections alone count as partial evidence at most | A feature that helps users can also be gamed; cap what it can do |
| The review showed any node could reset the revision counter or raise the limit, because only `revise` was wrapped | One wrapper around every node refuses writes to input, limit, counter and log | A limit is only a limit if nothing else can change it |
| A critic could say "passed" while listing a blocking problem | Code decides: passed **and** no blocking issue | Don't let the model grade its own pass/fail flag |
| LangGraph's default retry skips `ValueError`, so a malformed model reply (a Pydantic error) would never be retried | Our own retry rule for model nodes: an allow-list (bad output, Claude Code errors), 2 attempts; network retries left to the SDK so they don't multiply | Reading what a framework default actually does before relying on it |
| The loop's safety limit (`recursion_limit`) formula was one step short | Measured the real minimum per revision count: LangGraph counts the input step too; a test pins the exact number | Measuring a framework's behaviour instead of assuming it |

---

## Milestone 4: Router + fallback ✅
*Ticket: `tickets/T-006-router-fallback.md`*

**Goal:** pick traditional RAG or the workflow per request and record why; when the workflow can't
finish, return a labelled partial result instead of an error; measure routing accuracy.

| Step | Status | What we built | Why | Result |
|---|---|---|---|---|
| 1. Ticket + housekeeping | ✅ | T-006, branch, Milestone 3 marked merged | Clean start | Pushed |
| 2. Explain routing + fallback, plan | ✅ | Rules + Haiku router, safe default RAG, `POST /api/assist`, fallback with a 300 s budget, unsupported/needs-input replies | The owner approves the design before code | Approved 2026-11-18 |
| 3. Labelled routing set | ✅ | `evaluation/routing_cases.jsonl`: 30 requests labelled with route and action (run, needs input, unsupported) | Measure routing before building it | Owner approved 2026-11-18: 15 RAG, 7 workflow, 5 needs input, 3 unsupported; 7 borderline, 3 injection |
| 4. Router | ✅ code | `router/`: rules for certain cases, Haiku names the kind, a fixed table picks route and action, safe default RAG; message HTML-escaped; threat model `SECURITY.md` from the owner's security guides | The cheapest path that works, and a route text can't steer | 46 new tests (297 total); rules decide 10 of 30 labels, all correctly (11 before a review fix held back "between"); code review: 5 fixes (mixed questions, comparisons, invisible-character tags, whitespace, log status) |
| 5. Fallback | ✅ code | `run_workflow` streams the graph and keeps the last finished step; a failed stage, an unavailable service, a rate limit, the loop limit or the 300 s budget ends in `status: "fallback"` with finished and unfinished stages, a fixed message, retrieved sources per requirement and at most one cited RAG answer | Never present a partial answer as complete, and never turn a failure into a bare error | 24 new tests (389 total); code review: 6 fixes (fallback could raise, retried a failed service, stale critic issues after a revision, stage lists, wrong-key and rate-limit cases, generator closing); QA clean |
| 6. `POST /api/assist` + route log | ✅ code | One endpoint: route, then RAG, the workflow, or a fixed needs-input / unsupported reply; the decision comes back with the result; chat cap for routing and RAG, career cap for the workflow; one JSON line per request in `logs/routes.jsonl` (no request text); router traced; `router.cli` | The adaptive entry point the frontend will use, and the data for routing stats | 18 new tests (407 total); code review: no bugs; fixed: log capped and rotated, busy vs failed requests told apart in the log, explicit check instead of `assert` |
| 7. Routing eval + comparison + PR | ✅ | `routing_eval` (rules-only free mode, `--rescore`), `routing_compare` (each path runs once, reused across strategies; "served" decided in code), release checks | Measure routing separately from answer quality, and test whether adaptive is really better (spec 2A) | 30/30 labels correct (10 by rules, 20 by Haiku, 2.2 s each); adaptive served 4/4 in 177 s and 15 calls vs always-workflow 2/4 in 320 s and 21 calls, always-RAG 2/4; retrieval unchanged; 425 tests; QA clean; merged as `56fd164` (PR #4, CI green) |


### Problems we hit and how we solved them

| Problem | What we did | Why it's worth mentioning |
|---|---|---|
| The spec's router schema has the model return the route, so an injected "route=agentic" could steer it | The model only names the kind of request; a fixed table in code picks the route | Keep decisions that cost money or matter for safety in code |
| The first rules sent "What is Docker? Also summarise this posting." to RAG and dropped the second request | Rules decide only single, plain questions; anything mixed or about an attachment goes to the model | Rules are cheap, but only where they are certain |
| Zero-width and fullwidth characters could hide our delimiter tags (also in the RAG and workflow prompts) | Untrusted text is normalised and invisible characters removed before tags are neutralised (T-008) | Injection defences need adversarial Unicode tests, not just the obvious spelling |
| Ingestion redirects could reach any host, including private addresses | https manifest hosts only; private, numeric and localhost hosts refused (T-007) | SSRF and knowledge-base poisoning come through "harmless" plumbing |
| The first fallback could itself crash, retried a service that had just failed, and showed critic issues for an older roadmap | Fallback assembly can't raise, no extra call after an outage, stale issues dropped and labelled | The failure path needs as much review as the happy path |
| A failure used to be a bare 502 | The workflow streams step by step and returns a labelled partial result with what finished | Users get something honest and useful instead of an error page |
| 30/30 routing accuracy looks too good | Recorded with its bias: labels and prompt written by the same author | Reporting a result together with its limits |
---

## Milestone 5: Hybrid retrieval + reranking ✅
*Ticket: `tickets/T-010-hybrid-retrieval.md`*

**Goal:** add keyword (sparse) search and a reranker next to semantic search, and keep each only if
the retrieval evaluation shows it helps, measured against semantic-only on the same corpus (v2,
1,592 chunks) and labels (v1.2). Also look for a better "not covered" signal than the 0.45 cosine
threshold, whose margin is gone (`q-031` 0.520 vs lowest covered 0.526).

| Step | Status | What we built | Why | Result |
|---|---|---|---|---|
| 1. Ticket + housekeeping | ✅ | T-010, branch, T-009 marked merged | Clean start | Pushed |
| 2. Explain hybrid, fusion, reranking; open questions | ✅ | Tables for the owner; library options checked against docs | The owner approves the design before code | Approved 2026-11-19: local reranker, fastembed BM25, own RRF, labels first, +300 ms budget |
| 3. Harder labels + baseline | ✅ | Labels v1.3: 6 exact-term and 4 near-topic uncovered questions (owner approved); semantic baseline re-run | Today's set couldn't show an exact-term gain | Semantic ranks all 6 new exact-term questions first (Recall@5 0.961); the threshold fails: 3 of 4 new uncovered clear 0.45, and `q-041` scores 0.393 |
| 4. Sparse index | ✅ measured | `retrieval/sparse.py`: fastembed BM25 vectors in an in-memory Qdrant index (IDF modifier) over the same chunks; the real index untouched until the eval says keep | Keyword matching for exact terms; no Voyage tokens | BM25 alone: Recall@5 0.855, MRR 0.755 |
| 5. Fusion | ✅ measured | Our own `rrf_fuse` (k=60); `retrieval_eval --hybrid 20` compares semantic, BM25 and hybrid on one embedding call, all thresholded on cosine | Combine the two rankings without comparing incompatible scores | **Didn't help:** hybrid Recall@5 0.921 and MRR 0.914 vs semantic 0.961 / 0.987; fixed no miss, added two; abstention unchanged; +11-15 ms |
| 6. Reranker (moved first) | ✅ measured | `retrieval/rerank.py` (local fastembed cross-encoder, 0..1 score) and `retrieval_eval --rerank 10,20 [--rerank-model]`: semantic and reranked from one embedding call | Better ordering, and maybe a better abstention score | **Didn't help:** MiniLM-L-6 lowered Recall@5 0.961 -> 0.921 and MRR 0.987 -> 0.904; bge-reranker-base kept recall but lowered MRR, cost 660-1500 ms per question, and fixed no abstention case (`q-049` scored 0.996). Not added to the service |
| 7. Decision + PR | ✅ | Owner decision 2026-11-19: stay semantic-only; experiments kept in the eval; release checks | Keep only what helps | Semantic-only kept; PR to `main` |

### Problems we hit and how we solved them

| Problem | What we did | Why it's worth mentioning |
|---|---|---|
| The existing exact-term questions already scored 1.0, so hybrid couldn't show a gain | Added 6 harder exact-term and 4 near-topic uncovered questions before measuring (labels v1.3) | A test that can't fail proves nothing |
| The new labels showed the real weakness was "not covered", not ranking | Moved the reranker first, since its score might be a better abstention signal | Let the measurement pick the order of work |
| Both rerankers were near-certain about on-topic chunks that don't answer (0.999) | Measured, recorded, not adopted | A popular component can make a system worse |
| Hybrid chunks found only by BM25 had no cosine score, so the threshold wasn't comparable | Looked up their cosine from the stored vectors (`dense_scores`) | Compare variants on the same yardstick |
| The textbook reason for hybrid (embeddings miss exact terms) didn't hold here | Kept semantic-only and wrote down when to re-test | Decisions are about this data, not general advice |

---

## Milestone 6: Frontend ✅
*Ticket: `tickets/T-011-frontend.md`*

**Goal:** make GradPath usable from a browser: questions, job analysis and the full preparation
workflow, with clickable citations, honest statuses (fallback and partial answers shown as
partial) and clear errors. `DESIGN.md` comes first; the owner approves it before any code.

| Step | Status | What we built | Why | Result |
|---|---|---|---|---|
| 1. Ticket + housekeeping | ✅ | T-011, branch `feat/t-011-frontend` | Clean start | Pushed |
| 2. Plan + open questions | ✅ | Screens, API mapping, long-run and partial-answer handling, security rules, versions checked | The owner approves the design before code | Decided 2026-11-19: backend `partial` status, run polling, answer-quality items 2-4 in TASKS |
| 3. `DESIGN.md` | ✅ | design-advisor draft: an "annotated study notebook" look, honesty states, long-run progress view | One agreed look before building | Approved 2026-11-19 after a visual mock-up (dark first, light/dark toggle) |
| 4. Frontend shell | ✅ | Next.js 16.4.6 + Tailwind 4.3.5 app: tokens, dark-first theme toggle, header/footer, typed API client, safe-link helper, `/api` proxy; frontend CI job | A tested base every screen builds on | 27 Vitest tests; lint, type check and build clean; checked in the browser (dark default, toggle, saved choice) |
| 5. Ask screen (`/`) | ✅ | Question box with example questions, pasted-posting and sample-profile tray, `/api/assist` call with timer and Stop waiting, answer card with safe citations, honesty panels (not covered, needs input, busy, errors), route line | The first screen against the real backend: proves the proxy, client and error handling end to end | 54 Vitest tests; code review fixes applied; a real question answered in ~13 s with a postgresql.org citation |
| 6. Partial answers, safe markdown, proxy timeout | ✅ | T-012 `partial` status with a "Not covered" line; answers render a safe markdown subset; T-013 proxy timeout raised to 330 s | Honest half-answers, readable answers, long runs that don't get cut off | Real runs: q-031/q-049 partial, a covered question answered; 40 s stub returns 200 (500 at 30 s before) |
| 7. Profile screen (`/profile`) | ✅ | Profile form saved only in the browser, validation that matches the backend's limits exactly (code points, integers, 12,000-character total), sample and blank starts, confirmed clear; the Ask tray can use the saved profile | The visitor's own profile instead of the sample | 117 Vitest tests; review fixes applied (tampered storage ignored, errors follow rows, emoji counted like Python) |
| 8. Resume import (T-014) | ✅ | "Fill from a resume" on the Profile screen; `POST /api/profile/from-resume` (one fast-tier call, never traced or stored, contact details scrubbed) | Faster start than typing a profile | Reviewed twice + QA; checked with the fictional resume and the owner's own (kept out of git) |
| 9. Job screen (`/job`) | ✅ | Paste a posting, see each requirement with its coverage, importance, the posting quote, a study note and distinct source chips; "Build a preparation plan" carries the posting to Ask. T-015: citations link to readable GitHub pages | Shows what the knowledge base covers for a real posting | 144 Vitest tests; a real run of the sample posting (16 requirements in ~25 s); review fixes applied |
| 10. Plan screen (`/plan`) + background runs (T-016) | ✅ | Workflow runs in the background behind a run id; the browser polls and shows each stage live; the plan with honesty banners, gaps, roadmap, interview questions and corrections; Ask and Job hand over to it | The 80-300 s run is visible instead of a frozen spinner, and every partial result is labelled | 528 backend + 189 frontend tests; reviewed (backend always-hard + QA); real runs through `/plan` (~50 s, complete) and Ask (complete with open issues) |
| 11. Design critique | ✅ | design-advisor critique of all four screens from 50 screenshots (both themes, 1280 and 375 px, real data); 11 small fixes: type scale, aligned left edges, mobile chips and badges, DESIGN.md loading copy, "Build plan again", motion-safe smooth scroll | Checks the built UI against the approved design before release | No blockers; fixes in `e694acb`, rechecked in the browser; 189 frontend tests |
| 12. Release checks | ✅ | Secret, personal-data and attribution scan; retrieval re-check; SECURITY.md checklist; `pip-audit`; T-017 (three request bodies now reject unknown fields) | The project's release gate | All pass; one local path removed from a ticket; demo mode and visitor keys wait for Milestone 7; 531 backend tests |

---

## Milestone 7: Demo and live modes ⏳
*Ticket: `tickets/T-018-demo-live-modes.md`*

**Goal:** a public site that costs nothing. Demo mode (the default) replays recorded runs with no
keys; live mode runs on a visitor's own Anthropic key, never stored, logged or traced; plus the
limits a public deploy needs. Scope, order and decisions (owner, 2026-11-20) are in the ticket.

| Step | Status | What we built | Why | Result |
|---|---|---|---|---|
| 0. Ticket + plan | ✅ | T-018, branch `feat/t-018-demo-live-modes`; plan approved; modes `local / demo / live`; separate demo endpoints | The owner decides scope and order before code | Resume upload moved out of 7 |
| 1. Demo mode with no keys | ✅ | `APP_MODE` local/demo/live (default demo); `require_model_routes` on every model router (deny by default); lifespan skips Voyage and Qdrant in demo; `demo/` recordings validated against the live response models; `GET /api/demo`, `GET /api/demo/{id}`; tracing only in local | The public site must start and serve with no keys, and no route may spend quota in demo | 568 backend tests; review fixes applied (default and fail-closed guard tested, links and unreadable files skipped); a real startup with every key blanked opened no retrieval and refused `/api/chat` with 403 |

### Problems we hit and how we solved them
- **The old default mode was "demo" but meant "local".** Tests, CLIs and the owner's runs used the
  server's credentials under `APP_MODE=demo`. Fixed with a third value, `local`; `.env.example` now
  sets it, and API tests force it through a `conftest.py` fixture.
- **FastAPI 0.163 nests included routers**, so a test that walked `app.routes` for the guard found
  nothing. The route inventory now comes from the OpenAPI schema.

## Milestones 4–8: what's next

| # | Milestone | What it will do | Why it matters |
|---|---|---|---|
| 4 | Router + fallback | Choose RAG or the workflow per request and record why; labelled partial answers on failure; measure routing accuracy | Use the cheapest path that works; never present a partial answer as complete |
| 5 | Hybrid retrieval + reranking ✅ | Measured keyword search and reranking against semantic-only; neither helped, so neither was kept | Shows decisions backed by measurement, not tutorials |
| 6 | Frontend ✅ | `DESIGN.md` first, then Next.js: inputs, requirements, gaps, roadmap with citations, status and errors | Makes the system usable and demoable |
| 7 | Demo and live modes | Recorded runs with a sample profile; live mode with a visitor's own key, never stored or logged | A public portfolio site that costs nothing |
| 8 | Deploy | Vercel, Render, Qdrant Cloud (free); release checks; README with diagram and demo steps | A live link employers can open |

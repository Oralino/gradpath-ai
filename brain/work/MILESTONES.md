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
| 3 | Agentic workflow | ⏳ | Job + profile -> gaps -> roadmap | A LangGraph workflow with a self-check loop |
| 4 | Router + fallback | ⏳ | Pick the cheapest path that works | Routing accuracy, labelled partial answers |
| 5 | Hybrid retrieval + reranking | ⏳ | Improve search for exact terms | Before/after metrics vs semantic-only |
| 6 | Frontend | ⏳ | Make it usable | Next.js app designed from `DESIGN.md` |
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

## Milestones 2–8: what's next

| # | Milestone | What it will do | Why it matters |
|---|---|---|---|
| 2 | Retrieval evaluation + tracing | Label 30–50 questions with their correct sources; measure Recall@K, Precision@K, MRR; turn on LangSmith | Measured quality makes the project credible and gives a baseline for every experiment |
| 3 | Agentic workflow (LangGraph) | Analyse job and profile in parallel -> retrieve -> gap analysis -> roadmap -> critic, with a bounded revision loop; `POST /api/career/prepare` | The main feature needs several dependent steps, which one prompt can't do reliably |
| 4 | Router + fallback | Choose RAG or the workflow per request and record why; labelled partial answers on failure; measure routing accuracy | Use the cheapest path that works; never present a partial answer as complete |
| 5 | Hybrid retrieval + reranking | Add keyword search and reranking; keep them only if the evaluation shows they help | Exact terms ("MVCC", "404") are where semantic search is weakest |
| 6 | Frontend | `DESIGN.md` first, then Next.js: inputs, requirements, gaps, roadmap with citations, status and errors | Makes the system usable and demoable |
| 7 | Demo and live modes | Recorded runs with a sample profile; live mode with a visitor's own key, never stored or logged | A public portfolio site that costs nothing |
| 8 | Deploy | Vercel, Render, Qdrant Cloud (free); release checks; README with diagram and demo steps | A live link employers can open |

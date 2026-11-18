# MILESTONES.md
The project's story, milestone by milestone: what we built, why, and what it does, written so the
owner can retell it. Open to-dos are in `TASKS.md`, finished items in `DONE.md`, details and commits
in `tickets/`. Concepts and interview answers are in `../engineering/WALKTHROUGH.md`.

**Status key:** ✅ done · 🔨 in progress · ⏳ planned

## At a glance

| # | Milestone | Status | Goal | What you can show |
|---|---|---|---|---|
| 0 | Project setup | ✅ | Decide the plan, stack and rules before coding | Public repo, `brain/` docs, licence-checked sources |
| 1 | RAG foundation | 🔨 | Load sources, answer with citations, analyse a job description | Cited answers, "not covered" answers, 40+ tests |
| 2 | Retrieval evaluation + tracing | ⏳ | Measure search quality | Recall@K / Precision@K / MRR numbers, LangSmith traces |
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

## Milestone 1: RAG foundation 🔨
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
| 7. Tests, review, commit | ⏳ | Full test run, code review (high-risk parts), commit and PR | Quality gate before merging | |

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
| The model could invent requirements that aren't in the posting | Each requirement carries an exact quote; code checks the quote appears in the posting and flags it if not | Verifying model output against the source instead of trusting it |
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

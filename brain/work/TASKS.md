# TASKS.md
Open work. Owner-only items are marked **(owner)**. Finished work moves to `DONE.md`.
Non-trivial work gets a ticket in `tickets/` when it starts; open tickets are listed here as links.
Milestones follow the spec's order, adjusted to the owner's decisions (`../product/REQUIREMENTS.md`).

## Current
- [ ] **(owner)** Review the setup docs, then say go for Milestone 1.

## Before Milestone 1
- [ ] Make Claude Code callable from Python on this PC (CLI or Agent SDK), for `ChatClaudeCode`.
- [ ] Confirm the licences marked `license_verified=no` before downloading each source.
- [ ] **(owner + Claude)** Fill gaps: behavioral interviews (STAR), caching, message queues.
- [ ] More new-grad backend job descriptions in `private/job_descriptions/` (one so far).

## Milestones
1. [ ] **RAG foundation:** uv project, provider factory (`ChatClaudeCode`, `ChatAnthropic`, fake),
       ingestion (loaders, splitter, Voyage, local Qdrant), retrieval service, `/api/chat` traditional
       RAG with citations and abstention, tests.
2. [ ] **Retrieval eval baseline + tracing:** labelled questions, Recall@K / Precision@K / MRR,
       LangSmith tracing and datasets, first results in `EVALUATION.md`.
3. [ ] **Agentic workflow:** typed state, JD extraction, profile analysis, retrieval tool, gap
       analysis, roadmap, critic with bounded revision; `/api/career/prepare` with a job ID.
4. [ ] **Router + fallback:** route schema, router, labelled fallback, routing eval vs baselines.
5. [ ] **Hybrid retrieval + reranking:** measured against the semantic baseline.
6. [ ] **Frontend:** design-advisor drafts `DESIGN.md`; Next.js JD and profile input, requirements,
       gaps, roadmap with citations, status and error states.
7. [ ] **Demo and live modes:** record and replay runs with a sample profile; visitor key handling.
8. [ ] **Deploy:** Vercel + Render + Qdrant Cloud; release checks; README with diagram and demo steps.

## Later
Interview practice with feedback, multi-JD comparison, resume alignment, progress tracking,
multi-user accounts.

## Bugs
None open.

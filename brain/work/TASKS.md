# TASKS.md
Open work. Owner-only items are marked **(owner)**. Finished work moves to `DONE.md`.
Non-trivial work gets a ticket in `tickets/` when it starts; open tickets are listed here as links.
Milestones follow the spec's order, adjusted to the owner's decisions (`../product/REQUIREMENTS.md`).

## Current
- [ ] **(owner)** Review and merge the Milestone 1 PR.
- [ ] Write `HANDOFF.md`; start the Milestone 2 session after owner approval.

## Before Milestone 2
- [ ] **(owner + Claude)** Fill corpus gaps: behavioral interviews (STAR), caching, message queues,
      Docker/Kubernetes, CI/CD, LLM/RAG tooling (LangChain, vector databases).
- [ ] More new-grad backend job descriptions in `private/job_descriptions/` (one so far).

## Milestones
The milestone plan and its story (what, why, what it does) live in [MILESTONES.md](MILESTONES.md).

## Deferred from the Milestone 1 code review (2026-11-17)
Before any deploy (Milestones 7–8):
- [ ] Auth or passcode, per-IP rate limits and a concurrency cap on `/api/chat` and
      `/api/jobs/analyze` (each call can start a Claude Code process and spend plan quota).
- [ ] Enforce `APP_MODE` (demo vs live); the app must start and serve demo mode with no keys set
      (today the lifespan needs `VOYAGE_API_KEY`).
Milestone 2 (tracing):
- [ ] Wire `LANGSMITH_TRACING` explicitly (settings field is unused; tracing now depends on shell
      variables) and decide what may reach LangSmith (always-hard area).
- [ ] `ChatClaudeCode._generate` drops `run_manager` and context variables in its worker thread,
      so callbacks/tracing don't see sync calls.
- [ ] Grounding check beyond citation ids (faithfulness metric in `EVALUATION.md`).
Ingestion polish:
- [ ] Re-check robots.txt and the host gap after a redirect to another host.
- [ ] Check Content-Type before cleaning (a PDF would be cleaned as HTML).
- [ ] A document that now yields zero chunks keeps its stale processed JSONL.
- [ ] Make the index rebuild atomic (build a new collection, then swap via an alias).

## Later
Interview practice with feedback, multi-JD comparison, resume alignment, progress tracking,
multi-user accounts.

## Bugs
None open.

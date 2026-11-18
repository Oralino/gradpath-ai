# TASKS.md
Open work. Owner-only items are marked **(owner)**. Finished work moves to `DONE.md`.
Non-trivial work gets a ticket in `tickets/` when it starts; open tickets are listed here as links.
Milestones follow the spec's order, adjusted to the owner's decisions (`../product/REQUIREMENTS.md`).

## Current
- [ ] [T-006 Milestone 4: router + fallback](tickets/T-006-router-fallback.md) (in progress).

Security gaps from `../engineering/SECURITY.md` (proposed, waiting for the owner):
- [ ] T-007 (proposed): ingestion redirects: https only, same or manifest host only, no private IPs
      (SSRF and knowledge-base poisoning).
- [ ] T-008 (proposed): `safety.neutralise_tags` misses zero-width and fullwidth tag variants.
- [ ] Add `uvx pip-audit` to the release checks (dependency vulnerabilities).
- [ ] **(owner)** Two-factor authentication on GitHub, Anthropic, Voyage and LangSmith.

## Corpus (before Milestone 5)
- [ ] **(owner + Claude)** Fill corpus gaps: behavioral interviews (STAR), caching, message queues,
      Docker/Kubernetes, CI/CD, LLM/RAG tooling (LangChain, vector databases).
- [ ] More new-grad backend job descriptions in `private/job_descriptions/` (one so far).

## Milestones
The milestone plan and its story (what, why, what it does) live in [MILESTONES.md](MILESTONES.md).

## Deferred from the Milestone 1 code review (2026-11-17)
Before any deploy (Milestones 7–8):
- [ ] Auth or passcode and per-IP rate limits on the model routes (each call can start a Claude
      Code process and spend plan quota). Concurrency caps done: `api/limits.py` (T-003).
- [ ] Enforce `APP_MODE` (demo vs live); the app must start and serve demo mode with no keys set
      (today the lifespan needs `VOYAGE_API_KEY`).
- [ ] `POST /api/career/prepare` (like the other routes) uses the server's model credentials
      whatever `APP_MODE` says; live mode must pass the visitor's key instead (T-003 review).
- [x] LangGraph's "Retrying task" log line no longer carries exception text (filter in
      `workflows/graph.py`, T-003).
- [x] `workflows.cli --out` saves a real profile's results only under `private/` (T-003).
- [ ] When live-mode key handling lands: the visitor-key tracing guard in `get_chat_model` checks
      once, when the model is built; re-check it covers how routes build models (T-002 review).
Milestone 2 (tracing):
- [x] Wire `LANGSMITH_TRACING` explicitly and decide what may reach LangSmith (T-002, `tracing.py`).
- [x] `ChatClaudeCode._generate` worker thread now runs in a copy of the caller's context (T-002).
      `run_manager` is still not passed in: it only matters for token streaming, which we don't use.
- [ ] Grounding check beyond citation ids (faithfulness metric in `EVALUATION.md`).
Workflow (from the T-003 evaluation):
- [ ] The roadmap sometimes says "no source in the knowledge base" for a gap that has retrieved
      evidence (PostgreSQL, twice). `no_resources` flags it as minor; consider blocking, or a prompt
      rule to cite listed evidence.
- [ ] Every first roadmap needed a revision (4/4): record which check fires before tuning.
Ingestion polish (T-005, done 2026-11-18):
- [x] Re-check robots.txt and the host gap after a redirect to another host.
- [x] Check Content-Type before cleaning (a PDF would be cleaned as HTML).
- [x] A document that now yields zero chunks keeps its stale processed JSONL.
- [x] Make the index rebuild atomic (build a new collection, then swap via an alias).

## Later
Interview practice with feedback, multi-JD comparison, resume alignment, progress tracking,
multi-user accounts.

## Bugs
None open.

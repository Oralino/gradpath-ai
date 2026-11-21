# TASKS.md
Open work. Owner-only items are marked **(owner)**. Finished work moves to `DONE.md`.
Non-trivial work gets a ticket in `tickets/` when it starts; open tickets are listed here as links.
Milestones follow the spec's order, adjusted to the owner's decisions (`../product/REQUIREMENTS.md`).

## Current
- [ ] [T-018](tickets/T-018-demo-live-modes.md): Milestone 7, demo and live modes (plan approved
      2026-11-20: scope, order and decisions in the ticket).
- [ ] DESIGN.md: record the visible input rows and "Build plan again" on the Plan screen
      (design-advisor drafts, owner approves; T-011 design critique).
- [ ] PDF/DOCX resume upload (T-014 did pasted text; uploads are always-hard). Moved out of Milestone 7
      (owner decision 2026-11-20, T-018) to a later milestone.
- [ ] Milestone 7 (moved from 6 on 2026-11-20, not built there): a "sources as of" date the API
      returns and the footer shows (`DESIGN.md` Known gaps and footer copy).

Answer quality (owner decision 2026-11-19: before Milestone 7's public demo):
- [ ] Answer eval set: ~20 questions with must-contain facts plus must-refuse cases, scored in code.
- [ ] Grounding check: Haiku checks each claim against its cited chunk; report a "supported" rate.
- [ ] Re-run the retrieval and answer evals as a release check when sources, prompts or models change.

Security gaps from `../engineering/SECURITY.md` (proposed, waiting for the owner):
- [x] [T-007](tickets/T-007-ingestion-url-allowlist.md): ingestion URLs limited to https manifest hosts.
- [x] [T-008](tickets/T-008-tag-neutraliser-unicode.md): tag neutraliser handles invisible and look-alike characters.
- [ ] Add `uvx pip-audit` to the release checks (dependency vulnerabilities). Ran for Milestone 6:
      clean (T-011); `npm audit` for the frontend also found 0 vulnerabilities (2026-11-20). Adopting
      both in `CLAUDE.md` is the owner's call.
- [ ] **(owner)** Two-factor authentication on GitHub, Anthropic, Voyage and LangSmith.

## Corpus (before Milestone 5)
- [x] Fill corpus gaps (T-009, 2026-11-19): 10 sources added.
- [x] Citations for raw GitHub files point at raw.githubusercontent.com; map them to the docs
      sites' readable URLs ([T-015](tickets/T-015-readable-citation-links.md)).
- [x] Before Milestone 5: the 0.45 threshold no longer separates near-topic uncovered questions.
      Reranker scores tried in T-010: no better. Follow-up moved to "Current" (answer-step abstention).
- [ ] More new-grad backend job descriptions in `private/job_descriptions/` (one so far).
- [ ] **After Milestone 6 (owner decision 2026-11-19):** corpus update driven by need, in a T-009-style
      ticket. Run the job-analysis tool over the target postings to list poorly answered skills; use
      the UI's "not covered" and partial answers; check the remaining Voyage free tokens first.
      Candidates seen so far: Kubernetes Pod Lifecycle / configure probes, PostgreSQL explicit locking
      (`SKIP LOCKED`), GitHub Actions trigger events, Kafka consumer groups. Covering eval questions
      `q-031`, `q-047`, `q-049`, `q-050` means relabelling them and writing new near-topic uncovered
      questions to keep the refusal test.

## Milestones
The milestone plan and its story (what, why, what it does) live in [MILESTONES.md](MILESTONES.md).

## Deferred from the Milestone 1 code review (2026-11-17)
Before any deploy (Milestones 7–8):
- [ ] Auth or passcode and per-IP rate limits on the model routes (each call can start a Claude
      Code process and spend plan quota). Concurrency caps done: `api/limits.py` (T-003).
      Known gap (T-006): `/api/assist` spends its routing call before the career cap can answer
      503 while a workflow is running; per-IP limits close it.
- [x] Enforce `APP_MODE`; the app starts and serves demo mode with no keys set (T-018 step 1).
- [ ] `POST /api/career/prepare` (like the other routes) uses the server's model credentials
      whatever `APP_MODE` says; live mode must pass the visitor's key instead (T-003 review).
- [x] LangGraph's "Retrying task" log line no longer carries exception text (filter in
      `workflows/graph.py`, T-003).
- [x] `workflows.cli --out` saves a real profile's results only under `private/` (T-003).
- [ ] Before live mode: a 422 handler that drops `input` from FastAPI's validation errors, so a
      visitor key sent in a wrong field is never echoed back (found in T-017).
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

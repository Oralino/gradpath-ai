# TASKS.md
Open work. Owner-only items are marked **(owner)**. Finished work moves to `DONE.md`.
Non-trivial work gets a ticket in `tickets/` when it starts; open tickets are listed here as links.
Milestones follow the spec's order, adjusted to the owner's decisions (`../product/REQUIREMENTS.md`).

## Current
- [ ] [T-011](tickets/T-011-frontend.md): Milestone 6, the Next.js frontend (in progress).
- [ ] Milestone 6: a backend `partial` answer status (owner decision 2026-11-19). Today
      `ChatAnswer.status` is only `answered` or `insufficient_evidence`, so an answer that opens with
      "the evidence doesn't cover ..." (`q-031`, `q-049`) looks like a full answer. Own ticket.
- [ ] Milestone 6: run id + status polling for workflow runs (owner decision 2026-11-19). Own ticket;
      always-hard area (workflow limits).
- [ ] Milestone 6: import a profile from pasted resume text (owner decision 2026-11-19). New endpoint:
      resume text in, `UserProfile` out (Haiku, structured output); contact details dropped; text
      not stored or traced; the owner reviews the result before saving. Fictional sample resume for
      demos and tests. Own ticket. PDF/DOCX upload deferred to Milestone 7 (always-hard: uploads).
- [ ] Milestone 6 (backend, small): a "sources as of" date the UI can show (`DESIGN.md` Known gaps).
- [ ] Milestone 6: answers contain markdown (`**bold**`, backticks, `- ` lists) that the UI shows as
      raw characters, because `DESIGN.md` renders plain text only. Owner to choose: ask the answer
      prompt for plain text, or render a small safe subset (lists, bold, code) without HTML.

Answer quality (owner decision 2026-11-19: before Milestone 7's public demo):
- [ ] Answer eval set: ~20 questions with must-contain facts plus must-refuse cases, scored in code.
- [ ] Grounding check: Haiku checks each claim against its cited chunk; report a "supported" rate.
- [ ] Re-run the retrieval and answer evals as a release check when sources, prompts or models change.

Security gaps from `../engineering/SECURITY.md` (proposed, waiting for the owner):
- [x] [T-007](tickets/T-007-ingestion-url-allowlist.md): ingestion URLs limited to https manifest hosts.
- [x] [T-008](tickets/T-008-tag-neutraliser-unicode.md): tag neutraliser handles invisible and look-alike characters.
- [ ] Add `uvx pip-audit` to the release checks (dependency vulnerabilities).
- [ ] **(owner)** Two-factor authentication on GitHub, Anthropic, Voyage and LangSmith.

## Corpus (before Milestone 5)
- [x] Fill corpus gaps (T-009, 2026-11-19): 10 sources added.
- [ ] Citations for raw GitHub files point at raw.githubusercontent.com; map them to the docs
      sites' readable URLs.
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

# TASKS.md
Open work. Owner-only items are marked **(owner)**. Finished work moves to `DONE.md`.
Non-trivial work gets a ticket in `tickets/open/` (moved to `tickets/in-progress/`, then
`tickets/done/`, as its status changes); open tickets are listed here as links.
Milestones follow the spec's order, adjusted to the owner's decisions (`../product/REQUIREMENTS.md`).

## Current
- [ ] [T-020](tickets/in-progress/T-020-deploy.md): Milestone 8, deploy (plan approved 2026-11-21: decisions
      in the ticket). Done: steps 0, 1 (index on Qdrant Cloud), 2, 2b (Docker image) and 3 (live
      on Render and Vercel) and 4 (visitor address vouched for by the site with a shared secret;
      direct calls to Render refused) and 5 (deployed-site checks, Trivy in CI, security
      headers, separate keys, the waking screen T-028). Open from step 5: a
      Content-Security-Policy decision. Next: step 6 (README), then the milestone PR.
- [ ] [T-027](tickets/open/T-027-app-info-logs.md): the API's own INFO log lines (sign-in
      outcomes and others) never reach the logs; only warnings do. Found closing T-026.
- [ ] DESIGN.md: record the GitHub sign-in row of the live panel (replaces the passcode field and
      decisions 11-12; design-advisor drafts, owner approves; T-026).
- [ ] DESIGN.md: record the visible input rows and "Build plan again" on the Plan screen
      (design-advisor drafts, owner approves; T-011 design critique).
- [ ] PDF/DOCX resume upload (T-014 did pasted text; uploads are always-hard). Moved out of Milestone 7
      (owner decision 2026-11-20, T-018) to a later milestone.
- [x] A "sources as of" date the API returns and the footer shows (T-018 step 3).

Answer quality (owner decision 2026-11-19: before Milestone 7's public demo):
- [x] Answer eval set: 20 cases (14 must-contain, 6 must-refuse), scored in code (T-018 step 10).
- [x] Answers add unsupported advice: fixed by the no-advice prompt rule, 7/166 -> 1/151
      unsupported claims ([T-019](tickets/done/T-019-answers-follow-sources.md)).
- [x] Grounding check: Haiku checks each claim against its cited chunk; 96% supported (T-018 step 10).
- [ ] Re-run the retrieval and answer evals as a release check when sources, prompts or models change.

Security gaps from `../engineering/SECURITY.md` (proposed, waiting for the owner):
- [x] [T-007](tickets/done/T-007-ingestion-url-allowlist.md): ingestion URLs limited to https manifest hosts.
- [x] [T-008](tickets/done/T-008-tag-neutraliser-unicode.md): tag neutraliser handles invisible and look-alike characters.
- [ ] Add `uvx pip-audit` to the release checks (dependency vulnerabilities). Ran for Milestone 6:
      clean (T-011); `npm audit` for the frontend also found 0 vulnerabilities (2026-11-20). Adopting
      both in `CLAUDE.md` is the owner's call.
- [ ] **(owner)** Two-factor authentication on GitHub, Anthropic, Voyage and LangSmith.

## Corpus (before Milestone 5)
- [x] Fill corpus gaps (T-009, 2026-11-19): 10 sources added.
- [x] Citations for raw GitHub files point at raw.githubusercontent.com; map them to the docs
      sites' readable URLs ([T-015](tickets/done/T-015-readable-citation-links.md)).
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
- [x] Passcode and per-IP rate limits on the model routes (T-018 step 7); closes the T-006 gap
      (`/api/assist` spending its routing call while a workflow runs) and the step 5 finding (a
      made-up key spending a Voyage search: now behind the passcode).
- [ ] Optional: a free key pre-check (models list, cached per owner tag) and a kinder message for
      Anthropic's "no credit" 400 (from the T-018 step 5 review).
- [x] Enforce `APP_MODE`; the app starts and serves demo mode with no keys set (T-018 step 1).
- [x] Live mode passes the visitor's key to every model route (T-018 step 5).
- [x] LangGraph's "Retrying task" log line no longer carries exception text (filter in
      `workflows/graph.py`, T-003).
- [x] `workflows.cli --out` saves a real profile's results only under `private/` (T-003).
- [x] A 422 handler that drops `input` from FastAPI's validation errors (T-018 step 6).
- [x] Re-checked (T-018 step 5): every API route builds models through `deps.get_answer_model` /
      `get_extraction_model` -> `get_chat_model(api_key=...)`, and tracing is off in live mode.
Milestone 2 (tracing):
- [x] Wire `LANGSMITH_TRACING` explicitly and decide what may reach LangSmith (T-002, `tracing.py`).
- [x] `ChatClaudeCode._generate` worker thread now runs in a copy of the caller's context (T-002).
      `run_manager` is still not passed in: it only matters for token streaming, which we don't use.
- [x] Grounding check beyond citation ids: per-claim grounding check, T-018 step 10.
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

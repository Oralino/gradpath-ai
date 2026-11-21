# T-018: Milestone 7, demo and live modes
Milestone 7 ticket. Plan and story in `../MILESTONES.md`; modes in
`../../engineering/ARCHITECTURE.md` ("Providers and modes"); threats in
`../../engineering/SECURITY.md` (01, 07, release checklist).

- **Type:** feature
- **Status:** in progress
- **Opened:** 2026-11-20 · **Closed:**
- **GitHub Issue:** none

## Summary
Make a public site that costs nothing:
- **Demo mode** (default online): replays recorded runs from `demo_runs/` (sample profile only). No
  model or embedding calls, and the API starts and serves with no keys set at all. Today the lifespan
  needs `VOYAGE_API_KEY`, and `demo_runs/` doesn't exist.
- **Live mode:** the visitor's own Anthropic key, per request, never stored, logged, traced or returned.
  Today every route builds models with the server's credentials whatever `APP_MODE` says.
- **Before any public deploy:** auth or passcode and per-IP rate limits on the model routes; a 422
  handler that drops `input` (T-017 finding); CORS allow-list and a CSRF test.

Candidate items also listed for this milestone (scope and order are the owner's call, see Decision):
PDF/DOCX resume upload; a "sources as of" date in the API and footer; the answer eval set and
grounding check (owner decision 2026-11-19: before the public demo).

## Decision
Owner decisions, 2026-11-20 (plan approved):
- **Scope:** the core steps, plus the "sources as of" date, the answer eval set and the grounding check.
  PDF/DOCX resume upload moves out of 7 (later milestone): not needed for a zero-cost demo, and it adds
  file-validation risk right before the deploy.
- **Voyage in live mode:** the owner's Voyage key embeds visitors' questions, behind a per-IP rate limit
  (visitors paste only an Anthropic key). Rejected: asking visitors for a Voyage key too (two keys is too
  much friction).
- **Auth:** a shared passcode in a request header (server env var) on live routes, plus per-IP limits;
  demo mode stays open. Rejected: per-IP limits alone; a passcode on demo too.
- **Order:** 1 demo mode with no keys, 2 record demo runs, 3 sources date, 4 live source search
  (added 2026-11-20, below), 5 visitor key end to end, 6 422 handler that drops `input`, 7 passcode
  and per-IP limits, 8 CORS allow-list and CSRF test, 9 frontend demo/live switch (design-advisor
  first), 10 answer eval set and grounding check, 11 release checks and PR.
- **Live source search for visitors without a key (owner decision 2026-11-20):** both hybrid paths
  (traditional RAG and the agentic workflow) need a model to write their output, so a visitor with
  no key can't "fall back" to traditional RAG. Instead, demo and live mode add a search box: a real
  retrieval over the knowledge base (the owner's Voyage key, no model call) that returns the
  matching source passages with links, labelled "sources only, no written answer", plus a
  rules-only routing preview (`router/rules.rule_kind`; "a model would decide" when the rules
  can't). The server opens retrieval in demo mode only when `VOYAGE_API_KEY` is set; without it the
  search is off and demo mode still starts with no keys (the release check holds). Needs a per-IP
  limit (step 7) because Voyage's 3 requests a minute are shared; about 20 tokens a query from the
  non-refreshing free tokens. Rejected: a server-paid model key (zero-cost rule); running the
  owner's Pro plan on the server (tied to the owner's own login).
- **Modes (step 1, owner decision 2026-11-20):** `APP_MODE` is `local` (owner's machine, server
  credentials, tracing allowed), `demo` (deployed, recordings only, model routes off) or `live`
  (deployed, visitor key). Default `demo`. Rejected: `local / public` with no recordings-only mode.
- **Replay (step 1):** separate read-only `GET /api/demo` and `GET /api/demo/{id}`. Rejected: replaying
  on the model routes by matching the request to a sample (brittle, keeps the routes reachable).
- **Found from guide 02 (for steps 4/6):** run ids are the only protection on
  `GET /api/career/runs/{id}`; unguessable ids aren't access control. Bind a run to its starter
  before live mode opens the run routes.

## Changes
- Branch: `feat/t-018-demo-live-modes`
- PR:
- Files touched: step 1: `config.py`, `tracing.py`, `api/deps.py`, `api/main.py`, `api/demo.py`,
  `api/{chat,jobs,career,runs,assist,profile}.py`, `demo/`, `tests/test_demo.py`, `tests/conftest.py`,
  `tests/test_tracing.py`, `.env.example`, README, ARCHITECTURE, SECURITY, WALKTHROUGH, MILESTONES.
- Commits (hash, message):

## Verification
Step 1 (2026-11-20): 568 backend tests pass, 1 skipped on Windows (the symlink test needs rights;
CI on Linux runs it); ruff clean. A real startup with `APP_MODE=demo` and every key blanked opened no
retrieval, served `/api/demo` and refused `POST /api/chat` with 403. code-reviewer: no blocking
issue; fixed: the default mode and a fail-closed guard are now tested, links and unreadable files in
`demo_runs/` are skipped, a warning when tracing is asked for outside local mode, a stale comment.
Deferred from the step 1 review:
- FastAPI parses the JSON body before dependencies, so a malformed body gets 422 before the 403
  (step 5's 422 handler; a body-size cap with step 6).
- `/docs`, `/redoc`, `/openapi.json` and `llm_provider` in `/api/health` are open outside local
  mode (the `/docs` decision, Milestone 8 in SECURITY.md 01).
- `test_every_committed_recording_is_valid` passes empty until step 2 adds recordings: add a
  "at least one" assert then.
Owner: set `APP_MODE=local` in your own `.env` (it held `demo`, which now means recordings only).

Step 2 (2026-11-20): `uv run python -m gradpath.demo.record` in the owner's Terminal panel saved 8
recordings in about 4 minutes. Routes as intended (RAG x4, needs_input, workflow); the Kubernetes
question came back `partial`, so its title says "a known gap". The plan is
`complete_with_limitations` (1 revision, one blocking issue on a Docker item). Scanned: no local
paths, contact details or keys (the only `@` is FastAPI's `@app.get` in a study note). code-reviewer:
no leak path; fixed: expected route per example, corrupt files replaced, a forced workflow ask
rebuilds or flags its plan, local paths and more key kinds in the scan, the refusal names the kind,
a tracing check, Qdrant closed if model setup fails. 588 backend tests. Served through `/api/demo`
with every key blanked.

Remaining release checks are filled in at step 11. Release checks from `CLAUDE.md` apply (demo mode with no keys, visitor key never in logs,
traces or responses, retrieval eval, the SECURITY.md checklist including its "From Milestone 7" line).

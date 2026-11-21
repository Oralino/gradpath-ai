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
- PR: [#11](https://github.com/Oralino/gradpath-ai/pull/11)
- Files touched: step 1: `config.py`, `tracing.py`, `api/deps.py`, `api/main.py`, `api/demo.py`,
  `api/{chat,jobs,career,runs,assist,profile}.py`, `demo/`, `tests/test_demo.py`, `tests/conftest.py`,
  `tests/test_tracing.py`, `.env.example`, README, ARCHITECTURE, SECURITY, WALKTHROUGH, MILESTONES.
- Files touched, step 9: backend `api/live.py`, `api/deps.py`, `api/main.py` (error codes, health),
  frontend `lib/liveSession.ts`, `lib/serverInfo.tsx`, `lib/api.ts`, `lib/types.ts`,
  `lib/examples.ts`, `lib/useRecordings.ts`, `lib/useCountdown.ts`, `app/layout.tsx`,
  `app/search/page.tsx`, `components/{LivePanel,RecordedExamples,SourceSearch,ModeBadge,ModeNote,
  ServerGate,ModeErrorPanel,RetryAfter}.tsx`, changes to `Assistant`, `JobAnalysisView`,
  `PlanView`, `ResumeImport`, `SiteHeader`, `SourcesDate`, `CitationList`, `RouteLine`,
  `StatusPanel`, `PlanResult`, `icons`, and their tests; ARCHITECTURE, WALKTHROUGH, MILESTONES.
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

Step 3 (2026-11-20): `knowledge_base/index_info.json` from `ingest --info-only` matches Qdrant
(1,592 chunks, 27 documents); `/api/health` returns `sources_as_of`; the footer showed "Sources as
of 18 Nov 2026 · …" in the browser (API + `next dev`), now 19 Nov after the review fix. code-reviewer:
no bugs; fixed: manual sources no longer date the index (file time, not a fetch date), the summary
is computed before the rebuild and written after it, a missing processed file is logged, tests for
the run ordering. Not changed: the footer line reflows once when the date arrives (the date leads
the sentence per DESIGN.md's copy); the "·" separators are read aloud like the rest of the footer.
602 backend + 195 frontend tests; lint, type check and build clean. Note: running `npx prettier`
once downloaded Prettier from npm (not a project tool); its formatting was reverted by hand.

Step 4 (2026-11-20): `POST /api/search` in a real demo-mode API with the owner's Voyage key:
"What is a multicolumn index?" gave 4 passages (SQLite and PostgreSQL docs, scores 0.59-0.64) and
the rules preview "traditional RAG"; "How should a service shut down gracefully?" gave 2 Twelve-Factor
passages and "a model would decide"; `/api/chat` stayed 403. code-reviewer fixes: search embeds
without waiting or retrying (a full window or a Voyage 429 answers 429 at once, one request at most),
Voyage errors logged by type only, `open_retrieval` passes its settings through, excerpts keep line
breaks and cut cleanly, tests for the Voyage error paths. Left: the cross-module test helper import
(the project's existing pattern). Per-IP limits (step 7) and CORS for this route (step 8) still to
do. 629 backend tests.

Step 5 (2026-11-20): visitor key in the `X-Anthropic-Key` header; live answers 401 without a
well-formed one; every API route builds both model tiers through the key-aware dependencies (a spy
test per route); refused key 401, the visitor's rate limit 429; runs bound to their key (HMAC owner
tag, tested through `/api/career/runs` and `/api/assist`); live refuses to start without
`LLM_PROVIDER=anthropic_api`, with a server `ANTHROPIC_API_KEY`, or with `ANTHROPIC_BASE_URL` /
`ANTHROPIC_API_URL` set; SDK loggers capped at WARNING. code-reviewer (security): no path stores,
logs, traces or returns the key; fixed: route-level ownership and per-route key tests, logger levels
restored in tests, the host-redirect refusal, deploy notes in SECURITY.md. Moved to step 7: a made-up
key of the right shape spends one Voyage search before Anthropic refuses it (passcode, per-IP
limits, optional key pre-check), and a "no credit" message. qa-checker: ruff, 662 backend + 195
frontend tests, secret and attribution scan, no key in any log call, `.env` untracked: all clean.
Not tested with a real key: the owner has none (zero-cost rule).

Step 6 (2026-11-20): `safe_validation_errors` keeps loc/msg/type only; unknown field names
become "(unknown field)", other non-identifier locations "?". Tests: a key as an unknown field, as
a field name, inside a too-long or wrong-type field, nested in the profile, and in broken JSON never
comes back or reaches the logs; the frontend's row locations survive. code-reviewer: no findings
beyond suggestions (applied: a note about future dict fields, shape pinned, an edge-case table).
Problem: commit 33dce49 pushed a test file with a syntax error (an escaped newline in an edit
script became a real one, and the commit was chained with `;` after the failing check); fixed in
the next commit. 680 backend tests.

Step 7 (2026-11-20): passcode (`X-GradPath-Passcode`, 16+ printable ASCII, constant-time,
5 failures per client in 15 min lock it), per-client limits off in local mode (search 2/min
60/day + 1,000/day total; model 6/min 60/day; workflow 3/h 10/day, also charged and pre-checked by
`/api/assist`; polling 60/min), `TRUSTED_PROXY_HOPS`, a 256 KB body cap (413). code-reviewer
(security): no bypass; fixed: IPv6 /64 grouping and no entries from mere checks, global counters
outside the evictable table, all `X-Forwarded-For` lines and ports, the body cap, a passcode with
surrounding whitespace that could never match (bug), search 6 -> 2/min, assist pre-check, tests
for each. Moved to Milestone 8: verify Render's proxy chain before setting the hops, uvicorn proxy
headers, `/docs`. Accepted: a burst of concurrent guesses can slightly exceed 5. qa-checker: all
clean (697 tests at that point). 716 backend tests after the fixes.

Step 8 (2026-11-20): measured first: FastAPI refuses `text/plain`, url-encoded, multipart and
missing content types with 422 before the route runs. No CORS middleware; `OriginCheck` refuses
POST/PUT/PATCH/DELETE from origins not in `ALLOWED_ORIGINS` (and any request with two Origin
headers) before the body is read. Real servers: a page POST through `next dev` passed (Next forwards
the browser's Origin), evil and `null` origins 403, `text/plain` 422, preflight 405 with no CORS
headers. code-reviewer: no bypass; applied: duplicate Origin refused, tests for other methods, the
order before the body cap and the preflight status, a fail-closed note in `.env.example`. Milestone 8
must verify Vercel's rewrite forwards Origin and add the deployed origin. 761 backend tests.

For step 11 (owner decision 2026-11-20: left for the release checks): tests for the recorder's
command-line entry point (`--only` with an unknown id, Qdrant closed in `main`) and for a leftover
temp file after a failed write; a frontend test that leaving the page aborts the footer's health
request.

Step 9 (2026-11-21): backend (commit 89845b1): `POST /api/live/check` checks the passcode, the key's
shape and the key itself (a free models-list call) and returns a 12 h token, an HMAC over expiry,
passcode and a hash of the key; every error body carries a `code`; `/api/health` has
`search_enabled`. Frontend: the core (key in module memory only, token in sessionStorage plus an
in-memory copy, credentials on model routes only, 401s mapped by code) was reviewed and given its
own tests, then two gaps fixed before the screens: a blocked sessionStorage lost the token entirely,
and the panel could not tell why it reopened (now `refusal`). Screens by engineer from DESIGN.md
decisions 7-12. Choices the design left open: Job and Plan show their single recording at once in
demo only (a one-row picker in local and live, so a live result is not replaced); resume import in
demo shows "Importing a resume needs a model, and this site runs in demo mode..."; a plan run is
resumed after a reload only in local mode or in live mode with a key. After the review, also beyond
the design: a passcode or key with characters a header can't carry is refused locally ("A passcode
uses only letters, digits and keyboard symbols, with no spaces."); a passcode lockout shows the
Retry-After countdown and disables "Use live mode" until it ends; the recordings picker is disabled
while a live run is going. The bound-token copy: "The remembered passcode no longer works with this
key (it works only with the key first used with it, until the server restarts). Enter the passcode
again."
code-reviewer: no key-handling issue; fixed: a 401 with an unknown code passed silently (now drops
both values and the panel explains it), picking a recording during a run hid the run, a refusal
followed the visitor to the next page (and pulled focus), non-ASCII header values became a
misleading "can't reach the server", the lockout ignored Retry-After, Search imported the whole Ask
screen for its examples. qa-checker: secrets, attribution, debug leftovers, storage and header
greps, control characters: all clean. 787 backend + 286 frontend tests; lint, typecheck, build pass.
Browser check through `next dev`: demo (badge, mode notes, recordings on Ask/Job/Plan with the strip
and read-only inputs, `/search` with plain-text excerpts and the route preview, no console errors);
live with a throwaway passcode and a made-up key (wrong passcode -> field error and focus; right
passcode -> "Anthropic refused this API key", key field emptied and focused, nothing in
sessionStorage, the key nowhere in the page; server log names the error type only; the refusal does
not follow to /plan). Not checkable: the key-set strip and a real model run (no paid key, zero-cost
rule).

Step 10 (2026-11-21): `evaluation/answer_cases.jsonl` (20 cases; facts taken from the indexed
pages, owner-approved), `evaluation/answer_eval.py` (scored in code, `--rescore`, `--only`,
`--no-grounding`) and `evaluation/grounding.py` (one Haiku call per answer, per-claim verdicts,
arithmetic in code), by engineer; lead change: a refuse case whose judge finds no claims fails as
"not checked" instead of passing. 803 backend tests, ruff clean. Real run from the owner's Terminal
panel (Claude Code on the Pro plan, 20 Voyage queries): 12/14 answer cases, 6/6 refusals, 159/166
claims supported, 24 s per case; details and the two retrieval-caused failures in EVALUATION.md.
Follow-up in TASKS.md: answers add advice not in the evidence.

Step 11 (2026-11-21), release checks:
- Leftover tests (owner, 2026-11-20): recorder `--only` with an unknown id exits before opening
  any service; Qdrant is closed when recording fails; a failed write leaves no temp file and keeps
  the old recording (`save` now removes its temp file on failure); a leftover `.json.tmp` is
  ignored by the library and overwritten; the shared health request is aborted when the page
  unmounts (it moved from the footer to `ServerInfoProvider` in step 9). `dd37ad4`.
- Secret scan of the branch diff (21 commits), commit messages, logs and `demo_runs/`: no keys,
  personal data or local paths (one hit: the made-up `C:\Users\someone` in a scan test); no AI
  attribution; single author; no `.env`, `private/` or log tracked. The live check's test key and
  passcode appear in no log or file.
- Demo mode with no keys at all: a launcher with no `.env` and every key removed: health answers
  (`search_enabled: false`), 8 recordings served, chat/jobs/runs and the live check 403
  `demo_mode`, search 503 `search_off`.
- Visitor key never in logs, traces or responses; tracing off for visitor requests: covered by
  `test_visitor_key.py` (a full request at DEBUG logs nothing with the key; refused keys get fixed
  text) and `test_tracing.py` (deployed modes never trace; a visitor key is refused while tracing
  is on); the step 9 browser check saw the same from outside.
- SECURITY.md checklist: request bodies Pydantic with `extra="forbid"` (incl. `SearchRequest`);
  no exception text in responses or logs; model and retrieved text only through the delimiting
  helpers (also the new grounding judge); no model tools (`tools=[]`), structured outputs
  validated; limits in place; `uvx pip-audit`: no known vulnerabilities (104 pinned packages);
  `npm audit`: 0. From Milestone 6: model text as text, links http(s) only (step 9 review). From
  Milestone 7: auth on model routes (passcode + token), per-IP limits, Origin check instead of
  CORS (step 8), visitor key never logged or traced, demo with no keys: all checked above. The
  Milestone 8 and live-deploy lines (HTTPS, headers, proxy chain, one worker) belong to the deploy.
- Retrieval eval: unchanged (EVALUATION.md, 2026-11-21). Answer eval: see step 10 and T-019.
- 808 backend + 287 frontend tests; lint, typecheck, build clean.

Release review (code-reviewer, whole branch, focus on steps 10-11 and T-019) and QA:
- Fixed: `test_real_chunk_ids_load` failed on CI (`knowledge_base/processed/` is gitignored, so
  a fresh clone has no chunks); it now skips there. CI had been red on `225e8f6` and `dd37ad4`
  without the lead noticing; checked after every push from here.
- Fixed: generic must-contain phrasings narrowed ("the original", "versions", "check in",
  "duplicate", "miss", "slow"); both saved runs re-score identically (12/14). Curly apostrophes
  now match straight ones. `--only` with an unknown id is a clean error; result files carry
  seconds in their names.
- Fixed (passcode area, re-reviewed: no probe, no lock bypass, lock still checked first): a
  session token sent without a key got `passcode_required` and counted toward the IP lock; it now
  gets 401 `key_required` and does not count.
- Kept: a refuse case answered in full with every claim supported passes as "grounded partial"
  (the documented intent). QA: no failing checks, 287 frontend tests stable over 3 runs, no
  secrets, attribution, debug leftovers or control characters. For the owner: commit metadata
  carries the owner's personal email (as on `main` before).
- 809 backend + 287 frontend tests.

Then the PR to `main`.

# SECURITY.md
GradPath's own threat model: for each threat in the owner's reference guides
([`../security/`](../security/README.md)), whether it applies here, what defends against it today
(with the file), what is missing, and when that gets done. The guides explain the threats; this file
applies them. Architecture is in [ARCHITECTURE.md](ARCHITECTURE.md), open work in
[`../work/TASKS.md`](../work/TASKS.md).

Written 2026-11-18 (Milestone 4) from the code on `feat/t-006-router-fallback`. Update it when a
milestone changes the attack surface (login, uploads, frontend, deploy).

**Principle (from the guides):** the model is not the security boundary. Limits, ids, routes,
statuses and permissions are decided in our code; the model only fills validated fields.

## Attack surface today
- **API** (`api/`): `/api/chat`, `/api/jobs/analyze`, `/api/assist`, `/api/career/prepare`,
  `/api/career/runs` (start) and `/api/career/runs/{id}` (poll), `/api/profile/from-resume`,
  `/api/health`, `/api/demo`, `/api/demo/{id}` and `/api/search` (T-018: no model call, the owner's
  Voyage key, per-IP limited); live routes behind a passcode; no cookies, no CORS middleware, an
  Origin check on POSTs (T-018 step 8); not deployed. Runs on the owner's PC.
- **Frontend** (`frontend/`, Milestone 6): Next.js pages that call same-origin `/api/*`, which Next
  forwards to the API, so the backend address stays server-side. The profile and the last plan stay
  in the browser (localStorage / sessionStorage) and leave it only inside a request the visitor makes.
- **Model calls**: Claude through Claude Code (local, Pro plan) or the Anthropic API; Voyage for
  embeddings. Three external services receive data: Anthropic, Voyage, LangSmith (opt-in tracing).
- **Ingestion** (`ingestion/`): fetches approved URLs from `knowledge_base/source_manifest.csv`, run
  by the owner only.
- **Vector store**: local Qdrant in file mode (`backend/data/qdrant/`, no network port).
- **Modes** (T-018): `APP_MODE` local / demo / live, default demo. Outside local every model route
  answers 403 (`api/deps.require_model_routes`, deny by default); `/api/demo` serves recorded runs.
- **Not built yet**: visitor keys (7), deploy (8), file uploads (later; T-014 takes pasted resume
  text only).

Status key: ✅ defended · ⚠️ gap, fix now · 🕒 applies from a later milestone · — does not apply.

## 01 Web application threats

| Threat | Status | Where / defence today | Gap and when |
|---|---|---|---|
| SQL injection | — | No SQL database. Qdrant is queried through its client with typed filters, never string-built queries. | If a database is added (accounts, Later), parameterised queries only. |
| XSS | ✅ / 🕒 8 | API returns JSON only; model text is bounded (1,000 chars, router reason 200). The frontend (Milestone 6, release-checked 2026-11-20) follows the rules in the next column. | Keep these rules: render model and retrieved text as plain text (React escaping, no `dangerouslySetInnerHTML`, no raw-HTML markdown: only the safe subset in `frontend/lib/modelText.ts`, parsed to data and rendered as fixed React elements, links reduced to their text); links only `http(s)` and only `source_url` values from the manifest. Source search (T-018) returns retrieved excerpts: same rule, plain text only, links only from `source_url`. Still to do: a Content-Security-Policy on deploy (8). |
| CSRF | ✅ | No cookies or sessions; the live passcode and visitor key are custom headers a form can't set; FastAPI rejects every content type a form can send (measured: `text/plain`, url-encoded, multipart, none -> 422); `OriginCheck` refuses a POST whose `Origin` isn't in `ALLOWED_ORIGINS` (403, before anything runs); no CORS middleware, so cross-origin reads and preflights get no permission (T-018 step 8, `test_cross_site.py`, checked through `next dev`). | Milestone 8: add the deployed frontend's origin to `ALLOWED_ORIGINS` and check that Vercel's rewrite forwards the browser's `Origin` (if it drops it, requests arrive with none and pass, which is still safe; if it rewrites it, allow that value). Make a real POST through the deployed site and one with a forged foreign `Origin` through the Vercel URL (expect 403); preview-deployment URLs get 403 unless listed. |
| SSRF | ✅ | `ingestion/fetch.py`: only manifest URLs with status `approved`; robots.txt re-checked on every redirect hop; content-type allow-list; at most 5 redirects. Users can't submit URLs. | Fixed in T-007: every URL and redirect hop must be https on port 443 and a manifest host; private, numeric and localhost hosts refused. Known limit: no DNS check of a manifest host. |
| Path traversal | ✅ | `workflows/cli.py` `out_allowed`: a real profile's results only under `private/`; `evaluation/workflow_eval.py` `load_profile` refuses paths outside the repo. The API takes no file paths. | Uploads (7) must never use a client file name as a path. |
| Unsafe file uploads | 🕒 7 | No upload endpoint. | Before any upload: size limit, type from the file's signature not its name, parse in memory, never execute or serve back, never index into the shared collection. High-risk area in CLAUDE.md. |
| Remote code execution | ✅ | No `eval`, `exec`, `pickle`, `shell=True` or `yaml.load` in `src/` (checked 2026-11-18). Models have no tools (see 07 Excessive agency). | Keep it that way; the release secret scan can grep for these. |
| Insecure deserialization | ✅ | JSON only, parsed by Pydantic with `extra="forbid"` on every request body. | — |
| Security misconfiguration | 🕒 8 | Settings typed in `config.py`; secrets are `SecretStr`; `.env` gitignored. | Milestone 8: decide whether `/docs` stays public, set security headers, debug off, check Render/Vercel defaults. |

## 02 Authentication and access control

There are no accounts, logins or sessions today, so these threats have nothing to attack yet. They
become design rules for Milestone 7 (a passcode or token guarding the model routes).

| Threat | Status | Rule for Milestone 7 |
|---|---|---|
| Brute force, password spraying, credential stuffing | ✅ | No user passwords. The live passcode (T-018 step 7): 16+ characters enforced at startup, constant-time compare, 5 failures per IP in 15 min lock that IP, never logged or echoed (tested). Shared networks (T-020 step 2): a valid session token still passes while its IP is locked (it proves an earlier correct passcode and can't be guessed); passcodes, even right ones, and bad tokens wait out the lock; limit messages say "your network". |
| Session hijacking, session fixation | 🕒 7 | Prefer no sessions. If one is ever needed: `HttpOnly`, `Secure`, `SameSite=Strict`, a new id after login, short expiry. |
| Privilege escalation, broken access control | 🕒 7 | One role (visitor). Settings that cost money (revision limit, model choice) come only from server settings, never from the request: already true for `max_revisions` (`api/career.py`). |
| IDOR / BOLA | ✅ | Live mode (T-018 step 5): each run is bound to the key that started it (HMAC owner tag; another key gets the same 404 as an unknown id). Run ids (T-016): random uuid4, validated, not listable, the same 404 for unknown/expired/malformed; a run record never holds the posting or profile; the result (profile-derived reasoning) is kept in memory for 15 min after the run, at most 20 runs. Anyone holding a run id can read that result until it expires. Guide 02 says unguessable ids aren't access control: done for live mode (above); local mode stays unbound (one user). |

## 03 API security

| Risk | Status | Where / defence today | Gap and when |
|---|---|---|---|
| Input validation | ✅ | Pydantic schemas with bounds: resume text 100–15,000 (stripped), question 2,000, job description 50–20,000, profile 12,000 total, corrections 10 × 500, router message 3–2,000 (whitespace-only refused). | — |
| Mass assignment | ✅ | `extra="forbid"`; the workflow refuses node writes to protected keys (`workflows/graph.py` `_wrap`). | — |
| Excessive data exposure | ✅ | Fixed error messages (`api/main.py`); exception text never returned; results are typed response models. 422s carry only `loc`/`msg`/`type`: no `input` or `ctx`, unknown field names and non-identifier locations masked (`safe_validation_errors`, T-018 step 6). | — |
| Resource limits | ✅ | Concurrency caps (`api/limits.py`: chat 2, jobs 1, career 1, search 2, else 503); source search embeds without waiting or retrying (`ThrottledEmbeddings.embed_query_now`: a full Voyage window or a 429 answers 429 at once, one Voyage request at most, T-018); revision limit 0–3; recursion backstop. | Workflow time budget done (T-006: 300 s, then a labelled fallback); per-IP rate limits done (T-018 step 7, `api/ratelimit.py`). |
| Inventory | ✅ | Ten routes, all in `api/main.py` (resume import T-014; run start and poll T-016; `/api/demo` list and get and `/api/search`, T-018). `test_demo.py` fails if a route is added without being listed as open or guarded. | Keep the list in ARCHITECTURE.md current. |

## 04 Network and infrastructure

| Threat | Status | Defence / plan |
|---|---|---|
| DDoS, abuse of model routes | 🕒 7–8 | Concurrency caps now; per-IP limits and demo mode (no model calls) by default before deploy. Free tiers cap the damage: no payment method anywhere (owner rule), so nothing can bill. |
| MITM | 🕒 8 | HTTPS on Vercel and Render; Anthropic, Voyage and Qdrant Cloud clients use HTTPS. Ingestion: https only (T-007). |
| Exposed services | ✅ | Local Qdrant is a file, not a server; the API listens on localhost in development. |
| Supply chain | ⚠️ | Exact pins in `uv.lock`, `uv sync --locked` in CI, GitHub Actions pinned to commit SHAs. **No vulnerability scan of dependencies.** Proposed: `uvx pip-audit` (free) in the release checks. |

## 05 Database and data

| Threat | Status | Defence / plan |
|---|---|---|
| Data breach, exfiltration | ✅ | No personal data stored: the repo holds only fictional sample profiles; the owner's real data lives in `private/` (gitignored). Nothing is persisted per request. |
| Tampering, poisoning | ✅ | Only owner-approved, licence-checked sources (`source_manifest.csv`, `status=approved`); each chunk keeps its `document_id` and `source_url`; atomic rebuilds via an alias (T-005). Redirects can't leave the approved hosts (T-007). |
| Backups | ✅ | The index is rebuildable from the manifest and the embedding cache; code and labels are on GitHub. |
| Cryptography | 🕒 8 | Secrets only in `.env` locally and the hosts' environment settings when deployed; TLS in transit. |

## 06 Human and organisational

Solo project, so the realistic risks are a phished account or a leaked key.
- Two-factor authentication on GitHub, Anthropic, Voyage and LangSmith **(owner)**.
- Keys only in `.env`; the release checks scan diffs, logs, `demo_runs/` and commit messages.
- Ransomware or a lost PC: everything but `.env` and `private/` is on GitHub; keep your own backup of
  `private/`.

## 07 AI, LLM and RAG

| Threat | Status | Where / defence today | Gap and when |
|---|---|---|---|
| Direct prompt injection | ✅ | User text is data in delimited blocks (`workflows/prompting.py` `block()`, `rag/answer.py`); the router HTML-escapes the whole message and the model only names a `kind`, while code picks the route (`router/route.py`). Ids, statuses, pass/fail and limits are decided in code. Tested: `test_router.py`, the wf-004 injection eval case. | — |
| Indirect prompt injection | ✅ | Retrieved chunks and postings are wrapped and labelled as data; models have no tools, so injected text can only bend wording. | Fixed in T-008: untrusted text is NFKC-normalised and stripped of invisible format characters, and any tag opener (or a look-alike bracket) followed by one of our tag names is neutralised. |
| RAG poisoning | ✅ | See 05 Tampering: approved sources only, provenance per chunk, rebuild and rollback. | A diff review of changed chunks on re-ingest (Later). |
| Sensitive information disclosure | ✅ | No secrets in prompts. Logs record exception types only (router, workflow retry filter, API handlers). Tracing redacts and is off for visitors (`tracing.py`). Voyage receives questions and requirement text, not the profile; Anthropic receives the job description and profile (needed for the task). Resume import (T-014): the pasted resume goes to the fast model once, under `tracing_context(enabled=False)` (tested, also through `ChatClaudeCode`), is never logged or stored, and model/SDK errors are logged by type only; contact details are dropped by the prompt and scrubbed in code. | Live mode (T-018 step 5): the key travels in the `X-Anthropic-Key` header, is shape-checked, passed only to the model client and never logged, stored, traced or returned (tested in `test_visitor_key.py`); live refuses to start with a server key; the anthropic/httpx loggers are capped at WARNING. Still a release check on the deployed site. |
| Cross-tenant leakage | — | Single shared public corpus; no user documents are indexed. | Rule: uploads are never added to the shared collection. |
| Vector database attacks | ✅ / 🕒 8 | Local file store; only the ingest command writes. | Qdrant Cloud (8): key only on the server; use a read-only key for serving if the free tier offers one (check then). |
| Excessive agency | ✅ | No model has tools: `ChatClaudeCode` runs with `tools=[]`, `setting_sources=[]`, `max_turns=3` (`providers/claude_code.py`). Every output is a validated Pydantic model; nothing the model says triggers an action. | Keep: any future tool needs an allow-list and server-side checks. |
| Insecure output handling | ✅ | Outputs validated; ids filtered to known facts and chunks; model text bounded; the frontend renders it as text (see XSS). | — |
| Unbounded consumption | ✅ | Size limits, concurrency caps, revision limit, `max_turns`, one batched Voyage call per request; per-IP limits (T-018 step 7). The owner's Voyage key (T-020 step 2): every server-paid query embedding spends from a daily (300) and lifetime (20,000) budget stored in Qdrant, so restarts don't reset it, and search fails closed when it's spent (`retrieval/budget.py`); repeated questions reuse a cached vector keyed by a hash, with no query text stored (`retrieval/query_cache.py`); `SEARCH_ENABLED=false` turns public search off. | Time budget done (T-006). |
| System prompt leakage | ✅ | The prompts are public in the repo by design; none holds a secret or a rule that security depends on. | — |
| Model supply chain, theft, poisoning | — | Hosted models only; no model files, no fine-tuning. Libraries pinned (see 04). | — |
| Hallucination | ✅ | Answers only from retrieved evidence, citations checked in code, abstention below the 0.45 threshold, critic + revision, evaluations in EVALUATION.md. | Grounding check beyond citation ids (TASKS). |

## 08 Testing and operations
- **Tests:** injection cases in `test_router.py` and the workflow tests (`test_workflow_*.py`); eval case
  wf-004; routing labels rt-026 to rt-028.
- **Logging:** types and counts, never prompts or exception text; a route log comes in Milestone 4
  step 6.
- **Incident response (solo):** if a key leaks, revoke it at the provider first, then remove it from
  history; record what happened in a bug ticket.

## Release security checklist
From guide 09, narrowed to this app. Run before each release; the project's release checks in
`CLAUDE.md` point here.
- [ ] Every request body is a Pydantic model with bounds and `extra="forbid"`.
- [ ] No stack traces or exception text in responses or logs.
- [ ] Model and retrieved text enters prompts only through the delimiting helpers.
- [ ] Models have no tools; outputs are validated before use.
- [ ] Concurrency, size, revision and time limits in place.
- [ ] Secret scan: diff, logs, `demo_runs/`, commit messages; no `.env` tracked.
- [ ] `uvx pip-audit` clean (once adopted).
- [ ] From Milestone 6: model text rendered as text; links `http(s)` only.
- [ ] From Milestone 7: auth on model routes, per-IP limits, CORS allow-list, visitor key never
      logged or traced, demo mode works with no keys.
- [ ] From Milestone 8: HTTPS only, security headers, `/docs` decision, separate dev and prod keys.
- [ ] Live deploy, Voyage (T-020 step 2): the server uses its own revocable Voyage key; the
      budget numbers (`EMBED_BUDGET_DAILY`, `EMBED_BUDGET_TOTAL`) are set on purpose; a restart
      keeps the counts (check on the deployed site); the owner knows `SEARCH_ENABLED=false`.
      One server instance only: the counters are read once per UTC day and written back, so two
      instances (a second Render instance, a long deploy overlap) would overwrite each other's
      counts. Demo and live refuse a local Qdrant folder (`QDRANT_URL` required). Known limit:
      live-mode plans spend from the same daily budget (about one embedding per skill), so
      passcode holders can use up the day's public searches.
- [ ] Live deploy (T-018): exactly one uvicorn worker (the run store, run-owner secret and slots
      are per process); never `--log-level trace`; no proxy or platform log format that records
      request headers (`X-Anthropic-Key`); `ANTHROPIC_BASE_URL` / `ANTHROPIC_API_URL` unset (live
      refuses to start otherwise).
- [ ] Live deploy, proxy (T-018 step 7 review): check the real `X-Forwarded-For` chain on Render
      before setting `TRUSTED_PROXY_HOPS` (too low: every visitor shares one address and 5 wrong
      passcodes lock everyone out; too high: a client-written entry is trusted); run uvicorn so it
      does not rewrite the client address from the header itself (`--no-proxy-headers`, or no
      `FORWARDED_ALLOW_IPS=*`); decide `/docs`, `/redoc`, `/openapi.json` in demo and live.

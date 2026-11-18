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
- **API** (`api/`): `/api/chat`, `/api/jobs/analyze`, `/api/career/prepare`, `/api/health`; no login,
  no cookies, no CORS middleware, not deployed. Runs on the owner's PC.
- **Model calls**: Claude through Claude Code (local, Pro plan) or the Anthropic API; Voyage for
  embeddings. Three external services receive data: Anthropic, Voyage, LangSmith (opt-in tracing).
- **Ingestion** (`ingestion/`): fetches approved URLs from `knowledge_base/source_manifest.csv`, run
  by the owner only.
- **Vector store**: local Qdrant in file mode (`qdrant_storage/`, no network port).
- **Not built yet**: frontend (Milestone 6), demo/live modes and visitor keys (7), deploy (8),
  uploads (none planned before 7).

Status key: ✅ defended · ⚠️ gap, fix now · 🕒 applies from a later milestone · — does not apply.

## 01 Web application threats

| Threat | Status | Where / defence today | Gap and when |
|---|---|---|---|
| SQL injection | — | No SQL database. Qdrant is queried through its client with typed filters, never string-built queries. | If a database is added (accounts, Later), parameterised queries only. |
| XSS | 🕒 6 | API returns JSON only. Model text is bounded (1,000 chars, router reason 200) but **not** HTML-safe. | Frontend rules (Milestone 6): render model and retrieved text as plain text (React escaping, no `dangerouslySetInnerHTML`, no raw-HTML markdown); links only `http(s)` and only `source_url` values from the manifest; a Content-Security-Policy on deploy. |
| CSRF | 🕒 7 | No cookies or sessions, so a cross-site page has no credentials to ride on. | Milestone 7: keep auth out of cookies (header token or passcode per request); CORS allow-list of the frontend origin only; test that a cross-site `text/plain` form POST is refused (check FastAPI's JSON content-type handling then, not assumed). |
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
| Brute force, password spraying, credential stuffing | 🕒 7 | No user passwords. If a demo passcode is added: long random value, constant-time compare, per-IP rate limit and back-off on failures, never logged. |
| Session hijacking, session fixation | 🕒 7 | Prefer no sessions. If one is ever needed: `HttpOnly`, `Secure`, `SameSite=Strict`, a new id after login, short expiry. |
| Privilege escalation, broken access control | 🕒 7 | One role (visitor). Settings that cost money (revision limit, model choice) come only from server settings, never from the request: already true for `max_revisions` (`api/career.py`). |
| IDOR / BOLA | 🕒 6–7 | No stored per-user objects. When run ids appear (status polling, Milestone 6): random UUID4, not listable, results expire, nothing personal kept server-side. |

## 03 API security

| Risk | Status | Where / defence today | Gap and when |
|---|---|---|---|
| Input validation | ✅ | Pydantic schemas with bounds: question 2,000, job description 50–20,000, profile 12,000 total, corrections 10 × 500, router message 3–2,000 (whitespace-only refused). | — |
| Mass assignment | ✅ | `extra="forbid"`; the workflow refuses node writes to protected keys (`workflows/graph.py` `_wrap`). | — |
| Excessive data exposure | ✅ | Fixed error messages (`api/main.py`); exception text never returned; results are typed response models. | — |
| Resource limits | ✅ / 🕒 7 | Concurrency caps (`api/limits.py`: chat 2, jobs 1, career 1, else 503); revision limit 0–3; recursion backstop. | Workflow time budget (Milestone 4 step 5); per-IP rate limits (7). |
| Inventory | ✅ | Four routes, all in `api/main.py`. | Keep the list in ARCHITECTURE.md current. |

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
| Sensitive information disclosure | ✅ | No secrets in prompts. Logs record exception types only (router, workflow retry filter, API handlers). Tracing redacts and is off for visitors (`tracing.py`). Voyage receives questions and requirement text, not the profile; Anthropic receives the job description and profile (needed for the task). | Live mode (7): the visitor's key is never logged, stored or traced (release check). |
| Cross-tenant leakage | — | Single shared public corpus; no user documents are indexed. | Rule: uploads are never added to the shared collection. |
| Vector database attacks | ✅ / 🕒 8 | Local file store; only the ingest command writes. | Qdrant Cloud (8): key only on the server; use a read-only key for serving if the free tier offers one (check then). |
| Excessive agency | ✅ | No model has tools: `ChatClaudeCode` runs with `tools=[]`, `setting_sources=[]`, `max_turns=3` (`providers/claude_code.py`). Every output is a validated Pydantic model; nothing the model says triggers an action. | Keep: any future tool needs an allow-list and server-side checks. |
| Insecure output handling | ✅ / 🕒 6 | Outputs validated; ids filtered to known facts and chunks; model text bounded. | Frontend escaping (see XSS). |
| Unbounded consumption | ✅ / 🕒 7 | Size limits, concurrency caps, revision limit, `max_turns`, one batched Voyage call per request. | Time budget (M4 step 5), per-IP limits (7). |
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

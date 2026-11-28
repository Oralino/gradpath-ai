# T-020: Milestone 8, deploy
Milestone 8 ticket: the public site on free tiers. Plan and story in `../../MILESTONES.md`; modes and
deploy in `../../../engineering/ARCHITECTURE.md`; threats and the live-deploy checklist lines in
`../../../engineering/SECURITY.md`.

- **Type:** feature
- **Status:** in progress
- **Opened:** 2026-11-21 · **Closed:**
- **GitHub Issue:** none

## Summary
Deploy GradPath publicly at zero cost: Next.js on Vercel, FastAPI on Render, the index on Qdrant
Cloud. The site runs in live mode: visitors without the passcode see what demo shows (recordings,
source search); visitors with the passcode and their own Anthropic key use the full app.

## Decision
Owner decisions, 2026-11-21 (plan approved as recommended):
- **Mode: live.** Live shows everything demo does and adds the key panel; the owner shares the
  passcode only with chosen people. Rejected: demo only (nobody could try the real app online).
- **Voyage key on the server for search: yes** (decision of 2026-11-20), behind the limits below.
- **Order:** 0 free-tier check, 1 copy the index to Qdrant Cloud without re-embedding, 2 production
  backend + Voyage and shared-network protections, 2b the backend as a Docker image, 3 frontend on
  Vercel, 4 measure the proxy chain and set `TRUSTED_PROXY_HOPS`, 5 checks on the deployed site,
  6 README and docs, then the PR.
- **Voyage protections (step 2):** a site-wide search budget (daily and total) stored in Qdrant
  Cloud so restarts don't reset it, failing closed when spent (starting at 300 a day, a setting);
  a cache of question embeddings (identical normalised questions reuse one; the example
  questions embedded once); a separate Voyage key used only by the deployed server (revocable);
  `SEARCH_ENABLED=false` as an off switch. Rejected: a CAPTCHA (third-party script on every page;
  the budget caps the damage anyway); search behind the passcode (takes away the only live feature
  for visitors without a key).
- **Shared networks (step 2):** a household, office or university shares one IP. A valid session
  token passes even while the IP is locked for passcode guessing (the lock stops guessing; a
  valid token proves an earlier correct passcode and can't be guessed); wrong or forged tokens
  still count. Limit messages say "your network (this can include other people on the same
  Wi-Fi)". Per-IP numbers unchanged: the site-wide budget is the hard ceiling. Rejected: per-browser
  limits instead of per-IP (a browser id is free to throw away).
- **Qdrant Cloud idle rule:** rely on the suspension email and one-click reactivation; if the
  cluster is ever deleted, the step 1 copy script rebuilds it from the local index at no cost.
  Rejected: a scheduled GitHub Actions ping (a Qdrant key in GitHub secrets, a job forever).
- Accounts and every dashboard secret are created and pasted by the owner; the lead only gives
  the list of setting names.
- **Backend in Docker (step 2b, owner 2026-11-21):** the API ships as a Docker image that Render
  runs (Render's Docker runtime, free tier), so it runs the same on the owner's PC, in CI and in
  production, and the owner learns Docker on a real service. Plan, explained before building:
  - `backend/Dockerfile`: `python:3.13-slim`; uv from its official image; `uv sync --frozen
    --no-dev` from `uv.lock` (same pins as today); a non-root user; one uvicorn worker on Render's
    `$PORT` (runs live in memory, so never more than one worker).
  - `backend/.dockerignore`: keeps `.env`, `private/`, local Qdrant data, caches, tests and
    reports out of the image. Secrets reach the container only as Render environment variables,
    never baked into the image; the image holds no index (the deployed API reads Qdrant Cloud).
  - CI: a job in `.github/workflows/ci.yml` builds the image on every push and PR (GitHub's
    runners have Docker; free for a public repo); it builds only, never pushes to a registry.
  - Local run: optional, needs Docker Desktop (free for personal use; the owner installs it).
  - Checks: the image builds; `/api/health` answers from the container in demo mode with no keys;
    no secret or `.env` inside the image (`docker history`, a file listing); memory at idle and
    during a search stays well under Render's 512 MB; image size recorded.
  - Watch for: the API printed an "unauthenticated requests to the HF Hub" warning at startup,
    so something downloads from Hugging Face; find what and make sure the container doesn't
    depend on a download at every cold start.
  - Rejected: Render's native Python runtime (simpler, but nothing to run the same way locally
    or in CI, and no Docker learning); a Dockerfile for the frontend (Vercel builds Next.js
    itself); Docker Compose (one service only; Qdrant is a cloud service).

- **Client address (step 4, owner 2026-11-28):** the site's server vouches for each visitor's
  address with a shared secret, instead of trusting a count of proxy hops alone. The owner asked
  how other sites solve this; the standard answer (AWS's documented CloudFront pattern) is a
  secret header only the proxy adds. `frontend/proxy.ts` (Next.js Proxy, server only) sends
  `X-GradPath-Client-IP` and `X-GradPath-Proxy-Secret`; the API believes the address only when
  the secret matches. Owner requirement: the secret never reaches the browser (no `NEXT_PUBLIC_`
  name, never on a response, not in the build). Rejected: hops only (the public Render URL lets a
  direct caller forge the trusted entry); Vercel IP allow-list (no fixed outgoing IPs on Hobby);
  a private network (two companies). The temporary `/api/debug/forwarded` page (off unless
  `DEBUG_FORWARDED=true`) measured it.
- **Direct calls to Render (step 4, owner 2026-11-28): blocked (option C).** After the
  measurement the owner asked what other sites do. Options: A, keep `TRUSTED_PROXY_HOPS=0` (all
  direct callers share one bucket); B, `TRUSTED_PROXY_HOPS=3` (each direct caller by the address
  Render's Cloudflare added); C, refuse every call without the site's secret ("origin
  cloaking", AWS's documented pattern). Chosen: C (`SiteOnly`, health check exempt).
  `TRUSTED_PROXY_HOPS` stays 0. Rejected: B (hop counts break silently when a provider changes
  its chain; Render doesn't document it), A (lead's first recommendation; weaker than the
  standard). Consequences: `/docs`, `/redoc`, `/openapi.json` are unreachable on the deployed
  site (that SECURITY.md decision is settled); a mismatched secret takes the site down (403
  `site_only`) until both dashboards match.
- **Changing the secret without an outage (owner 2026-11-28): rejected for now.** Option: a
  `PROXY_SHARED_SECRET_PREVIOUS` that Render also accepts while the owner switches Vercel to the
  new value (set previous + new in Render, then Vercel, then delete previous). Rejected because
  today's gap is 1-2 minutes on a low-traffic site and the secret will rarely change; during the
  switch two secrets work, and a forgotten "previous" keeps an old value alive; and it doesn't
  help the case that matters most, a leaked secret, which must die at once anyway. Reconsider
  as its own ticket if the site gets steady traffic.

## Step 0: free-tier terms (checked 2026-11-21, from the providers' pages)
| Service | Free, no card | Limits that matter |
|---|---|---|
| Render web service | yes | spins down after 15 min idle, about 1 min to wake; 512 MB; 750 instance hours a month; may restart any time; bandwidth overage suspends for the month |
| Qdrant Cloud | yes | 1 node, 1 GB RAM, 4 GB disk; suspended after a week unused, deleted about three weeks after the notice unless reactivated |
| Vercel Hobby | yes | a proxied (external rewrite) request may take at most 120 s; over the free usage the project is paused, no paid overage |
| Voyage | yes | 200M free tokens for voyage-4; the 3 RPM limit is observed on the owner's account, not stated in the docs |
Consequences: Voyage abuse is a small risk (about 20 tokens a search); Render restarts make an
in-memory budget useless, hence the Qdrant-stored budget; the 120 s limit is fine because plans run
in the background with short polls; the cold start needs a visible "Waiting for the server..." state.

## Changes
- Branch: `feat/t-020-deploy`
- PR:
- Files touched (step 2): `retrieval/budget.py`, `retrieval/query_cache.py`,
  `retrieval/guarded.py` (new), `retrieval/service.py`, `config.py`, `api/main.py`,
  `api/search.py`, `api/deps.py`, `api/ratelimit.py`, `backend/Dockerfile`
  (`--no-proxy-headers`), tests `test_embed_guard.py` (new) and `test_live_check.py`;
  ARCHITECTURE, WALKTHROUGH, SECURITY, MILESTONES.
- Files touched (step 2b): `backend/Dockerfile`, `.dockerignore`, `.gitattributes` (all new),
  `.github/workflows/ci.yml` (`docker` job), CLAUDE.md and README (Docker commands),
  ARCHITECTURE (Container), WALKTHROUGH (The API as a Docker image).
- Commits (hash, message): `7777054` docs: plan the backend Docker image and move the ticket to
  in-progress (T-020); `21f7573` feat: package the API as a Docker image and build it in CI
  (T-020); `29e93a9` docs: explain the API Docker image and how to run it (T-020); `ba117e5`
  fix: let the image check tolerate unreadable folders (T-020).

## Verification
Step 5 (2026-11-28), checks on the deployed site (in progress):
- Release checklist, code: every request body is a Pydantic model with `extra="forbid"` and
  bounds (corrections: 500 characters, at most 10); responses carry fixed text, never exception
  text; models have no tools; untrusted text enters prompts through `block()` /
  `neutralise_tags` (system prompts are fixed text); no `dangerouslySetInnerHTML`; model and
  source links pass `safeExternalUrl`; nothing logs headers or keys; the Dockerfile runs one
  worker with `--no-proxy-headers`. Secret scan of the branch diff, commit messages and
  `demo_runs/`: clean; only `.env.example` tracked.
- Render logs, last 7 days (server-side search, control `GET /api/health` = 50 lines): no
  `sk-ant`, `lsv2_`, `Bearer`, `x-anthropic-key`, proxy secret, `code=`, `Traceback`, ERROR or
  WARNING lines.
- HTTPS: `http` answers 308 to `https`; `Strict-Transport-Security` (2 years, preload) on pages
  and the API. No other security headers yet (decision pending).
- Memory: Render's free plan shows no memory graph (paid plans only). No out-of-memory or crash
  event across every deploy and today's searches.
- Vercel's 120 s limit: RAG answers take about 6 s (EVALUATION.md); plans run in the background
  with short polls.
- Restart keeps the budget: stored counts read with a read-only script (counts only). A new
  search made today 1; after the owner's manual restart, the next new search continued from the
  stored count (today 52: the 50 in between came from the eval run, see EVALUATION.md).
- Scanners: `pip-audit` on the runtime requirements: no known vulnerabilities. `npm audit`:
  0. Trivy 0.57.1 on the API image (`python:3.13.18-slim-trixie`, Debian 13.7): 0 CRITICAL, no
  Python package findings; 55 HIGH, 106 MEDIUM, 79 LOW, 15 unknown, all Debian base packages;
  of the HIGH, only `zlib1g` and `libzstd1` have a fixed version, the rest none yet (most in
  tools the API never runs: util-linux, login, systemd-homed).
- Retrieval eval on the deployed index: unchanged (EVALUATION.md, 2026-11-28).

Step 4 (2026-11-28), shared-secret client address, before deploy:
- Files: `api/ratelimit.py` (`from_site`, `client_ip`), `api/debug.py` (new), `api/main.py`
  (start check: `PROXY_SHARED_SECRET` 32+ printable characters when set), `config.py`,
  `.env.example`, `frontend/proxy.ts` (new); tests `test_proxy_secret.py` (new),
  `test_rate_limits.py`, `frontend/proxy.test.ts` (new).
- Backend 912 passed, 1 skipped; ruff clean. Frontend lint, typecheck, build, new tests 8/8.
- Local end-to-end (`next build` + `next start` with a dummy secret and a stand-in API that
  echoes headers): the dummy secret is nowhere in `.next/static` or `.next/server`; a browser's
  forged `X-GradPath-Client-IP` and secret were dropped and replaced; the stand-in API got both
  headers; the browser's response headers held no secret. Locally `next start` does not
  overwrite `X-Forwarded-For` (the caller's own value was used), so the deployed check must show
  that Vercel does.
- qa-checker: ruff format, 316 frontend tests, secret and attribution scan, no `NEXT_PUBLIC_`
  name, no debug leftovers or control characters: all pass.
- code-reviewer: no way found for a browser or a direct caller to get a chosen address trusted,
  no secret leak in the code. Taken: `proxy.ts` treats a badly shaped secret as unset (a stray
  character would have made every /api request fail), warning once without the value; the
  API refuses a weak `PROXY_SHARED_SECRET` in every mode, not only live; one warning (no
  values) when the secret matches but the address is unusable. To check on the deployed site
  (it can't be seen locally): no `x-middleware-*` header and no secret on responses through
  Vercel; exactly one `X-Forwarded-For` entry arriving at `proxy.ts`. Not taken: putting the
  debug page behind sign-in (it shows only the caller's own request and is off by default).
  Known limit: a CDN put in front of Vercel later would make every visitor share one address
  (fails closed: a shared limit, never a bypass).
- After the fixes: backend 914 passed, 1 skipped; frontend proxy tests 10/10, lint, typecheck.
  Commits `dd25ff9`, `dcd565f`; CI green on `dcd565f`.
- Deployed measurement (2026-11-28; the owner set `PROXY_SHARED_SECRET` in Render and Vercel,
  Vercel Production only, and `DEBUG_FORWARDED=true` for a few minutes; the lead never saw the
  value). Through the site, from the owner's browser: `proxy_secret_matches: true`; the API's
  rate-limit key was the owner's real public IP, the same with a forged `X-Forwarded-For:
  6.6.6.6`, a forged `X-GradPath-Client-IP` and a guessed secret (both dropped by `proxy.ts`).
  `X-Forwarded-For` at Render: 4 entries [the browser's own value or Vercel's view of it,
  Vercel's outgoing server, Render's Cloudflare, Render's internal 10.x proxy]: the forged
  `6.6.6.6` arrived first, so Vercel passes the browser's header through on an external rewrite
  and no hop count is safe through the site. Responses through the site carry no
  `x-middleware-*` and no `x-gradpath-*` header. Straight at the Render URL (curl, from the
  owner's PC): a forged `X-GradPath-Client-IP` and a guessed secret were ignored; the chain had 3
  entries [caller, Cloudflare, internal] plus any forged ones on the left, so hops 3 named the
  real caller. `DEBUG_FORWARDED` then removed: the page answers 404 through the site and
  directly. The owner's IP is not recorded here.
- Option C built (`SiteOnly` in `api/main.py`; tests in `test_proxy_secret.py`; a conftest
  fixture keeps a developer's `.env` secret from turning the guard on for the whole suite).
  qa-checker: targeted tests 3 runs, no flakes; no secrets, attribution or control characters;
  CI's Docker smoke test calls only `/api/health` and sets no secret. code-reviewer: no bypass
  found (trailing or double slashes, case, encodings, `OPTIONS`, `HEAD` all get 403; body never
  read before the check). Taken: `proxy.ts` now sends the secret even when it can't measure the
  address (else that visitor would be refused); one warning (no values) when a request carries
  a wrong secret, the sign of a Render/Vercel mismatch; the site shows "The site can't reach its
  server right now" for `site_only` instead of the API's "use the website" text; the unused
  `HEAD` exemption dropped; more tests. Backend 936 passed, 1 skipped; frontend 319 passed,
  lint, typecheck. Commits `8941e5e`, `fedebf3`; CI green on `fedebf3`.
- Deployed (2026-11-28, Render and Vercel on `fedebf3`): straight at the Render URL `/api/demo`,
  `/docs`, `/redoc`, `/openapi.json`, `/api/auth/me`, `/api/debug/forwarded` and a search POST
  get 403 `site_only`; `/api/health` 200. Through the site: health, demo and `/api/auth/me` 200,
  the sign-in link redirects to GitHub, a real source search returns hits; `/docs` 404 (the site
  has none). `TRUSTED_PROXY_HOPS` stays unset (0). Step 4 done.

Step 3 (2026-11-27), deploy on Render and Vercel (the owner made the accounts and pasted every
value; the lead checked setting names and value shapes only, never values):
- **Render** web service `gradpath-ai`: Docker runtime, `backend/Dockerfile`, build context the
  repo root, branch `feat/t-020-deploy` (switch to `main` after the milestone merges), region
  Virginia (closest to the Qdrant cluster in AWS `ca-central-1`), Free instance (one instance),
  health check `/api/health`, auto-deploy on commit, no build filters. Environment: `APP_MODE`,
  `LLM_PROVIDER`, `LIVE_PASSCODE`, `VOYAGE_API_KEY` (the server-only `gradpath-server` key),
  `QDRANT_URL`, `QDRANT_API_KEY`, `LANGSMITH_TRACING=false`, then `ALLOWED_ORIGINS`; no
  `ANTHROPIC_*`. Values checked before deploying with a script that reported only yes/no
  (exact for the three public values; passcode length and characters; `pa-` and `https://`
  prefixes; no quotes or spaces).
- First deploy of `38b3fed`: build 2 min 21 s, startup about 1 s. `/api/health`: `app_mode:
  live`, `llm_provider: anthropic_api`, `search_enabled: true`, sources dates present.
- **Vercel** project `gradpath-ai` (Hobby): root `frontend`, Next.js preset, branch `main` (its
  `frontend/` was identical to the deploy branch's then; since T-026 the production branch is
  `feat/t-020-deploy`, like Render's, until the milestone merges), `GRADPATH_API_URL` = the Render URL,
  `NEXT_TELEMETRY_DISABLED=1`. Build 34 s. Production domain `https://gradpath-ai-phi.vercel.app`;
  HTTPS with `Strict-Transport-Security`.
- Through the site: `/api/health` and `/api/demo` 200; before `ALLOWED_ORIGINS`, a search POST
  with the site's `Origin` got 403 `cross_site` (so Vercel's rewrite forwards the browser's
  `Origin` unchanged); after it, 200 with passages. A forged `Origin` and a preview-deployment
  `Origin` both get 403.
- In the browser: a recorded example (Kubernetes liveness, partial answer with sources), source
  search ("What makes an API endpoint idempotent?", 2 passages), the live panel shown.
- Live mode: a wrong or missing passcode gets 401 `passcode_required` before any Anthropic call.
  The owner entered the real passcode and a fake key of the right shape: the passcode passed and
  Render's call to Anthropic was refused ("Anthropic refused this API key"), so the whole path up
  to Anthropic works. **Not checked:** a full answer with a real key (the owner has no Anthropic
  API key: zero-cost rule).
- Render's logs (searched server-side for `sk-ant`, the fake key, `passcode`; read in full after
  the first deploy): no key, passcode or token; only request lines and `AuthenticationError on
  /api/live/check`.
- Seen for step 4: every request reaches the app from `127.0.0.1` (`TRUSTED_PROXY_HOPS=0`), so all
  visitors share one rate-limit and passcode-lock bucket. The lead's two test searches spent the browser's
  "two searches a minute". Step 4 measures the chain and sets the hops. `/docs` is public (200): the
  SECURITY.md decision is still open.

Step 2 (2026-11-27), backend protections:
- Built as designed: `GuardedEmbeddings` (cache, then budget, then Voyage) wraps every query
  embedding outside local mode; the budget (300 a day, 20,000 in all) and the cache live in
  Qdrant; `SEARCH_ENABLED`; a valid token passes a locked network; "your network" wording.
- Found while building: LangChain's vector store embedded a probe text with Voyage at every
  start, outside any budget; turned off (`validate_collection_config=False`).
- code-reviewer: no blocker; guard covers search, RAG, job analysis and the workflow; the
  passcode change has no abuse path. Taken: refunds only for a single question refused at no
  cost (`WindowFull`, Voyage 429), since a failed batch may have paid; demo and live refuse a
  local Qdrant folder; one-instance and live-spends-the-public-budget limits in SECURITY.
  Not taken: mapping Qdrant errors to 503 (same as today's search), reloading counts before
  every spend (one more round trip per question; one instance covers it).
- qa-checker: 847 tests, the new tests 5 times in a row (no flakes), no secrets, no query
  text in any log or payload. Docstrings left off trivial `__init__`s and one-liners.
- After the fixes: 850 passed, ruff clean. Real check on the owner's Qdrant Cloud in
  throwaway collections (deleted after): a vector-less collection works, the daily cap holds
  across a restart, a refund is saved, a respelled question hits the cache, payloads hold
  only counts, the day and the model name.

Step 1 (2026-11-27), the owner's Qdrant Cloud cluster (free tier):
- `.env` checked without printing values: `QDRANT_CLOUD_URL` is https on `*.cloud.qdrant.io`,
  the key is set, `QDRANT_URL` stays empty; a read-only call found the new cluster empty.
- `copy_index --dry-run`: 1,700 local points. `copy_index`: 1,700 copied and checked (ids match
  exactly, sampled payloads and vectors equal). No Voyage tokens.
- Retrieval eval against the cloud (one Voyage call, `retrieval-20261127-215553.json`): every
  summary number equals the local run of 2026-11-21 (Recall@5 0.961, Precision@5 0.605, MRR
  0.987; 97% covered kept, 67% uncovered rejected), every question ranks the same chunks in the
  same order, scores differ by at most 0.0001. Search takes about 67 ms per question from the
  owner's PC (3 ms locally): the network round trip.

Step 2b (2026-11-22), CI run 44982475342, `docker` job green (backend and frontend jobs green too):
- The image builds from the repo root in about 50 s on a cold runner.
- Inside the image: no `.env` file anywhere, no `private/`, local data, tests, frontend or uv; no
  key-like strings under `/app`; runs as uid 10001.
- The Voyage tokenizer loads with networking switched off (`--network none`).
- Started with no keys, the API answers `/api/health` in demo mode (`search_enabled: false`);
  memory at idle 204 MiB (Render free limit 512 MB). Memory during a search is measured in step 5,
  once the deployed service has its keys.
- Image size: 338 MB compressed, 1.27 GB unpacked. Most of it is libraries the deployed API
  doesn't use (the bundled Claude Code CLI in `claude-agent-sdk`, fastembed and onnxruntime for the
  evals); trimming them is a possible later change, not needed for the free tier.
- code-reviewer: no blocking issue; taken: a stricter secret scan, `demo_runs/*.json` only, the
  model name read from settings, a faster failing health loop, precompiled code. qa-checker:
  secrets, attribution, YAML, allowlist paths, lockfile and ruff all pass (actionlint not run).
- Not checked locally: Docker isn't installed on the owner's PC (Docker Desktop is optional).

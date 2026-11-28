# T-026: Sign in with GitHub replaces the live passcode
Live mode's gate. Part of Milestone 8 ([T-020](T-020-deploy.md)); the flow is described in
`../../../engineering/ARCHITECTURE.md` (live mode), threats in `../../../engineering/SECURITY.md`.

- **Type:** change
- **Status:** in progress
- **Opened:** 2026-11-27 · **Closed:**
- **GitHub Issue:** none

## Summary
Live mode (the visitor's own Anthropic key) was gated by a shared passcode (T-018 step 7). The owner
found sharing it a chore (2026-11-27). The gate itself stays, because live mode spends the owner's
Voyage key on embeddings; it becomes "Sign in with GitHub".

## Decision
Owner decisions (2026-11-27), from options A (no passcode, the key is the pass), B (GitHub sign-in)
and C (visitors bring a Voyage key too): **B**, with
- GitHub accounts at least **30 days** old (younger: refused, against throwaway accounts);
- **anyone** old enough, plus an optional block list (`GITHUB_BLOCKED_USERS`);
- a sign-in lasts **1 day** (`SESSION_TTL_S`).

Design (lead):
- **GitHub OAuth App**, web flow with **PKCE** (S256) and **no scopes**: the server reads the public
  `id`, `login` and `created_at` once and drops the GitHub token. Rejected: a GitHub App (more setup,
  nothing gained for identity only).
- **No database:** `gp_session` = base64url(JSON {exp, id, login}) + HMAC-SHA256(SESSION_SECRET,
  purpose|body). HttpOnly, Secure, SameSite=Lax, Path=/, 1 day. The sign-in's state and PKCE
  verifier live in a second signed cookie (`gp_oauth`, 10 minutes, Path `/api/auth/github`); the
  purpose string keeps one cookie from passing as the other.
- **Fixed redirects** built from `PUBLIC_SITE_URL` (`/?signin=ok|too_new|blocked|denied|failed`):
  no caller-supplied address, no open redirect.
- **Per-user limits** (`gh:<id>`) on model, workflow and poll, on top of the per-IP ones; runs are
  bound to the GitHub user and the key. The passcode lock is gone: a forged cookie costs nothing and
  locks no one out.
- **Logs:** outcomes only; uvicorn's access line for `/api/auth/` hides its query string
  (`RedactAuthQuery`), because the callback's `code` and `state` sit there (found by a test).
- `/api/live/check` stays as the free key check, now behind the session, and issues nothing.
- Rejected: accounts with email and password (personal data, password storage, a sign-up wall for
  employers); option A (no control over who uses live mode); option C (two keys for visitors).

## Changes
- Branch: `feat/t-020-deploy` (Render deploys from it; part of the Milestone 8 PR)
- PR:
- Backend: `api/auth.py` (new), `api/deps.py`, `api/live.py`, `api/ratelimit.py`, `api/main.py`,
  `config.py`; tests `test_auth.py` (new), `test_live_check.py`, `test_rate_limits.py`,
  `test_visitor_key.py`, `test_demo.py`.
- Frontend (built in a side session from the lead's API contract): `lib/liveSession.ts`,
  `lib/api.ts`, `lib/types.ts`, `components/LivePanel.tsx`, `components/SignInNotice.tsx` (new),
  `ModeBadge.tsx`, `ModeNote.tsx`, `app/layout.tsx` and the affected tests.
- Docs: REQUIREMENTS, ARCHITECTURE, SECURITY, WALKTHROUGH, TASKS, `.env.example`.
- Commits (hash, message):

## Verification
- Backend: 897 passed, 1 skipped; ruff clean. `test_auth.py` runs the whole flow against a fake
  GitHub (`httpx.MockTransport`): state mismatch, missing, foreign or expired sign-in cookie, PKCE
  verifier and secret sent, accounts of 29, 29.9 and 31 days, blocked users, refused or broken code
  exchanges, odd profiles, caller-supplied redirects ignored, nothing identifying logged, the access
  log redacted, per-IP sign-in limit, live-only routes, tampered and long-lived signatures.
- Frontend: lint, typecheck, 305 tests, build.
- qa-checker: all pass; no secrets, attribution or debug leftovers.
- code-reviewer: no critical flaw. Taken: `/api/live/check` checks the session before counting the
  model limit (an anonymous caller could spend a shared network's limit; new test); the GitHub
  client ignores proxy and certificate environment variables (`trust_env=False`); the unverified
  API version header removed; "Signed in" shown only after `/api/auth/me` confirms it (frontend).
  Not taken, recorded as known limits: sign-out deletes the cookie but a copied cookie stays valid
  for its day (blocking by numeric id, or a new SESSION_SECRET, cuts it off); the GitHub token is
  not revoked (the OAuth App's expiring tokens die in 8 hours; no token is kept); `__Host-` cookie
  prefix (would break testing live mode over http on localhost); a weak-but-long SESSION_SECRET
  passes the start check (Render's Generate makes a random one).
- Deployed (2026-11-27): CI green on `09e8744` (backend, frontend, docker); Render live on it with
  the four GitHub settings (names checked in the dashboard, values never read). The Vercel project
  had been paused (503 `DEPLOYMENT_PAUSED`; the owner resumed it) and still built `main`, the old
  passcode frontend: its production branch is now `feat/t-020-deploy` (switch back after the
  milestone merges) and `09e8744` was redeployed to production. The site shows "Sign in with
  GitHub" and no passcode; through Vercel, `/api/auth/me` answers `{"signed_in": false}` and
  `/api/auth/github/login` answers 302 to GitHub with the production callback and sets `gp_oauth`
  (HttpOnly, Secure, SameSite=Lax, Path `/api/auth/github`).
- **Still to check (owner):** delete `LIVE_PASSCODE` in Render; one real sign-in on the site (the
  303 back and `gp_session` passing Vercel's rewrite), `/api/auth/me` showing the login, sign-out,
  and Render's logs free of code, state, login and id.

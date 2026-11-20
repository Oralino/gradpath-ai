# T-013: /api proxy cuts requests at 30 s
The frontend's `/api` proxy gave up on slow backend requests. Index: `../TASKS.md`, `../DONE.md`.

- **Type:** bug
- **Status:** done
- **Opened:** 2026-11-20 · **Closed:** 2026-11-20
- **GitHub Issue:** none

## Summary
Found while checking T-012. An `/api/assist` request that waited on Voyage's free-tier rate limit
came back as a plain-text 500. The Ask screen showed its generic server error. The Next log said
`Failed to proxy http://127.0.0.1:8000/api/assist Error: socket hang up`. Every preparation run
(80-300 s) from the Ask screen would hit the same limit.

## Cause
`next.config.ts` forwards `/api/*` to FastAPI with `rewrites()`. Next's proxy for external
rewrites has a 30-second timeout by default: `proxyTimeout || 30000` in
`next/dist/server/lib/router-utils/proxy-request.js`, set by `experimental.proxyTimeout`. Step 1
of T-011 had noted this risk but had not verified it.

## Decision
- Set `experimental.proxyTimeout` to 330 s. That is above the backend's run budget
  (`workflow_time_budget_s`, default 300 s), so the backend's own "stopped early" result always
  arrives before the proxy gives up. It is also above `DESIGN.md`'s 320 s client cut-off.
- This is a stopgap until run polling (TASKS) makes every request short. The setting is
  `experimental`, so check it on each Next upgrade.
- Rejected:
  - Calling FastAPI directly from the browser: it needs CORS, and it puts the API address in client
    code (see the T-011 proxy decision).
  - A custom route handler that proxies with its own `fetch`: more code for the same result.

## Changes
- Branch: `feat/t-011-frontend` (Milestone 6 branch)
- PR:
- Files touched: `frontend/next.config.ts`
- Commits (hash, message): `c15c033` fix: raise the /api proxy timeout above the workflow run budget (T-013)

## Verification
A stub backend on :8000 that answers every request after 40 s, called through the dev server:
- with the fix: `HTTP 200 in 40.0 s` (twice);
- control, setting commented out: `Internal Server Error`, `HTTP 500 in 30.0 s` (the bug).
Type check, lint and production build clean. Not covered: a real 80-300 s workflow run through the
Ask screen (comes with the Plan screen).

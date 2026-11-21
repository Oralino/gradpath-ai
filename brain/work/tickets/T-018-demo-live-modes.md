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
- **Order:** 1 demo mode with no keys, 2 record demo runs, 3 sources date, 4 visitor key end to end,
  5 422 handler that drops `input`, 6 passcode and per-IP limits, 7 CORS allow-list and CSRF test,
  8 frontend demo/live switch (design-advisor first), 9 answer eval set and grounding check,
  10 release checks and PR.

## Changes
- Branch: `feat/t-018-demo-live-modes`
- PR:
- Files touched:
- Commits (hash, message):

## Verification
To be filled. Release checks from `CLAUDE.md` apply (demo mode with no keys, visitor key never in logs,
traces or responses, retrieval eval, the SECURITY.md checklist including its "From Milestone 7" line).

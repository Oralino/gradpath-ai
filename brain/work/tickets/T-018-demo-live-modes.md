# T-018: Milestone 7, demo and live modes
Milestone 7 ticket. Plan and story in `../MILESTONES.md`; modes in
`../../engineering/ARCHITECTURE.md` ("Providers and modes"); threats in
`../../engineering/SECURITY.md` (01, 07, release checklist).

- **Type:** feature
- **Status:** in progress (plan waiting for the owner's go-ahead)
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
Pending: the plan was put to the owner on 2026-11-20 with the open questions (which candidate items
belong in 7, their order, the Voyage-key question for live mode, the auth form). Recorded here once
answered.

## Changes
- Branch: `feat/t-018-demo-live-modes`
- PR:
- Files touched:
- Commits (hash, message):

## Verification
To be filled. Release checks from `CLAUDE.md` apply (demo mode with no keys, visitor key never in logs,
traces or responses, retrieval eval, the SECURITY.md checklist including its "From Milestone 7" line).

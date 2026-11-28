# T-027: the API's own INFO log lines never reach the logs
Logging gap found while closing [T-026](../done/T-026-github-sign-in.md). How the API logs is in
`../../../engineering/ARCHITECTURE.md`; what must never be logged is in `../../../engineering/SECURITY.md`.

- **Type:** bug
- **Status:** open
- **Opened:** 2026-11-28 · **Closed:**
- **GitHub Issue:** none

## Summary
On Render, after a successful real sign-in, a search of the whole log for `github sign-in` found
nothing, though `api/auth.py` logs `github sign-in: ok` at INFO. uvicorn's access lines and the
API's warnings do appear. So sign-in outcomes (ok, denied, too new, blocked, state mismatch) and any
other `gradpath.*` INFO line are invisible in production, which makes abuse or a broken sign-in
harder to see.

## Cause
Likely: no handler or level is configured for the `gradpath` loggers, so Python's last-resort
handler prints WARNING and above only (`api/main.py` sets levels only for the noisy libraries in
`QUIET_IN_LIVE`). To confirm before fixing.

## Decision
To decide: configure the `gradpath` logger at INFO (one handler, uvicorn's format) and check that
no INFO line anywhere carries a key, question text, login, id, code or state. The privacy checks
in `test_auth.py` still apply. Always-hard area (what reaches the logs): review + QA.

## Changes
- Branch:
- PR:
- Files touched:
- Commits (hash, message):

## Verification

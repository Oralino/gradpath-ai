# T-017: request bodies reject unknown fields
Found by the Milestone 6 release security checklist (`../../../engineering/SECURITY.md`, "Release security
checklist", first item). Index entries in `../../TASKS.md` and `../../DONE.md`.

- **Type:** bug
- **Status:** done
- **Opened:** 2026-11-20 · **Closed:** 2026-11-20
- **GitHub Issue:** none

## Summary
The checklist says every request body is a Pydantic model with bounds and `extra="forbid"`. Three
were not: `ChatRequest` (`/api/chat`), `AnalyzeRequest` (`/api/jobs/analyze`) and `ResumeRequest`
(`/api/profile/from-resume`). An unknown field was silently dropped instead of rejected.

## Cause
`api/chat.py`, `api/jobs.py` and `api/profile.py` declared their request models without a
`model_config`; Pydantic's default is `extra="ignore"`. The workflow and assist inputs already forbade
extras (`workflows/schemas.py`, `router/assist.py`).

## Decision
Add `model_config = ConfigDict(extra="forbid")` to the three models, so an unknown field is a 422.
The frontend already sends exactly the declared fields (`frontend/lib/api.ts`), so nothing changes
for it.

Found while testing: FastAPI's 422 body echoes the rejected value (`input`) back to the sender. It
goes only to the client that sent it and is never logged, and the frontend keeps only field paths
(T-011 step 1), so it is not a leak today. Before live mode (Milestone 7) a visitor key sent in a
wrong field would come back in that response, so a 422 handler that drops `input` is listed in
`../../TASKS.md`. Rejected for now: building that handler here (no visitor keys exist until
Milestone 7).

## Changes
- Branch: `feat/t-011-frontend`
- PR: [#8](https://github.com/Oralino/gradpath-ai/pull/8), merged 2026-11-20 as `14af492`
- Files touched: `backend/src/gradpath/api/chat.py`, `api/jobs.py`, `api/profile.py`,
  `backend/tests/test_api_errors.py`
- Commits (hash, message): `a6d6fcf` fix: reject unknown fields in chat, job and resume request
  bodies (T-017)

## Verification
New test `test_request_bodies_reject_unknown_fields` (all three routes answer 422 with a single
`extra_forbidden` error); `tests/test_api_errors.py` 10 passed; ruff clean;
full backend suite 531 passed.

# T-012: partial answer status
One RAG answer status for "the sources answer only part of this". Index: `../TASKS.md`.

- **Type:** change
- **Status:** done
- **Opened:** 2026-11-20 · **Closed:** 2026-11-20
- **GitHub Issue:** none

## Summary
`ChatAnswer.status` is only `answered` or `insufficient_evidence`, so an answer that opens with "the
evidence doesn't cover how to configure liveness probes" (answer check 2026-11-19, `q-031`, `q-049`)
looks like a full answer in the UI. Owner decision 2026-11-19: the backend reports `partial`, and
the Ask screen shows a "Partial answer" badge and a "Not covered: ..." line (`DESIGN.md`, decision 1).

## Decision
- The model returns a new `not_covered` field: one short sentence naming what the evidence does not
  cover, empty when it answers the whole question. Code, not the model, sets the status: `partial`
  when `not_covered` is non-empty and the answer has at least one valid citation. The existing
  downgrades (no valid citation, model says insufficient) still win.
- `not_covered` defaults to empty, so a model (or fake) that leaves it out still validates and gets
  `answered`: the old behaviour, never a crash. It is capped at 300 characters.
- Rejected: a `partial: bool` from the model (the sentence is what the visitor needs, and a flag
  without it can't be shown); detecting "doesn't cover" phrases in the answer text (brittle,
  English-only).
- Workflow fallback counts a `partial` answer as help, like `answered`. The CLIs print the
  "Not covered" line too.

## Changes
- Branch: `feat/t-011-frontend` (Milestone 6 branch)
- PR: [#8](https://github.com/Oralino/gradpath-ai/pull/8), merged 2026-11-20 as `14af492`
- Files touched: `backend/src/gradpath/rag/answer.py` (prompt, `ModelAnswer.not_covered`,
  `ChatAnswer` status and `not_covered`, status rule), `backend/src/gradpath/workflows/fallback.py`
  (partial counts as help), `backend/tests/test_rag.py`; `frontend/lib/types.ts`,
  `frontend/components/Assistant.tsx` (+ test).
- Commits (hash, message): `0ea9ae7` feat: add a partial answer status with a not-covered line (T-012)

## Verification
- 6 new fake-model tests (partial, empty field, missing field, 300-character cap, both downgrades
  over a partial reply); plus filler values ("None", "n/a", "Nothing.") treated as empty; backend 465 passed, ruff clean.
- Frontend: a partial-answer test (heading, badge, "Not covered" line, focus); a test that markup in `not_covered` stays text and an empty one gets fixed copy; 89 tests, lint
  and type check clean. Code review (public API schema): no bugs; its three suggestions applied
  (filler values, a "Not covered" line in the three CLIs, the extra UI tests).
- Real runs through the Ask API (2026-11-20, the local API with its configured models): `q-031` (liveness probes) and
  `q-049` (`workflow_dispatch`) came back `partial` with a specific "not covered" sentence; the
  PostgreSQL multicolumn-index question came back `answered` with `not_covered` empty. The first
  `q-031` run opened the answer with the gap again, so the prompt now says the app shows the sentence
  above the answer; the re-run started with what the evidence does say.

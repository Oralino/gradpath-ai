# T-004: spaced closing tags slipped past tag neutralising
Index entries go in `../../TASKS.md` (open) and `../../DONE.md` (closed).

- **Type:** bug
- **Status:** done
- **Opened:** 2026-11-18 · **Closed:** 2026-11-18
- **GitHub Issue:** none

## Summary
Untrusted text (retrieved chunks, job descriptions, questions, and now profile facts and
corrections) containing `< /evidence>` or `< /job_description>` (whitespace before the slash) was
not neutralised, so it could look like a closing delimiter to the model and pose as instructions.
Found by code review during T-003 step 5b.

## Cause
`safety.neutralise_tags` matched `<(/?)\s*(tag)\b`: whitespace was allowed after the slash but
not before it. Shared by `rag/answer.py`, `jobs/analyze.py` and `workflows/prompting.py`.

## Decision
Pattern is now `<\s*(/?)\s*(tag)\b` (whitespace on both sides of the slash). Side effect, accepted:
harmless text such as `a < gap` becomes `a &lt;gap` inside prompts. Rejected: stripping all `<`
from untrusted text (destroys code samples in the knowledge base).

## Changes
- Branch: `feat/t-003-agentic-workflow` (found and fixed during T-003)
- Files touched: `backend/src/gradpath/safety.py`, `backend/tests/test_workflow_planning.py`
- Commits (hash, message):
  - `538432b feat: add gap analysis, roadmap, interview questions and critic nodes (T-003)`

## Verification
`test_spaced_closing_tags_are_neutralised` (`< /tag`, `</ tag`, `<  /  TAG >`); the existing RAG and
job-analysis injection tests still pass (201 total).

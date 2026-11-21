# T-019: answers follow the sources, no added advice
The RAG answer prompt and how it was measured. Related: [T-018](T-018-demo-live-modes.md) step 10
(the eval that found it), `../../engineering/EVALUATION.md`.

- **Type:** change
- **Status:** done
- **Opened:** 2026-11-21 · **Closed:** 2026-11-21
- **GitHub Issue:** none

> Reversed on 2026-11-21 by [T-024](T-024-answer-gap-filling.md): the owner chose to let answers
> add advice again.

## Summary
The first answer eval (T-018 step 10, 2026-11-21) found 7 of 166 claims not stated by the cited
chunks: true, but the model's own advice or general knowledge ("use cache-aside when data can
tolerate staleness", "EXPLAIN ANALYZE also runs the query"). The prompt already says "use only the
evidence"; the model reads that as "no invented facts", not "no added advice". Owner, 2026-11-21:
the model should not give its own advice; answers follow the sources.

## Decision
- Owner decision 2026-11-21: answers contain only what the cited evidence states, advice included.
  When a question asks for advice or a recommendation the evidence doesn't give, the answer gives
  what the evidence says and names the rest in `not_covered` (so the answer is `partial`).
- Scope: the RAG answer path (`rag/answer.py`) only. The preparation workflow produces a plan, which
  is advice by design; its steps cite sources and its critic checks them.
- Measured by re-running the answer eval (same 20 cases) and comparing with the first run.
- Rejected for now: a runtime grounding check that drops unsupported sentences from every answer
  (one more Haiku call, 7-11 s, on the visitor's key in live mode). The fallback if the prompt
  alone is not enough.
- The 4 recorded RAG answers in `demo_runs/` are re-recorded so the demo shows the app as it is.

## Changes
- Branch: `feat/t-018-demo-live-modes` (ships with Milestone 7)
- PR: [#11](https://github.com/Oralino/gradpath-ai/pull/11)
- Files touched: `backend/src/gradpath/rag/answer.py` (prompt), `backend/tests/test_rag.py`,
  `demo_runs/ask-{multicolumn-indexes,idempotent-endpoints,graceful-shutdown,not-covered}.json`,
  `evaluation/results/answer-eval-20261121-0621.json`, EVALUATION, WALKTHROUGH, TASKS, DONE.
- Commits (hash, message): `569adb5` change: answers state only what the cited sources say, no
  added advice (T-019); merged to `main` as `926fd6c` ([#11](https://github.com/Oralino/gradpath-ai/pull/11)).

## Verification

Backend tests 804 (a test pins the rule), ruff clean. Answer eval re-run from the owner's terminal
(Claude Code on the Pro plan): unsupported claims 7/166 -> 1/151 (the one left is the answer
describing its own gap), answer cases 12/14 and refusals 6/6 unchanged, partial answers 3 -> 6,
each naming a real gap (EVALUATION.md). The 4 RAG recordings were re-recorded with the new prompt
(recorder scan clean; `ask-idempotent-endpoints` is now an honest partial).

# T-024: answers may fill gaps with advice again (reverses T-019)
The RAG answer prompt. Related: [T-019](T-019-answers-follow-sources.md) (the rule this removes),
T-018 step 10 (the answer eval), `../../engineering/EVALUATION.md`.

- **Type:** change
- **Status:** done
- **Opened:** 2026-11-21 · **Closed:** 2026-11-21
- **GitHub Issue:** none

## Summary
T-019 made answers state only what the cited sources say. In the owner's local test (2026-11-21)
every question the knowledge base covered only in part came back `partial`, and answers to "how
should I prepare" questions were thin. The owner tried the prompt without the no-advice rule and
chose to keep it.

## Decision
Owner, 2026-11-21: keep gap-filling. The answer prompt goes back to the T-018 rules: use only the
evidence, no outside knowledge, cite what is used, name what isn't covered. The explicit
"no added advice" rule of T-019 is removed, so the model may add advice and general guidance
around the cited facts again (measured before: 7 of 166 claims not stated by the cited chunks).
- Measured by re-running the answer eval on the same 20 cases.
- The 4 recorded RAG answers are re-recorded so the demo matches.
- Option offered and not chosen: label added advice as the model's own ("General advice, not from
  the sources: ...").

## Changes
- Branch: `change/t-024-answer-gap-filling`
- PR: [#14](https://github.com/Oralino/gradpath-ai/pull/14), merged as `49da242`
- Files touched: `backend/src/gradpath/rag/answer.py` (prompt), `backend/tests/test_rag.py`,
  `demo_runs/ask-{multicolumn-indexes,idempotent-endpoints,graceful-shutdown,not-covered}.json`,
  `evaluation/results/answer-eval-20261121-103106.json`, EVALUATION, WALKTHROUGH, T-019, DONE, TASKS.
- Commits (hash, message): `c12e530` change: answers may add advice around the cited facts again
  (T-024); `c3560b7` docs: record the gap-filling eval and re-record the demo answers (T-024).

## Verification
809 backend tests; the prompt test now pins the evidence rules and that the no-advice rule is gone.
Answer eval from the owner's terminal: 12/14 answer cases and 6/6 refusals (unchanged), 172/178
claims supported (97%; the 6 others are general advice), partial answers 4 (EVALUATION.md). The 4
RAG recordings re-recorded with this prompt (recorder scan clean).

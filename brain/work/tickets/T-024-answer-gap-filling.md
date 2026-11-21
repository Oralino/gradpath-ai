# T-024: answers may fill gaps with advice again (reverses T-019)
The RAG answer prompt. Related: [T-019](T-019-answers-follow-sources.md) (the rule this removes),
T-018 step 10 (the answer eval), `../../engineering/EVALUATION.md`.

- **Type:** change
- **Status:** in progress
- **Opened:** 2026-11-21 · **Closed:**
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
- PR:
- Files touched:
- Commits (hash, message):

## Verification

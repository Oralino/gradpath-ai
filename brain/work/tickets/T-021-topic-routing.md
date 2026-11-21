# T-021: a question about one topic of a job gets an answer, not the full plan
Routing fix found by the owner's local test (2026-11-21). Router design in
`../../engineering/ARCHITECTURE.md` and `../../engineering/WALKTHROUGH.md` (Query router, T-006);
routing results in `../../engineering/EVALUATION.md`.

- **Type:** bug
- **Status:** done
- **Opened:** 2026-11-21 · **Closed:** 2026-11-21
- **GitHub Issue:** none

## Summary
With the sample posting and profile attached, "How should I prepare for the PostgreSQL indexing
part of this role?" ran the full preparation workflow (an 8-step plan in minutes) instead of a
focused answer. The question is about one topic; only step 3 of the plan answered it.

## Cause
`router/rules.py` `rule_kind`: a personal message ("I") with a plan word ("prepare") and both
inputs attached is decided as `job_preparation` by rule, with no model call. "prepare" and "study"
don't mean "the whole job", and the rule can't see "the indexing part". The classifier prompt
didn't cover the case either: it described `job_preparation` as a study plan for a specific job
and said nothing about one topic of that job.

## Decision
Owner, 2026-11-21 (approved the proposed fix):
- The rule decides `job_preparation` only on whole-job words (`roadmap`, `plan`, `missing`, `ready`,
  `gaps`) and never when the message narrows itself (`part`, `section`, `only`, `just`,
  `specifically`, `aspect`); everything else with "prepare" or "study" goes to the classifier.
- The classifier prompt gains one rule: `job_preparation` is for the job as a whole; preparing for
  one named skill or topic, even one from the attached job, is a `knowledge_question`.
- Measured with new labelled routing cases (owner-approved) and the routing eval.
- Known limit, not in scope: the focused answer comes from the knowledge base and does not use the
  attached posting or profile. Making single answers use them is a separate feature.

## Changes
- Branch: `fix/t-021-topic-routing`
- PR: [#13](https://github.com/Oralino/gradpath-ai/pull/13)
- Files touched: `backend/src/gradpath/router/rules.py`, `router/route.py` (classifier prompt),
  `backend/tests/test_router.py`, `backend/tests/test_routing_eval.py` (counts),
  `evaluation/routing_cases.jsonl` (6 cases), EVALUATION, WALKTHROUGH.
- Commits (hash, message):

## Verification
Tests: one-topic and narrowed requests are left to the model; whole-job requests still go to the
workflow by rule ("ready" alone was too broad: found while tracing the new labels, now only "am I
ready"). Routing eval from the owner's terminal: 36/36 correct (rules 9/9, model 27/27),
`topic_scope` 6/6, workflow precision and recall 1.0 (EVALUATION.md). 816 backend tests pass
(the local run had the owner's uncommitted gap-filling prompt test, which fails `test_rag`'s
prompt check by design; it is not part of this change).

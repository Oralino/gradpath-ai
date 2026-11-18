# T-006: Milestone 4: router + fallback
Index entries go in `../TASKS.md` (open) and `../DONE.md` (closed).

- **Type:** feature
- **Status:** in progress
- **Opened:** 2026-11-18 · **Closed:**
- **GitHub Issue:** none

## Summary
Choose the cheapest path that works for each request: traditional RAG for focused questions, the
LangGraph workflow for job + profile preparation. Record the route and why. When the workflow
cannot finish, return a clearly labelled partial result (what finished, what didn't, grounded RAG
help where it still applies) instead of an error. Measure routing accuracy against a labelled set
and compare adaptive routing with always-RAG and always-workflow (spec section 2A).

## Decision
Owner approved 2026-11-18 (recommended answers):
1. Router: deterministic rules first; Haiku classifies only what the rules can't decide, with a
   validated schema and the message passed as untrusted data. Output `{route, reason,
   requires_user_profile, requires_multi_step_workflow, decided_by}`.
2. Safe default when classification fails: `traditional_rag`.
3. New `POST /api/assist` (message + optional job description and profile); `/api/chat` and
   `/api/career/prepare` stay for direct use.
4. Workflow time budget: 300 s by default, a setting, checked between stages (graph run with
   `stream` so finished stages are known).
5. Routing accuracy on ~30 labelled requests; the adaptive vs always-RAG vs always-workflow
   comparison on 4 requests only (Pro-plan quota).
6. Requests the workflow can't serve yet (multi-job comparison, progress tracking, resume
   rewriting) are recognised and answered "not supported yet"; a workflow request missing its
   job description or profile gets "needs input" and runs nothing.
Fallback: on a stage failing after its retry, the loop limit, the time budget or an unavailable
dependency, return a result labelled `fallback` with the request, finished and failed stages, the
reason, and cited RAG help for the job's requirements where evidence exists; reasons logged by
type only.
High-risk area: the workflow's fallback limits (code-reviewer + qa-checker whatever the size).

## Changes
- Branch: `feat/t-006-router-fallback`
- PR:
- Files touched: `backend/src/gradpath/router/` (new), `backend/tests/test_router.py`,
  `evaluation/routing_cases.jsonl`, `brain/engineering/SECURITY.md` (new), `CLAUDE.md`, `brain/`,
  `workflows/fallback.py` (new), `workflows/graph.py`, `workflows/schemas.py`, `workflows/cli.py`,
  `api/career.py`, `config.py`, `evaluation/workflow_eval.py`, `.env.example`, workflow and API tests
- Commits (hash, message):

## Verification
- Step 4 (router): 46 tests, fake model only. code-reviewer: no way found for text to set the
  route; fixed: definition rule took mixed questions ("What is Docker? Also summarise this
  posting."), comparison words reached the plan rule, zero-width/fullwidth tag variants (router now
  HTML-escapes the whole message), whitespace-only messages, failures logged without status; tests
  now assert log contents and cover forged tags and KeyboardInterrupt.
- Step 5 (fallback): 24 tests with forced failures (stage after retry, service down, rate limit,
  wrong key, loop limit, time budget, failed parallel step, failed revise, stale issues, broken
  assembly, KeyboardInterrupt). code-reviewer found 6 issues, all fixed; qa-checker clean (lock,
  lint, format, 380 tests then, secrets, personal data, attribution, debug leftovers).
- Security: threat model in `brain/engineering/SECURITY.md` (2026-11-18) from the owner's guides.

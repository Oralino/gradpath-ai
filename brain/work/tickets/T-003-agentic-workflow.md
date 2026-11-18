# T-003: Milestone 3, agentic workflow (LangGraph)
Index entries go in `../TASKS.md` (open) and `../DONE.md` (closed).

- **Type:** feature
- **Status:** in progress
- **Opened:** 2026-11-18 · **Closed:**
- **GitHub Issue:** none

## Summary
Turn a job description and a (sample) profile into the MVP outputs in
`../../product/REQUIREMENTS.md`: JD analysis, requirements tied to the JD text, per-requirement
gaps (demonstrated / partially evidenced / not yet evidenced, with evidence, reasoning and
confidence), a prioritised roadmap with cited resources, and interview questions tied to the gaps.
Built as a LangGraph workflow with typed `CareerPrepState`, Pydantic-validated node outputs and a
bounded critic -> revise loop, served by `POST /api/career/prepare`.

Steps (proposed, awaiting the owner's go-ahead):
1. Ticket, branch, Milestone 2 housekeeping.
2. Explain LangGraph and the node plan / state schema to the owner; settle the open questions.
3. Fictional sample profile, committed; owner approves its content.
4. State + graph skeleton with stub nodes; graph-shape tests (parallel join, loop limit).
5. Nodes one by one, reusing `analyze_job` and `RetrievalService`; fake-model tests per node.
6. `POST /api/career/prepare`; one real run on the Pro plan from the Terminal panel; optional trace.
7. Small workflow evaluation (`evaluation/workflow_cases.jsonl`); review, QA, PR.

High-risk (always hard): the workflow's retry, revision and fallback limits; prompt-injection
defences for the profile and JD text; what reaches LangSmith.

## Decision
- LangGraph `langgraph==1.2.22` (already pinned). Checked against the installed package:
  `StateGraph(state_schema, context_schema=...)`, `add_edge([a, b], c)` waits for both branches,
  `add_conditional_edges(source, path, path_map)`, `RetryPolicy(max_attempts=...)`,
  `compile()` and the `recursion_limit` config as a second safety net.

## Changes
- Branch: `feat/t-003-agentic-workflow`
- PR:
- Files touched:
- Commits (hash, message):

## Verification

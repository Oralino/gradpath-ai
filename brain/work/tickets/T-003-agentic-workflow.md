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
- Owner approved the plan on 2026-11-18, with the recommended answers:
  1. Sample data: a fictional profile (`evaluation/profiles/sample_new_grad.json`) and a fictional
     job description (`evaluation/job_descriptions/sample_backend_new_grad.txt`), committed; the
     owner approves their content. The real posting stays in `private/`.
  2. Revision limit: 1 round by default, configurable in `.env`; tests cover 0, 1 and 2.
  3. "Correct assumptions and regenerate": a simple version now, a `corrections` field on the
     request that reruns the workflow. Pausing the graph for input (interrupt + checkpointer)
     is deferred to the frontend milestone.
  4. Profile input: a structured form (skills, projects, coursework, experience, weekly hours),
     so `analyze_profile` needs no model call. Resume extraction later.
- Graph: `analyze_job` (Haiku) -> `retrieve_knowledge` (one batched Voyage call) in parallel with
  `analyze_profile` (code); join -> `analyze_gaps` (Sonnet, cites profile ids + chunk ids, checked
  in code) -> `plan_roadmap` (Sonnet) in parallel with `interview_questions` (Haiku); join ->
  `evaluate` (code checks, then Haiku) -> `revise` (bounded) or `finalize`.
- Services (retrieval, models) go in LangGraph's runtime context, not the state, so the state stays
  plain, serialisable data. `errors` and `node_log` use a list reducer (parallel writes).
- `POST /api/career/prepare` answers synchronously in this milestone; the job-id + polling design
  comes with the frontend.
- `analyze_job()` and `POST /api/jobs/analyze` stay unchanged; the graph reuses their pieces.
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
- Step 4 (skeleton): 36 tests in `tests/test_workflow_graph.py` (152 total), ruff clean. Covers
  both joins, the loop at limits 0–3, protected keys, a broken route stopped by
  `recursion_limit` (measured minimum 7 + 2 per revision), input limits, and the sample profile.
- code-reviewer (step 4): no way found for the loop to exceed its limit. Fixed: any node could
  overwrite the counter/limit (now protected keys), non-int limits, unbounded JD and corrections
  (`WorkflowInput`), profile total size, critic flag vs blocking issues (`Critique.ok`), missing
  critique now partial, clear error for non-dict node returns, one revision cap constant, shared
  `Seniority` type. Deferred to step 6: mapping `GraphRecursionError` and node exceptions to API
  errors. Not done: blank optional strings become a 422 (the client omits blank fields).
- Step 5a (job + retrieval nodes, retry): 18 new tests (170 total), ruff clean. code-reviewer: retry
  bounded (2 attempts, inside one super-step), guard errors not retried, revise not double-counted,
  quote checks and untrusted wrapping preserved, batching matches `analyze_job`. Fixed: retry
  allow-list instead of LangGraph's default (which retried API 401s on top of the SDK's own
  retries); added retry and guard tests. For step 6: never return `str(exc)` to the client (a
  ValidationError message can echo the model's reply).

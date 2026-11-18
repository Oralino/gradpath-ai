# T-003: Milestone 3, agentic workflow (LangGraph)
Index entries go in `../TASKS.md` (open) and `../DONE.md` (closed).

- **Type:** feature
- **Status:** done (PR open)
- **Opened:** 2026-11-18 · **Closed:** 2026-11-18
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
- Files touched: `backend/src/gradpath/workflows/` (new: schemas, state, prompting, nodes, gaps,
  roadmap, critic, graph, cli), `api/career.py`, `api/limits.py` (new), `api/main.py`, `api/chat.py`,
  `api/jobs.py`, `evaluation/workflow_eval.py` (new), `jobs/analyze.py`, `safety.py`, `config.py`,
  `backend/tests/` (test_workflow_graph, _nodes, _planning, _eval, test_api_career),
  `evaluation/` (profiles, job_descriptions, workflow_cases.jsonl, results), `.env.example`,
  `CLAUDE.md`, `brain/`
- Commits (oldest first):
  - `bc28261 docs: open T-003 and record the Milestone 2 merge (T-003)`
  - `7d06696 docs: record the approved Milestone 3 plan and draft fictional sample data (T-003)`
  - `cf705c8 feat: add career workflow state, schemas and bounded LangGraph skeleton (T-003)`
  - `06ffe6b feat: add job analysis and knowledge retrieval nodes with bounded model retries (T-003)`
  - `538432b feat: add gap analysis, roadmap, interview questions and critic nodes (T-003)`
  - `37151ea feat: add POST /api/career/prepare and a workflow CLI (T-003)`
  - `1bc66bf fix: cite each source section once and keep minor issues; record the first real workflow run (T-003)`
  - `e9bd51a feat: add workflow evaluation cases and runner; cap model routes and redact retry logs (T-003)`
  - `9f23a19 fix: tighten workflow eval checks, save after each case, narrow the retry log filter (T-003)`
  - `4d6d0b1 docs: record the workflow evaluation, the retrieval re-check and remaining T-005 items (T-003)`
  - plus the closing docs commit

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
- Step 5b (gaps, roadmap, questions, critic, revise): 31 new tests (201 total), ruff clean, incl.
  full fake-model runs (complete; one revision; limit reached). code-reviewer: all text reaches
  prompts through `block()`, id checks hold, no cycles in dependencies. Fixed: `< /tag` slipped
  past `safety.neutralise_tags` (shared with rag and jobs), an empty or worse revision replaced the plan, an
  empty roadmap could pass, corrections alone could mark everything demonstrated, the item cap
  ran before filtering, and items with no sources weren't flagged. Deferred to the API/frontend
  steps: length caps on model-written text, and rendering it as text, never HTML.
- Step 6 (API + CLI): 15 new tests (215 total), ruff clean. code-reviewer: no exception text, model
  reply or key in responses; the request can't set the limit; threading safe. Fixed: CLI prints
  UTF-8 (Windows cp1252 would crash after a paid run), one run at a time (503 when busy), model
  text truncated at 1,000 chars on every returned field, responsibilities capped, our error log
  doesn't quote Pydantic input. Deferred (TASKS): the route uses the server's model credentials
  whatever `APP_MODE` says (live-mode ticket); LangGraph's own retry log line can include a
  Pydantic message; `--out` can write profile-derived text into a tracked folder.
- Real run 2026-11-18 (Pro plan, Terminal panel, sample posting + profile, tracing off):
  `complete` after 1 revision, 101 s, 18 requirements, 10 roadmap items, 10 questions; output
  `evaluation/results/workflow-20261118-014953.json`, findings in `EVALUATION.md`. Fixed from it:
  one citation per source section, minor issues kept on a complete result (217 tests).
- Step 7 (workflow eval + open tasks): 4 workflow cases all pass (8 checks each, 11/11 gap
  expectations) on the Pro plan, `evaluation/results/workflow-eval-20261118-070716.json`; retrieval
  re-check unchanged (Recall@5 0.968, MRR 0.984). Open tasks closed: concurrency caps on every
  model route (`api/limits.py`), LangGraph retry log redacted, `--out` guard; ingestion polish as
  T-005. code-reviewer on the eval: fixed citation check skipping unknown ids, first-match-only gap
  check, case sensitivity, results lost on interrupt, filter acting on other records, non-sample
  profiles in cases.
- Release QA (qa-checker, 2026-11-18): uv sync --locked, ruff, format, 248 tests (251 after the
  last T-005 fixes); no secrets, personal data, AI attribution or tracked ignored files; no debug
  leftovers. Release checks not applicable yet: demo mode with no keys and visitor-key handling
  (Milestone 7).

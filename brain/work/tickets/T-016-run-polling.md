# T-016: background preparation runs with a run id to poll
Live stage progress for 80-300 s workflow runs. Index: `../TASKS.md`, `../DONE.md`.

- **Type:** feature
- **Status:** done
- **Opened:** 2026-11-20 · **Closed:** 2026-11-20
- **GitHub Issue:** none

## Summary
Owner decision 2026-11-19 (DESIGN.md decision 2, option B): the Plan screen shows which workflow
stage is running. A synchronous request can't do that, and it held one HTTP request open for up to
5 minutes. Built as step 1 of the Plan-screen plan (a local planning note, not in the repo).

## Decision
- **API.**
  - `POST /api/career/runs` (a `WorkflowInput`) returns 202 `{run_id}`, or 503 when busy.
  - `GET /api/career/runs/{id}` returns `{status, elapsed_s, stages[{name,state}], revisions,
    result, error}`, or 404.
  - `/api/assist` starts a run for the workflow route and returns `outcome: "started"` with
    `run_id`.
  - `/api/career/prepare` and the CLI's `respond()` stay synchronous.
- **`workflows/runs.py` `RunStore`.**
  - **Thread and limits:** `run_workflow` runs in a daemon thread started in a copy of the caller's
    context (`contextvars`, so the tracing rules carry over). The same one-run slot
    (`limits.CAREER`) is held for the whole run. The revision limit, time budget and fallback are
    unchanged. `run_workflow` gained one observe-only hook, `on_step`, and an error in it is
    ignored.
  - **Privacy:** records never hold the posting or profile. Ids are uuid4, validated and can't be
    listed. Finished runs expire after 15 minutes, and at most 20 are kept.
  - **Errors:** fixed text only. A refused API key gets its own message, and logs carry exception
    types only. A type-only "run finished: status, fallback reason, seconds" line keeps fallback
    frequency observable, since the route log now records only "started".
  - **Ordering:** the slot is released before "done" or "failed" is published, so a client that
    sees a finished run can start the next one without a spurious 503. A record is stored only
    after its thread has started.
- **Stage states** come from a `PREREQS` table, and a test checks it against the compiled graph.
  After `evaluate`, neither `revise` nor `finalize` shows as running until it appears in the log,
  because the critic's verdict isn't known yet.
- **Rejected:**
  - WebSockets or server-sent events: more moving parts. Polling every 2 s is enough for stages
    that take tens of seconds.
  - A job queue or database (Celery, Redis): not free-tier friendly, and the demo needs only one
    run at a time.
  - Cancelling a run: a running stage can't be interrupted, and the time budget already stops a
    run at 5 minutes.
- **Known limits** (to document in ARCHITECTURE):
  - Runs live in one process. `--reload` or a restart forgets them (the poll gets 404), and the
    app must run as a single worker.
  - A stage that hangs holds the slot until it returns, because the budget is checked between
    steps. That was already true of the sync route.
  - With `max_revisions` of 2 or more, a second revise shows "done" while it is running.

## Changes
- Branch: `feat/t-011-frontend` (Milestone 6 branch)
- Files touched:
  - `backend/src/gradpath/workflows/runs.py` (new), `api/runs.py` (new), `workflows/graph.py`
    (`on_step`), `router/assist.py`, `api/assist.py`, `api/main.py`;
  - `tests/test_runs.py` (new), `tests/test_api_assist.py`.
- Commits (hash, message): `1d1effe` feat: run the preparation workflow in the background with a run id to poll (T-016); the Plan screen that polls it is `1d5c3c3` (T-011)

## Verification
- **Tests:** 528 backend tests, four runs in a row with no flakes. The new ones cover:
  - stage states at every point, including the revise loop, and the table matching the graph;
  - start and progress mid-run with a gate, and busy;
  - the slot freed once a run shows finished, after a refused key, after a pre-graph failure, and
    when a thread can't start;
  - a fallback counting as done, not failed;
  - no input on records;
  - expiry, MAX_RUNS, and malformed or unknown ids;
  - the tracing context carried into the thread, both on and off;
  - progress errors ignored;
  - the API's 202, 503, 404 and 422;
  - assist returning `started` and the polled result.
- **Review:**
  - code-reviewer, always-hard. Its one bug (slot released after "done") and four should-fixes
    were fixed. The route-log observability point was handled with the finish log line, and the
    deployment notes and the revise-display nit are recorded above.
  - qa-checker: all checks passed.
- **Real runs, 2026-11-20, local API:**
  - Through `/plan` with the sample posting and profile: about 50 s. The stages advanced live in
    the browser, the result came back `complete`, and a reload kept it.
  - Through the Ask screen: the router chose the workflow ("chosen by rules"), progress showed live,
    and the result was `complete_with_limitations`, with one blocking issue shown inline and one
    revision.

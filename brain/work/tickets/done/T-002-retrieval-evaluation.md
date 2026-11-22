# T-002: Milestone 2, retrieval evaluation + tracing
Index entries go in `../../TASKS.md` (open) and `../../DONE.md` (closed).

- **Type:** feature
- **Status:** done (merged, 93f1b79)
- **Opened:** 2026-11-17 · **Closed:** 2026-11-18
- **GitHub Issue:** none

## Summary
Measure how well search finds the right sources, so every later experiment (hybrid search,
reranking, chunk sizes) has a baseline to beat. A labelled set of 30–50 questions with their
correct sources; an eval runner (our own code) reporting Recall@K, Precision@K, MRR and latency;
the 0.45 threshold re-checked against the labels; LangSmith tracing wired explicitly; results in
`../../../engineering/EVALUATION.md`.

Steps:
1. Ticket, branch, Milestone 1 housekeeping.
2. Explain the metrics and the dataset format to the owner; draft
   `evaluation/retrieval_questions.jsonl` with the owner (incl. uncovered questions and the
   multi-column index recall case).
3. Eval runner using `search_many` (one Voyage request per batch); results table + JSON; first
   baseline in `EVALUATION.md`; threshold re-check.
4. LangSmith: explicit `LANGSMITH_TRACING` wiring and what may reach it (always-hard area);
   callbacks/context in `ChatClaudeCode._generate`'s worker thread; optional dataset upload.
5. Optional: GitHub Actions CI (lint + tests, no keys).

## Decision
- Owner approved the plan on 2026-11-18: 40 questions (30 covered, 10 uncovered) and GitHub
  Actions CI included.
- Labels name pages (`source_url`) plus an optional section heading, not chunk ids, so they
  survive chunk-size experiments; sections are needed for the two 100+ chunk single-page sources.
  Format and metric definitions: `../../../engineering/EVALUATION.md`.
- Uncovered questions are mostly near-domain (Kubernetes, OAuth, JWT, CI/CD, CORS, React, salary
  negotiation) to stress the threshold; 3 are off-domain.
- Rejected: LLM-generated labels (they would grade the model with its own opinion).
- Runner: own code (`gradpath/evaluation/`), raw top-K ranking with the threshold judged offline
  from best scores; embedding and vector search timed apart via new
  `RetrievalService.embed_many` / `search_vectors` (`search_many` now uses them, behaviour unchanged).
- Dataset v1.1: `q-035` (CORS) relabelled covered after the first run (a factual labelling error).
- Threshold stays 0.45: on v1.1 it keeps 100% covered and rejects 100% uncovered.
- Tracing (owner approved 2026-11-18): full local traces + client-side redaction; on only when
  asked and a key is set; never in live mode; set via `langsmith.configure` so the environment
  can't override it; visitor keys refused while tracing is on. Dataset upload to LangSmith
  deferred to Milestone 5 (useful once there are two configs to compare). Rejected: metadata-only
  traces (safer, but hides the prompts that explain a bad answer).

## Changes
- Branch: `feat/t-002-retrieval-evaluation`
- PR: https://github.com/Oralino/gradpath-ai/pull/2
- Merged: `93f1b79 Merge Milestone 2: retrieval evaluation, tracing and CI (T-002)` (2026-11-18)
- Files touched: `backend/src/gradpath/evaluation/` (new), `tracing.py` (new),
  `retrieval/service.py`, `providers/` (factory, claude_code, smoke), `rag/`, `jobs/`, `api/main.py`,
  `config.py`, `backend/tests/` (test_evaluation, test_tracing, conftest),
  `evaluation/retrieval_questions.jsonl`, `evaluation/results/`, `.github/workflows/ci.yml`,
  `.env.example`, `CLAUDE.md`, `brain/`
- Commits (oldest first):
  - `3d85d40 docs: open T-002 and record the Milestone 1 merge (T-002)`
  - `b57c745 feat: add labelled retrieval question set v1 (T-002)`
  - `630eb06 fix: relabel the CORS question as partly covered, dataset v1.1 (T-002)`
  - `a9cc871 feat: add retrieval eval runner and record the first baseline (T-002)`
  - `06eb78d feat: add explicit LangSmith tracing rules with redaction and traced steps (T-002)`
  - `5daa079 docs: record the first real LangSmith trace (T-002)`
  - `919814f ci: lint and test the backend on GitHub Actions (T-002)`
  - `68e6bda docs: record CI and finish the Milestone 2 story (T-002)`
  - `c7d2fff docs: link the Milestone 2 PR in T-002 (T-002)`

## Verification
- 103 tests pass (14 new in `tests/test_evaluation.py`); ruff lint and format clean.
- code-reviewer on the runner diff: no bugs; fixed unknown-field/empty-section/duplicate-target
  validation, line numbers in load errors, empty-input and bad-K guards; documented that
  `run_eval` must not use the API's shared service.
- Real baseline run 2026-11-18 (one Voyage call): `evaluation/results/retrieval-20261118-051615.json`;
  numbers in `EVALUATION.md`. The v1 run (before the label fix) is kept as
  `retrieval-20261118-051350.json`.
- Tracing: 116 tests pass, also with `LANGSMITH_TRACING` / `LANGCHAIN_TRACING_V2` / a key /
  `LANGSMITH_ENDPOINT` forced in the shell (QA). code-reviewer: the probe and eval CLIs never
  called `configure_tracing`, so a shell variable could still trace them unredacted; fixed by
  switching tracing off at import. Also fixed: explicit endpoint, `LANGSMITH_RUNS_ENDPOINTS`
  refused, wider phone rule, flush on shutdown even if close fails, env-cache-safe tests, a test
  that the real client redacts. Deferred: the visitor guard re-check for live mode (TASKS).
- Real trace 2026-11-18 (Pro plan, terminal panel shell): `rag.ask` printed `tracing: on`;
  LangSmith received one trace `answer_question` (6.7 s) with children `retrieve` (outputs: chunk
  ids + scores only) and `RunnableSequence` -> `ChatClaudeCode` (626 tokens, which excludes cached
  input tokens, a known Claude Code reporting gap) -> `parse`. Tracing set back to off afterwards.

# T-001: Milestone 1, RAG foundation
Index entries go in `../TASKS.md` (open) and `../DONE.md` (closed).

- **Type:** feature
- **Status:** in progress
- **Opened:** 2026-11-17 · **Closed:**
- **GitHub Issue:** none

## Summary
First working slice: a uv backend, the LLM provider layer, ingestion of the approved sources into a
local Qdrant index, a retrieval service, a traditional-RAG endpoint with citations and abstention,
and a first job-description skill extraction with per-skill retrieval (the spec's first milestone).

Steps:
1. Scaffold `backend/` (uv, pinned deps, settings, ruff, pytest).
2. Provider layer: `ChatClaudeCode` (Agent SDK, Pro plan), `ChatAnthropic`, fake model; factory.
3. Ingestion: approved manifest rows -> download to `knowledge_base/raw/` -> clean -> chunk -> metadata
   -> Voyage embeddings -> local Qdrant.
4. Retrieval service: query -> top-k chunks with metadata and scores; "no evidence" threshold.
5. Traditional RAG + `POST /api/chat`: evidence delimited as untrusted data, Pydantic answer schema,
   citations checked against the retrieved chunk IDs, abstention.
6. `POST /api/jobs/analyze`: extract requirements from a JD, retrieve per requirement, cited summary.
7. Tests with the fake model, fake embeddings and in-memory Qdrant; one manual real run.

## Decision
- **Claude Code from Python:** `claude-agent-sdk` (0.2.184), which bundles the Claude Code CLI, so no
  separate install. `ChatClaudeCode` subclasses LangChain's `BaseChatModel` and calls the SDK with
  built-in tools disabled.
- **Structured output gotcha:** current Opus 5.5 and Sonnet 5.5 reject forced `tool_choice`, so
  `ChatAnthropic.with_structured_output` must use the JSON-schema method (`output_config.format`), not
  forced tool calling. Verify against `langchain-anthropic` 1.7.x docs before writing it.
- Pinned versions checked on PyPI 2026-11-17: langchain-core 1.8.2, langchain-anthropic 1.7.10,
  langchain-voyageai 0.4.1, langchain-qdrant 1.1.0, langchain-text-splitters 1.1.3, langgraph 1.2.22,
  langsmith 0.15.0, qdrant-client 1.20.0, voyageai 0.6.0, anthropic 2.10.0, fastapi 0.163.2,
  pydantic 2.14.3, pypdf 7.1.0.
- Models per step (owner, 2026-11-17): `claude-haiku-5-5` for routing and extraction,
  `claude-sonnet-5-5` for answers, gap analysis and roadmap; set in config, not hard-coded.
- Who: lead builds steps 1, 2 and 5 (custom model class, untrusted-content handling); steps 3, 4 and 7
  may go to `engineer` with a brief; code-reviewer at the end (provider layer and prompt handling are
  always-hard).

## Changes
- Branch: `feat/t-001-rag-foundation`
- PR:
- Files touched:
- Commits (hash, message):

## Verification
- Steps 1–2: `uv run pytest -q` 12 passed; `ruff check` clean.
- Steps 1–2, real run (owner's terminal, 2026-11-17): after a one-time `/login` in the bundled
  CLI, `uv run python -m gradpath.providers.smoke` returned the text reply and a validated
  structured `Requirement(skill='SQL', importance='Required')` on `claude-haiku-5-5` via the Pro plan.
  Note: Claude Code reports `input_tokens` without cached tokens (2 here), so token counts from
  `claude_code` mode understate real input; use API mode for cost measurements.
- Step 3: engineer built `ingestion/`; lead review sent back 3 fixes (embedding cache, embed-before-
  rebuild, throttled queries) and added per-32 cache flushing. Full run: 18 sources, 52 pages,
  956 chunks indexed (1024-dim, `gradpath_kb`), ~20 min on the Voyage free tier.
- Step 4: `retrieval/service.py`, 7 tests; probe on the real index put the right source first for
  5/5 covered questions (0.59–0.68) vs 0.27–0.39 for uncovered ones; threshold 0.45
  (`EVALUATION.md`). Heading anchors stripped from section names (re-ingest). Suite: 43 passed.
- Step 5: `rag/` + `api/` (`POST /api/chat`, `GET /api/health`); 54 tests passed. Real index,
  uncovered question ("sourdough") abstained without a model call (best 0.302). Real run in the
  owner's terminal (Sonnet 5.5 via Pro plan, 2026-11-17): "What is a database index and when should
  I use one?" -> `answered`, 5 valid citations (PostgreSQL 11.1 Introduction x3, SQLite 1.3 and
  1.5), and it stated what the evidence did not cover (index costs, index types, multi-column
  indexes) instead of using outside knowledge. Recall gap noted: `db-postgres-indexes` page
  `indexes-multicolumn` exists but was not in the top 5; add as a Milestone 2 eval case.
- Step 6: `jobs/` + `POST /api/jobs/analyze` + `jobs.cli`; 64 tests passed. Real batched search of
  8 InterImage-style requirements: 1 Voyage request, 1.5 s; covered: REST/microservices, Git,
  Python, Agile/code review; not covered: Docker/Kubernetes, CI/CD, LangChain/vector databases
  (corpus gaps), clearance (eligibility).
- Step 6, real run (owner's terminal, Haiku + Sonnet via Pro plan): InterImage posting -> 20
  requirements, 9 covered, 8 not covered, 3 not applicable (degree, project experience, TS
  clearance), 7 study notes, 0 unverified quotes. Notes stayed grounded ("Go is not covered",
  "does not mention GitLab or GitHub"). Fixes from the run: `weak_evidence` coverage when no valid
  note (AWS/Azure, Vector databases had only weak matches), Markdown heading ids `{#...}` stripped,
  repeated document title dropped from citation sections. Re-ingest: 949 cache hits, 7 misses.
  Suite: 66 passed.
- Step 6, second real run: the three fixes confirmed (clean heading, deduped title, `~` label);
  24 requirements this time (extraction varies run to run; measure in Milestone 2). Notes for
  AWS/Azure, Docker, Vector databases and Agile said their evidence was limited yet were labelled
  covered, so notes now carry `evidence_strength` (direct/partial) and partial -> weak_evidence.
  Suite: 67 passed.

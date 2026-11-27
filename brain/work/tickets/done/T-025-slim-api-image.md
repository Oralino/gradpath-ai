# T-025: slim the API Docker image
Make the deployed API image install only what the server runs. Part of Milestone 8 (the image
from [T-020](../in-progress/T-020-deploy.md) step 2b); the image is described in
`../../../engineering/ARCHITECTURE.md` ("Container").

- **Type:** change
- **Status:** done
- **Opened:** 2026-11-27 · **Closed:** 2026-11-27
- **GitHub Issue:** none

## Summary
The image was 1.27 GB unpacked. Almost all of it was libraries the deployed API never imports:
`claude-agent-sdk` bundles the whole Claude Code program (364 MB installed on the owner's PC) for
local mode only; `fastembed` and `onnxruntime` serve the retrieval experiments; `beautifulsoup4`
serves index building; `pypdf` was imported nowhere. Owner request (2026-11-27): a smaller image
that installs only what the product needs to run, and a look at lighter base images such as UBI 9.

## Decision
- **Dependency groups, not a new base image.** `[project] dependencies` is the runtime set; new
  `[dependency-groups]` hold `local` (claude-agent-sdk), `eval` (fastembed) and `ingest`
  (beautifulsoup4, langchain-text-splitters). `[tool.uv] default-groups` lists all of them, so
  `uv sync` on a PC and in CI installs everything as before; the Dockerfile runs
  `uv sync --no-default-groups`.
- **`claude_agent_sdk` is imported when a Claude Code call runs** (`providers/claude_code.py`),
  not when the module loads: `providers/__init__.py` imports the module at every API start.
- **pypdf removed:** nothing imports it. It returns, pinned, with the PDF resume upload.
- `langchain-text-splitters` stays in the image anyway: `langchain-voyageai` depends on it.
  `numpy`, `grpcio` and `pillow` also stay: qdrant-client and voyageai need them.
- **Base image kept: `python:3.13-slim`.** It is about 130 MB of the 1.27 GB. Rejected: UBI 9
  (minimal is about as large; its newest packaged Python is 3.12, so 3.13 would have to be built
  in the image); Alpine (musl: several wheels we use aren't published for it, so builds from
  source); distroless Python (ships Debian's Python 3.11, not our pinned 3.13).
- **Guards:** `tests/test_runtime_deps.py` imports the app with the left-out modules blocked (CI
  installs every group, so nothing else would notice a new top-level import); the CI `docker`
  job checks the image doesn't contain them.

## Changes
- Branch: `feat/t-020-deploy` (Render deploys this image from it)
- PR:
- Files touched: `backend/pyproject.toml`, `backend/uv.lock`, `backend/Dockerfile`,
  `backend/src/gradpath/providers/claude_code.py`, `backend/tests/test_runtime_deps.py` (new),
  `.github/workflows/ci.yml`; ARCHITECTURE, WALKTHROUGH, TASKS.
- Commits (hash, message): `0995875` feat: install only the API's runtime dependencies in
  the image (T-025); `8cf9f8a` docs: record the slimmed API image (T-025).

## Verification
Local, 2026-11-27 (Docker Desktop 29.9.3):
- Image size, unpacked: **1.27 GB -> 560 MB** (`gradpath-api:latest` from step 2b vs the new
  build). Memory at idle in demo mode: 204 MiB -> 168 MiB.
- In the new image: none of `claude_agent_sdk`, `fastembed`, `onnxruntime`, `bs4`, `pypdf` can be
  found; the Voyage tokenizer still loads with `--network none`; demo mode answers `/api/health`
  with no keys. Live mode with no `QDRANT_URL` stops with its designed error, after the passcode
  and provider checks pass.
- Backend: 851 passed, 1 skipped; ruff clean. `test_runtime_deps.py` imports the app and the
  retrieval stack with the left-out modules blocked.
- code-reviewer: no bugs; no API-reachable module imports a left-out library. Taken: a static
  check that only four files import one (`providers/claude_code.py`, `retrieval/sparse.py`,
  `retrieval/rerank.py`, `ingestion/clean.py`), so lazy imports on request paths are covered; a
  clear `ClaudeCodeError` if `LLM_PROVIDER=claude_code` runs without the `local` group; a longer
  subprocess timeout. After: 852 passed, 1 skipped.
- CI run 46083083882 green (backend, frontend, docker with the new "runtime set only" step).
- Render auto-deployed `8cf9f8a` (build about 1 min): `/api/health` live with `search_enabled:
  true`; a new search through the Vercel site returned 4 passages in 2.7 s (Qdrant Cloud, the
  Voyage budget and the embedding path all ran in the slim image); no new errors in the log.

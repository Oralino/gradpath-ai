# T-029: LLM provider layer (Claude, Ollama, LM Studio, transformers.js)
Milestone 9 ticket (planned). Today's factory is `backend/src/gradpath/providers/factory.py`; modes
and live mode are in `../../../engineering/ARCHITECTURE.md` ("Providers and modes").

- **Type:** feature
- **Status:** in progress
- **Opened:** 2026-11-28 · **Closed:**
- **GitHub Issue:** none

## Summary
Visitors pick how answers are generated: their own Claude API key (as today), a local Ollama server,
a local LM Studio server, or an open-source model running in the browser with transformers.js
(WebGPU). Reference the owner gave: https://browser-rag.techie.fi/ (it calls `localhost:11434`
for Ollama and `localhost:1234/v1` for LM Studio from the page and runs `onnx-community/*` models in
the browser; it has no server and no Claude option).

## Decision
Owner decisions (2026-11-28):
- **The LangGraph workflow does not change.** A provider factory returns an LLM instance; the
  workflow, router and RAG chain only receive it and never know which model is behind it. (Today's
  `get_chat_model()` already works this way for `claude_code`, `anthropic_api` and `fake`.)
- **All four providers in the first version:** Claude API, Ollama (local, no key), LM Studio
  (local, OpenAI-compatible), transformers.js (WebGPU, several open models).
- **Build the browser relay.** The deployed workflow runs on Render, which can't reach a visitor's
  `localhost`, and transformers.js only runs in a browser. So for those providers on the deployed
  site the factory returns a relay chat model: a node's call queues the prompt for that visitor's
  run, the browser (which already polls background runs) runs it on the local model and posts the
  reply back. On the owner's PC, Ollama and LM Studio are plain server-side clients instead.
  Rejected: rewriting the workflow in TypeScript for the browser (the owner: a provider layer must
  not need workflow rewrites); local-only support (visitors on the site couldn't use their models).
- **Order:** after the Milestone 8 PR merges, on its own branch.
- Ollama means a local server with no key (Ollama Cloud with a key: possible later).

Design (lead, owner decisions 2026-11-28):
- **Relay model:** the factory gains `BrowserRelayChatModel` (a LangChain chat model). Its
  `invoke` puts the prompt (and, for structured steps, the JSON schema) in the run's outbox and
  waits; the browser polls the run, runs the prompt on its local model and posts the reply.
  Polling, not WebSockets: Vercel's external `/api` rewrite carries no WebSockets and caps each
  request at 120 s.
- **Local mode (owner's PC):** Ollama and LM Studio are server-side clients (`ChatOllama`; an
  OpenAI-compatible client for LM Studio), no relay; two new pinned dependencies. Lets the owner
  run the app and evals at zero cost.
- **Structured output:** the schema travels with the prompt; Ollama `format`, LM Studio
  `response_format` (`json_schema`); transformers.js extracts JSON from the text and retries
  once. Failures go through the existing labelled fallback.
- **Gate (owner): GitHub sign-in** for local-model runs, as for Claude live mode (they spend the
  Voyage budget and hold a server thread). Recorded examples and source search stay open.
- **Run style (owner): every local-model request is a background run** the browser polls (Ask,
  Analyse a job and Plan), so no 120 s Vercel limit; one relay path.
- **Models (owner): the visitor chooses** one model for both tiers, or a separate fast and smart
  model.
- **transformers.js (owner): 2-3 checked models**, tested for JSON output (candidates:
  Qwen2.5-1.5B-Instruct, Llama-3.2-1B-Instruct, and DeepSeek-R1-Distill-Qwen-1.5B (owner; it
  writes its reasoning in a `<think>` block first, which must be stripped before reading the
  answer or JSON); the list is confirmed when building).
- **Visitor setup:** add the site to `OLLAMA_ORIGINS` and restart Ollama; LM Studio with CORS on
  (`lms server start --cors`); Chrome 142+ asks for Local Network Access, so the first local
  call starts from a button click.
- **Build order:** 1 server-side Ollama and LM Studio (local mode); 2 relay model, endpoints,
  limits and timeouts (always-hard); 3 provider picker and browser clients for Ollama and LM
  Studio (design-advisor drafts the screen, owner approves); 4 transformers.js in a Web Worker;
  5 deployed-site checks, docs, PR; then T-030 (CSP).

Sources checked (2026-11-28): Ollama FAQ (allowed origins), Chrome's Local Network Access
guide, LM Studio structured-output docs (models under ~7B unreliable), Transformers.js v3 WebGPU.

Design notes still to settle while building:
- Search stays on Voyage: the index is `voyage-4`, so a local embedding model can't query it.
- Visitors must allow the site's origin in Ollama (`OLLAMA_ORIGINS`) and turn on CORS in LM
  Studio; Chrome may ask permission to reach local addresses. The setup box says so.
- Structured output: Ollama (`format` with a JSON schema) and LM Studio (`response_format`) can
  enforce JSON; small transformers.js models may fail it, which the labelled fallback shows.
- Always-hard areas touched: the workflow's retry and fallback limits (relay timeouts), what the
  browser may send back (untrusted model output), rate limits and run ownership for relay runs,
  whether relay runs need the GitHub sign-in (they still spend the Voyage budget).

## Changes
- Branch: `feat/t-029-provider-layer`
- PR:
- Files touched:
  - Step 1: `providers/local_servers.py` (new), `providers/factory.py`, `config.py`,
    `pyproject.toml` + `uv.lock` (`local` group: `langchain-ollama==1.2.0`,
    `langchain-openai==1.8.4`; 1.8.5 needs `langchain-core>=1.8.4`, we pin 1.8.2),
    `.env.example`, `tests/test_providers.py`, `tests/test_runtime_deps.py`
- Commits (hash, message):

## Verification
- Step 1 (2026-11-28): 947 tests pass, ruff clean; the API still imports with the new libraries
  blocked (`test_runtime_deps.py`). Real smoke run (`providers.smoke`, tracing off) through Ollama
  on `llama3.1:8b`: the plain reply and the structured `Requirement` both came back valid. LM Studio
  smoke run: pending a chat model in LM Studio (only an embedding model is installed).

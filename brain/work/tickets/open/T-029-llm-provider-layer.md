# T-029: LLM provider layer (Claude, Ollama, LM Studio, transformers.js)
Milestone 9 ticket (planned). Today's factory is `backend/src/gradpath/providers/factory.py`; modes
and live mode are in `../../../engineering/ARCHITECTURE.md` ("Providers and modes").

- **Type:** feature
- **Status:** open
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

Design notes to settle before building (lead, with the owner):
- Search stays on Voyage: the index is `voyage-4`, so a local embedding model can't query it.
- Visitors must allow the site's origin in Ollama (`OLLAMA_ORIGINS`) and turn on CORS in LM
  Studio; Chrome may ask permission to reach local addresses. The setup box says so.
- Structured output: Ollama (`format` with a JSON schema) and LM Studio (`response_format`) can
  enforce JSON; small transformers.js models may fail it, which the labelled fallback shows.
- Always-hard areas touched: the workflow's retry and fallback limits (relay timeouts), what the
  browser may send back (untrusted model output), rate limits and run ownership for relay runs,
  whether relay runs need the GitHub sign-in (they still spend the Voyage budget).

## Changes
- Branch:
- PR:
- Files touched:
- Commits (hash, message):

## Verification
TBD.

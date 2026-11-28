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
Step 2 build decisions (lead, 2026-11-28): relay runs in their own `RunStore` (2 slots, 1 per
user, apart from the Claude slot); kinds `ask`, `job`, `plan` on one poll route; the server
validates every structured reply (one retry, then the labelled fallback); bounded waits (reply
180 s (420 s since step 3, see Verification), idle 90 s, run deadline = relay budget 900 s +
the reply timeout, 40 prompts, 4 waiting); a cancel
route; an Ask routed to the workflow is charged as a plan only then. Resume import stays on
Claude.

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
- **Local address (owner, 2026-11-28): this computer only.** The picker's editable address
  accepts `localhost`, `127.0.0.1` and `[::1]` (any port), never a LAN or public host, so a
  visitor's posting and profile reach only their own PC and Chrome asks one permission
  (loopback). Rejected: LAN hosts (a second permission, more ways to send data elsewhere).
- **Picker screen (owner approved 2026-11-28, after a mockup on the real Plan page):** a pop-up
  dialog opened from a "Set up live mode" button in the form (and from "Change" on the strip),
  not an inline panel; running and failed runs stay on the page. DESIGN.md "Model provider
  picker" holds the layout and decisions 13-19 (all recommendations approved).
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
  - Step 2: `providers/relay.py`, `api/relay.py` (new), `workflows/runs.py` (`start_task`,
    `snapshot`, `refusal`, `cancel`), `api/deps.py` (`relay_access`, `relay_owner`),
    `api/limits.py` (`RELAY`), `api/ratelimit.py` (`relay` bucket), `api/main.py`,
    `providers/factory.py` (`relay=`), `config.py` (`RELAY_*`), `tests/test_relay.py`,
    `tests/test_api_relay.py`, `tests/test_demo.py`
  - Step 3 (frontend): `lib/localModels.ts`, `lib/relayRun.ts`, `lib/providerSession.ts`,
    `lib/useRelayRun.ts`, `lib/useProviderRoute.ts`, `components/ProviderPicker.tsx`,
    `components/ProviderSetup.tsx`, `components/RelayRunView.tsx` (new); `lib/api.ts` (relay
    calls; 409 shows its fixed text), `lib/types.ts`, `components/LivePanel.tsx` (split into
    `useLiveForm` and pieces), `Assistant.tsx`, `JobAnalysisView.tsx`, `PlanView.tsx`,
    `ResumeImport.tsx`, `ModeBadge.tsx`, `ModeNote.tsx`, `icons.tsx`, `app/globals.css`,
    `vitest.setup.ts`; tests for each new module and the screens. Docs: `DESIGN.md` (picker),
    ARCHITECTURE, SECURITY, WALKTHROUGH.
- Commits (hash, message):
  - `eed1291` feat: add Ollama and LM Studio as local-mode chat models (T-029)
  - `d9979bc` docs: record the Ollama and LM Studio smoke runs (T-029)
  - `d5fbb49` feat: add the browser relay chat model and relay run routes (T-029)
  - `4342797` docs: record the browser relay design, threats and real run (T-029)
  - `33ffb97` docs: design the model provider picker dialog (T-029)
  - `f57b872` feat: add the model provider picker and browser clients for Ollama and LM Studio (T-029)
  - `46a3a9b` fix: turn off Ollama thinking so large models answer within the call limit (T-029)

## Verification
- Step 1 (2026-11-28): 947 tests pass, ruff clean; the API still imports with the new libraries
  blocked (`test_runtime_deps.py`). Real smoke run (`providers.smoke`, tracing off) through Ollama
  on `llama3.1:8b`: the plain reply and the structured `Requirement` both came back valid. LM Studio
  (`qwen2.5-7b-instruct` Q4_K_M from `lmstudio-community`, 4.68 GB): three runs; both replies valid
  once the model had finished loading (one 400 while it was still loading). Gotcha: `lms server
  start` took port 1235 on this PC, not 1234, so `LMSTUDIO_BASE_URL` must match the port it prints.
- Commit `eed1291` CI green (backend, frontend, docker).
- Step 2 (2026-11-28): 992 tests pass, ruff clean. code-reviewer: no deadlock or cross-user leak;
  fixed the relay rate limit (a refused poll looked like a closed tab), quota spent by refused
  starts, a cancel route, a 90 s idle timeout for background tabs, `RecursionError` on nested
  JSON, the prompt cap labelled stage_failed, and the missing tests. Real run: a plan through the
  relay on the sample inputs, with a script as the browser forwarding prompts to Ollama
  (`llama3.1:8b`): complete, no fallback, 5 prompts in 242 s (18 requirements, 10 roadmap items,
  10 questions). The first attempt ended in the labelled fallback because that script stopped
  polling during a 133 s generation: the page must poll on its own timer (step 3).
- Left for later: each poll resends the full text of every waiting prompt (tens of KB a
  second while a slow prompt waits); fine on Vercel's free bandwidth, but a cursor could cut it.
- Step 3 (2026-11-28): frontend 436 tests, lint, typecheck and build clean (qa-checker).
  code-reviewer: fixed Stop doing nothing while a run was starting (and a start abandoned on
  unmount leaving an orphan run that held the visitor's one slot: the start is no longer aborted,
  a stale one is deleted when it answers), pagehide now reports the end (a page restored from the
  back/forward cache no longer shows a dead run), `redirect: "error"` on local requests (a redirect
  could carry the prompt off the computer), a failed reply post retried twice, an old relay result
  cleared on a validation error, stale comments. Real runs through the page (local mode, API on
  :8001 with tracing off, dev site on :3001, sample inputs) on Ollama:
  - `llama3.1:8b`: Analyse a job 70 s (21 requirements: 8 covered, 6 weak, 5 not covered, 2
    eligibility); Ask answered via the knowledge base (partial); Plan in about 2 min, finished with
    open issues (one revision; the check flagged 90 h of roadmap against 48 available). A second
    plan took one model call: the model marked all 12 requirements as eligibility, so nothing was
    left to study (model quality, not a client fault). Stop: the page ended at once and the API
    got `DELETE` 204. The page checked in about once a second throughout.
  - `qwen38-27b-iq4xs`: the first attempt ended in the labelled partial result: the first call ran
    past the 170 s client limit. Cause: the model's hidden thinking pass (measured on a small
    structured prompt: 9.1 s with thinking, 4.5 s without; `think: false` is accepted by
    `llama3.1:8b` too). Decision (lead): send `think: false` to Ollama. Retry: complete,
    "Checked" with no blocking issues, 5 model calls in under 5 minutes, specific gap reasons.
  - LM Studio `qwen3.8-27b@iq3_xxs` (CORS turned on with `lms server start --cors --port 1235`
    for the test, off again after; RAM cleared first, only that model loaded, 17.3 GB free):
    Connect listed 4 models (one an embedding model, which can't chat: filter it). The plan
    reached step 5 in 6 min, then ended in the labelled partial result
    (`dependency_unavailable`): the roadmap and interview-question stages run in parallel, the
    page answers one prompt at a time, and the server's 180 s reply timer starts when a prompt is
    created, so the second prompt used up its time waiting behind the first. Fix (owner,
    2026-11-28): the page keeps answering one prompt at a time (parallel calls would share the
    GPU and may need more memory), and the limits go up: `RELAY_REPLY_TIMEOUT_S` 180 -> 420 s,
    the page's per-call limit 170 -> 400 s. Rejected for now: starting the reply timer when the
    page takes a prompt (exact, but a new route in an always-hard area). **Known limit** (review):
    two parallel stages only succeed if both calls together finish within 420 s; if slow models
    still hit it, that timer change is the next step. Measured why LM Studio was slower than
    Ollama: same speed per token, but its Qwen model always writes hidden reasoning first (287
    characters on a tiny prompt; `/no_think` in the prompt did not stop it) and its
    OpenAI-compatible API has no switch like Ollama's `think: false`. Embedding models are now
    left out of the model menu.
  - Seen once, not reproduced: the run view's elapsed timer stuck at 0:25 while the server said
    108 s (the per-call "Waiting for" timer kept counting).

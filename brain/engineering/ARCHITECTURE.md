# ARCHITECTURE.md
How GradPath AI is built: stack, layout, components, data flow, modes, deployment and known limits.
What it must do is in `../product/REQUIREMENTS.md`; metrics in `EVALUATION.md`; the reasons behind
each choice in `WALKTHROUGH.md`. Nothing is implemented yet: this is the agreed design.

## Stack
| Layer | Choice | Notes |
|---|---|---|
| Language / tooling | Python 3.13, uv | Exact versions pinned in `uv.lock` |
| API | FastAPI + Pydantic | Long workflows return a job ID; the client polls status |
| Workflow | LangGraph | Typed state, conditional edges, bounded revision |
| Building blocks | LangChain | See "LangChain split" below |
| LLM | Claude | Through our provider layer (Claude Code locally, Anthropic API in live mode) |
| Embeddings | Voyage AI | `langchain-voyageai` |
| Vector store | Qdrant | Local embedded mode in dev; Qdrant Cloud free when deployed; `langchain-qdrant` |
| Workflow records | SQLite (TBD) | Single user; Postgres only with multi-user |
| Tracing / eval | LangSmith (optional) + local JSON logs | App runs fully without LangSmith |
| Frontend | Next.js + Tailwind CSS | From its milestone |
| Hosting | Vercel (frontend), Render (backend), Qdrant Cloud | Free tiers |

## LangChain split
Use LangChain for standard building blocks; write the parts interviewers ask about ourselves.

| LangChain | Our own code |
|---|---|
| `ChatAnthropic` and `.with_structured_output()` | Retrieval service: query building, metadata filters, evidence selection, citations, abstention; hybrid fusion (RRF) and reranking as eval experiments (T-010) |
| A custom `ChatClaudeCode` (`BaseChatModel` subclass) for the Pro plan | Query router (rules + a small validated classification) |
| `@tool` + LangGraph `ToolNode` for retrieval | Fallback policy |
| Document loaders, `RecursiveCharacterTextSplitter` | Evaluation metrics (Recall@K, Precision@K, MRR, routing accuracy, citation checks) |
| `VoyageAIEmbeddings`, `QdrantVectorStore` | Demo-run recording and replay; visitor key handling |

`langchain-core` is also a LangGraph dependency.

## Layout (planned)
```
backend/          uv project (pyproject.toml, uv.lock)
  src/gradpath/
    config.py     typed settings from the repo-root .env (secrets as SecretStr)
    api/          FastAPI routes
    providers/    chat-model factory: ChatClaudeCode, ChatAnthropic, fake model for tests (built)
    ingestion/    load, clean, chunk, embed, index
    retrieval/    retrieval service + retrieval tool
    router/       query router and route schema
    workflows/    LangGraph graph, state, nodes
    demo/         record and replay of runs
    evaluation/   metric code and eval runners
    schemas/      Pydantic models
    tracing.py    LangSmith on/off rules
  tests/
frontend/         Next.js 16 App Router + Tailwind 4 (T-011, Milestone 6)
  app/            routes: / (Ask), /job, /plan, /profile; layout.tsx; globals.css (design tokens)
  components/     UI parts (SiteHeader, ThemeToggle, ...)
  lib/            api.ts (typed client, fixed error messages), types.ts (mirrors the Pydantic
                  models), safeUrl.ts (the only way a citation becomes a link), theme.ts
  public/         theme-init.js (applies the saved theme before first paint)
knowledge_base/   raw/, processed/, source_manifest.csv
evaluation/       labelled datasets (retrieval questions, routes, workflow cases)
demo_runs/        recorded runs for demo mode (sample profile only)
private/          owner's real profile or resume (gitignored)
```

## Request flow
```
request -> router -> traditional_rag | agentic_workflow -> validation -> response + citations
                        \-- fallback (labelled partial result) on failure --/
```
- **Router:** returns `{route, reason, requires_user_profile, requires_multi_step_workflow}`; `route`
  is an enum; unparseable output falls back to a safe default: `traditional_rag`. Built in T-006
  (`router/`): rules for certain cases, then Haiku names a kind and a fixed table picks the route.
- **Entry point:** `POST /api/assist` (`router/assist.py`): route, then RAG, the workflow, or a
  fixed needs-input / unsupported reply; one route-log line per request (`logs/routes.jsonl`).
- **Traditional RAG:** retrieve -> answer from evidence only -> citations, or abstain. (Reranking
  and hybrid search were measured in Milestone 5 and not adopted; see `EVALUATION.md`.)
  Callable from the API and as a tool inside the workflow.
- **Agentic workflow (LangGraph):** `analyze_job` and `analyze_profile` in parallel ->
  `retrieve_knowledge` -> `analyze_gaps` -> `plan_roadmap` -> `evaluate` -> `revise` (bounded) or
  `finalize`. State is a typed `CareerPrepState` (see the spec, section 7); every node output is
  validated before the next node uses it.
  Built in `workflows/` (T-003): `state.py` (state + `WorkflowContext` runtime context for the
  retrieval service and models), `schemas.py`, `nodes.py`, `graph.py` (`build_graph`,
  `run_workflow`). The critic -> revise loop is bounded by `WORKFLOW_MAX_REVISIONS` (default 1,
  max 3), a counter kept by graph code, and `recursion_limit` = 7 + 2 per revision + 2. Joins use
  `add_edge([a, b], c)`, and `revise` re-plans only the roadmap.
- **Fallback:** on repeated tool failure, step/time budget overrun, invalid output after retries:
  keep the request, say which stages finished, run traditional RAG if it can still help, label the
  result partial, log the reason. Built in T-006: `run_workflow` streams the graph and ends in
  `fallback.build_fallback` (status `fallback`, `FallbackInfo`); budget `WORKFLOW_TIME_BUDGET_S`
  (default 300 s) checked between steps. No evidence means "the knowledge base doesn't cover this", never an
  unsupported answer.

## Providers and modes
All LLM calls go through one factory that returns a LangChain chat model.

| `LLM_PROVIDER` | Model | Used for |
|---|---|---|
| `claude_code` | `ChatClaudeCode`: calls Claude through the Claude Agent SDK (bundles the Claude Code CLI), built-in tools and user settings off | Local runs on the owner's Pro plan; recording demo runs |
| `anthropic_api` | `ChatAnthropic` with a server key or the visitor's key | Live mode |
| `fake` | LangChain fake chat model with canned responses | Tests |

`APP_MODE` (T-018, owner decision 2026-11-20) picks one of three modes; the default is `demo`
because it is the safe one for a server:

| `APP_MODE` | Where | Model routes | Retrieval (Voyage + Qdrant) | Tracing |
|---|---|---|---|---|
| `local` | Owner's machine | On, with the server's credentials | Opened at startup | Allowed (`tracing.decide`) |
| `demo` | Deployed | Off: 403 from `api/deps.require_model_routes` | Opened only when `VOYAGE_API_KEY` is set, for source search (`POST /api/search`, no model call); a failure to open turns search off instead of stopping startup, so demo still needs no keys | Off |
| `live` | Deployed | Off until visitor keys are wired in (T-018 step 4) | Opened at startup | Off |

The recordings in `demo_runs/` (`demo/library.py`) are served in every mode by `GET /api/demo` and
`GET /api/demo/{id}`. Each JSON file holds the inputs and the exact response, validated against the
same response models as the live routes; a file that drifts is skipped and `test_demo.py` fails.
They are made by `demo/record.py` (step 2): a fixed list of examples run through the same functions
the routes call, on the committed sample posting and fictional profile only, never traced, each
file scanned for contact details, keys and local paths before it is written.

**Source search (T-018 step 4):** `POST /api/search {query}` (`rag/sources.py`, `api/search.py`) is
the retrieval half of RAG for visitors without a key: one Voyage request, the top passages (at most
2 per document) as citations with a 600-character excerpt, an `insufficient` flag, and a rules-only
route preview (`router/rules.rule_kind` + the route table; null with a note when only the model
could decide). No model call, so it is open in every mode; 503 when the server has no retrieval;
its own concurrency cap (`limits.SEARCH`, 2); the query is never logged.

**Sources date (T-018 step 3):** ingest writes `knowledge_base/index_info.json` (committed) after
each successful index rebuild: the oldest and newest page fetch dates plus document and chunk
counts (`ingestion/index_info.py`; `ingest --info-only` rewrites it from the processed chunks with
no fetch or Voyage). The API reads it at startup in every mode and `/api/health` returns
`sources_as_of` (the oldest date: an "as of" claim every source supports) and `sources_newest`; the
footer shows "Sources as of {date}". Manual (owner-saved) sources are counted but don't set the
dates (their stamp is a file time). Read once at startup: restart the API after a re-ingest.

Deployed site:
- **Demo mode (default):** replays recorded runs from `demo_runs/`; no model or embedding calls, no
  keys needed.
- **Live mode:** the visitor pastes an Anthropic key. It travels over HTTPS with each request, lives
  only in memory for that request, and is never stored, logged, traced or returned. Query embeddings
  use the owner's Voyage key with a per-IP rate limit, and live routes need a shared passcode in a
  header (owner decision 2026-11-20, T-018).

## Tracing
Built in Milestone 2 (`tracing.py`, ticket T-002). One function, `configure_tracing(settings)`, decides
for the whole process; the API lifespan and the model-calling CLIs (`rag.ask`, `jobs.cli`, `workflows.cli`,
`providers.smoke`) call it at start and `flush()` at exit.

| Rule | Where |
|---|---|
| On only if `LANGSMITH_TRACING=true` **and** `LANGSMITH_API_KEY` is set in `.env` | `tracing.decide` |
| Off unless `APP_MODE=local`: never on the deployed site (demo or live), whatever `.env` says | `tracing.decide` |
| Off from import: `gradpath.tracing` sets `enabled=False` when first imported (retrieval and providers import it), so ingest, probe and eval never trace. Only `configure_tracing` turns it on, from our settings; langsmith's own variables (`LANGSMITH_TRACING`, `LANGCHAIN_TRACING_V2`) can't act alone | `tracing.py` |
| Uploads go only to `LANGSMITH_ENDPOINT` from settings (default LangSmith US); refused if `LANGSMITH_RUNS_ENDPOINTS` (extra destinations) is set | `tracing.decide`, `configure_tracing` |
| A request (visitor) API key is refused while tracing is on (checked when the model is built) | `providers.factory.get_chat_model` |
| Redacted client-side before upload: langsmith's secret rules + Voyage keys, emails, phone numbers. Not redacted: names, addresses, phone numbers without separators; hence the sample-profile rule | `tracing.redact` (the client's anonymizer) |
| Tests never trace (autouse fixture) | `tests/conftest.py` |

Trace tree: `answer_question` / `analyze_job` (chain) -> `retrieve` / `retrieve_many` (retriever;
output is chunk ids + scores only, the text is already in the prompt) -> the model call. Traces hold
full prompts, so with tracing on use only public postings and the sample profile, never a real
profile. Free plan: ~5k traces a month, ~14-day retention. Local JSON logs (route, nodes, fallback
events) come with the workflow in Milestone 3.

## Ingestion and retrieval
Ingestion (built, `ingestion/`, details in `WALKTHROUGH.md`): manifest (approved rows) -> polite
fetch with cache (`knowledge_base/raw/`, or `knowledge_base/manual/` for sites that block scripts)
-> clean -> heading-aware chunking (1200 chars, 150 overlap) -> `processed/<doc>.jsonl` -> Voyage
`voyage-4` embeddings (rate-limited + on-disk cache) -> Qdrant collection `gradpath_kb`, rebuilt
after all embeddings succeed. Run: `uv run python -m gradpath.ingestion.ingest [--dry-run]
[--refresh] [--only DOC ...]`. `raw/`, `processed/` and `manual/` are gitignored.

Chunk metadata: `document_id, chunk_id (<doc>:<page>:<n>), title, section (heading path),
source_url, source_type, collection, topic, license_or_usage_notes, retrieved_at`. Every source is
listed in `knowledge_base/source_manifest.csv` with its URL, licence and fetch URLs; nothing is
ingested without the owner's approval.

First corpus (2026-11-17 dry run): 18 sources, 52 pages, 956 chunks, ~188K estimated tokens.
Corpus v2 (2026-11-19, T-009): 27 approved sources, 87 pages, 1,592 chunks; adds Docker,
Kubernetes, CI/CD, HTTP caching, RabbitMQ, Kafka, behavioural interviews and LLM/RAG
(collection `ai_engineering`). Docs template markup (Hugo, Liquid, JSX) is stripped while cleaning.

Retrieval (built): `RetrievalService.search` -> top-k chunks above `retrieval_min_score` (0.45,
probe-calibrated), optional metadata filters and per-document cap; `insufficient` when none qualify.
Semantic-only by decision (Milestone 5, T-010): BM25 + RRF hybrid (`retrieval/sparse.py`) and local
cross-encoder reranking (`retrieval/rerank.py`, fastembed) both measured worse and are used only by
`evaluation/retrieval_eval.py` (`--hybrid`, `--rerank`). fastembed models download once into
`backend/data/models/` (gitignored).

Traditional RAG (built): `rag.answer_question` -> `POST /api/chat`. Abstains without a model call
when retrieval is insufficient; evidence in delimited untrusted blocks; Sonnet structured reply;
citations verified against retrieved ids. API endpoints so far: `GET /api/health`, `POST /api/chat`, `POST /api/jobs/analyze`,
`POST /api/career/prepare` (the workflow; synchronous; body `WorkflowInput`; errors mapped to
fixed messages, including `GraphRecursionError` -> 500), `POST /api/profile/from-resume` (T-014:
pasted resume text -> a draft `UserProfile` + notes; one fast-tier call, never traced, nothing
stored; `profiles/resume.py`), and `POST /api/career/runs` + `GET /api/career/runs/{id}` (T-016:
the workflow in a background thread behind a uuid4 run id; the browser polls every 2 s for stage
states and the result; `/api/assist` starts a run for the workflow route and returns `started`).
Runs live in memory in one process (`workflows/runs.py`): deploy as a **single worker**, and know
that a restart or `--reload` forgets running and finished runs (the poll then gets 404).

## Security
Retrieved content, uploads and JDs are untrusted data: delimited in prompts, never followed as
instructions. Upload type and size limits. Keys only on the server or per request. No sensitive profile
content in logs. Specific defences: TBD per milestone (always-hard area, see `CLAUDE.md`).

## Known limits
- `claude_code` mode is bound by the Pro plan's usage limits and is slower than the API; large eval
  runs may hit the limit.
- `claude_code` mode: the Agent SDK's bundled CLI needs a one-time Claude login on the PC. Calls made
  from a shell inside a Claude Code session inherit that session's variables, so test from a normal
  terminal. An `ANTHROPIC_API_KEY` in the process environment would make the CLI bill the API
  instead of the plan; settings read `.env` without exporting it.
- Structured output: `ChatAnthropic` must use `method="json_schema"` (current models reject a forced
  tool call); `ChatClaudeCode` uses the SDK's `output_format`. Both go through `with_structure()`.
- The 0.45 cosine threshold doesn't separate near-topic uncovered questions (labels v1.3: covered
  kept 97%, uncovered rejected 67%); no retrieval-side fix found in Milestone 5.
- LangSmith free plan: about 5k traces a month, about 14 days of retention. Results are kept in
  `EVALUATION.md`, not only in LangSmith.

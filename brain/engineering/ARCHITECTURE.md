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
| `ChatAnthropic` and `.with_structured_output()` | Retrieval service: query building, metadata filters, hybrid fusion, reranking, evidence selection, citations, abstention |
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
frontend/         Next.js (later)
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
  is an enum; unparseable output falls back to a safe default (TBD which).
- **Traditional RAG:** retrieve -> (rerank) -> answer from evidence only -> citations, or abstain.
  Callable from the API and as a tool inside the workflow.
- **Agentic workflow (LangGraph):** `analyze_job` and `analyze_profile` in parallel ->
  `retrieve_knowledge` -> `analyze_gaps` -> `plan_roadmap` -> `evaluate` -> `revise` (bounded) or
  `finalize`. State is a typed `CareerPrepState` (see the spec, section 7); every node output is
  validated before the next node uses it.
- **Fallback:** on repeated tool failure, step/time budget overrun, invalid output after retries:
  keep the request, say which stages finished, run traditional RAG if it can still help, label the
  result partial, log the reason. No evidence means "the knowledge base doesn't cover this", never an
  unsupported answer.

## Providers and modes
All LLM calls go through one factory that returns a LangChain chat model.

| `LLM_PROVIDER` | Model | Used for |
|---|---|---|
| `claude_code` | `ChatClaudeCode`: calls Claude through the Claude Agent SDK (bundles the Claude Code CLI), built-in tools and user settings off | Local runs on the owner's Pro plan; recording demo runs |
| `anthropic_api` | `ChatAnthropic` with a server key or the visitor's key | Live mode |
| `fake` | LangChain fake chat model with canned responses | Tests |

Deployed site:
- **Demo mode (default):** replays recorded runs from `demo_runs/`; no model or embedding calls, no
  keys needed.
- **Live mode:** the visitor pastes an Anthropic key. It travels over HTTPS with each request, lives
  only in memory for that request, and is never stored, logged, traced or returned. Query embeddings
  use the owner's Voyage key with a rate limit (TBD, see REQUIREMENTS).

## Tracing
- Local development: LangSmith on when `LANGSMITH_TRACING=true` and a key is set; otherwise local JSON
  logs (route, nodes, tool calls, errors, fallback events, latency, tokens).
- Deployed site: LangSmith off for visitor requests. Traces contain full prompts, so local tracing uses
  the sample profile, not real personal data.

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

Retrieval (built): `RetrievalService.search` -> top-k chunks above `retrieval_min_score` (0.45,
probe-calibrated), optional metadata filters and per-document cap; `insufficient` when none qualify.

Traditional RAG (built): `rag.answer_question` -> `POST /api/chat`. Abstains without a model call
when retrieval is insufficient; evidence in delimited untrusted blocks; Sonnet structured reply;
citations verified against retrieved ids. API endpoints so far: `GET /api/health`, `POST /api/chat`.

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
- LangSmith free plan: about 5k traces a month, about 14 days of retention. Results are kept in
  `EVALUATION.md`, not only in LangSmith.

# GradPath AI

An AI career-preparation app for new graduates. Give it a job description and your profile, and it
builds an evidence-backed preparation roadmap: the role's requirements, a skills-gap analysis with
confidence levels, prioritised learning steps with cited resources, and practice questions.

It is a portfolio project that demonstrates adaptive RAG: a router sends focused questions through a
single retrieval-and-generation pass, and multi-step requests (analyse this job against my profile and
plan my preparation) through a LangGraph agentic workflow. Both share one retrieval service, and both
are measured with a labelled evaluation set.

> Status: Milestones 0-6 done: the backend (RAG, the LangGraph workflow, the router and fallback,
> evaluations) and the Next.js frontend run locally. Next: demo and live modes (7), then deploy (8).
> The milestone story is in `brain/work/MILESTONES.md`.

## What you can do
| Screen | What it does |
|---|---|
| Ask (`/`) | Ask a backend preparation question and get an answer with citations, or a clear "not covered". Add a job posting and a profile and the router sends it to the full workflow instead. |
| Analyse a job (`/job`) | Paste a posting: each requirement with its coverage in the knowledge base, the quote from the posting, a study note and its sources. |
| Plan (`/plan`) | Posting + profile -> skills gap, roadmap with cited resources, interview questions. Runs in the background (1.5-5 min) with live stage progress; partial results are labelled as partial. |
| Profile (`/profile`) | Your profile, kept only in this browser; can be filled from pasted resume text. |

## Stack
Python 3.13 · FastAPI · LangGraph · LangChain · Claude (Anthropic) · Voyage AI embeddings · Qdrant ·
LangSmith tracing and evaluation · Next.js + Tailwind CSS.

## Modes
| Mode (`APP_MODE`) | Where | Model calls |
|---|---|---|
| `local` | Your machine | Claude through Claude Code, on your own Claude subscription |
| `demo` (the default) | Deployed site | None: replays recorded runs made with a sample profile; needs no keys |
| `live` (in progress) | Deployed site | Your Anthropic API key, sent per request, never stored |

`APP_MODE` defaults to `demo`, the safe choice for a server: the model routes answer 403 and only
the recorded examples (`/api/demo`) are served. Set `APP_MODE=local` in `.env` to run models on your
own machine (`.env.example` already does).

## Setup
Needs [uv](https://docs.astral.sh/uv/) and Python 3.13.

```bash
cp .env.example .env          # then fill in the keys you have (APP_MODE=local); demo mode needs none
cd backend
uv sync
uv run pytest -q              # no keys or network needed
uv run pytest --html=reports/tests.html --self-contained-html   # report to open in a browser
```

**Local live mode on your Claude plan** (`LLM_PROVIDER=claude_code`): the Claude Agent SDK ships
its own Claude Code CLI. Log in once from a normal terminal (not one running inside Claude Code):

```bash
.venv/Lib/site-packages/claude_agent_sdk/_bundled/claude.exe   # Windows; type /login, then /exit
uv run python -m gradpath.providers.smoke                      # one tiny real call
```

Make sure `ANTHROPIC_API_KEY` is not set in your shell, or Claude Code bills the API instead of your
plan. To use the API instead, set `LLM_PROVIDER=anthropic_api` and `ANTHROPIC_API_KEY` in `.env`.

## Run the app locally
Needs Node.js 20.9 or newer for the frontend. Build the knowledge-base index once (needs
`VOYAGE_API_KEY` in `.env`; it caches embeddings, so a re-run doesn't spend tokens again):

```bash
cd backend
uv run python -m gradpath.ingestion.ingest
```

Then start the API and the frontend in two terminals:

```bash
cd backend
uv run uvicorn gradpath.api.main:app        # API on http://127.0.0.1:8000 (docs at /docs)
```

```bash
cd frontend
npm ci
npm run dev                                  # http://localhost:3000; /api/* goes to the API
```

Local Qdrant allows one process at a time: stop the API before running ingest or an evaluation.
Frontend checks: `npm run lint && npm run typecheck && npm test && npm run build`.

## Documentation
Requirements, architecture, evaluation results and the design decisions live in `brain/`.

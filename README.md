# GradPath AI

An AI career-preparation app for new graduates. Give it a job description and your profile, and it
builds an evidence-backed preparation roadmap: the role's requirements, a skills-gap analysis with
confidence levels, prioritised learning steps with cited resources, and practice questions.

It is a portfolio project that demonstrates adaptive RAG: a router sends focused questions through a
single retrieval-and-generation pass, and multi-step requests (analyse this job against my profile and
plan my preparation) through a LangGraph agentic workflow. Both share one retrieval service, and both
are measured with a labelled evaluation set.

> Status: project setup. No code yet. See `brain/work/TASKS.md` for the milestones.

## Stack
Python 3.13 · FastAPI · LangGraph · LangChain · Claude (Anthropic) · Voyage AI embeddings · Qdrant ·
LangSmith tracing and evaluation · Next.js + Tailwind CSS.

## Modes
| Mode | Where | Model calls |
|---|---|---|
| Local live | Your machine | Claude through Claude Code, on your own Claude subscription |
| Demo (default online) | Deployed site | None: replays recorded runs made with a sample profile |
| Live with your key | Deployed site | Your Anthropic API key, sent per request, never stored |

## Setup
Needs [uv](https://docs.astral.sh/uv/) and Python 3.13.

```bash
cp .env.example .env          # then fill in the keys you have; demo mode needs none
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

## Documentation
Requirements, architecture, evaluation results and the design decisions live in `brain/`.

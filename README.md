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
TBD (Milestone 1). Copy `.env.example` to `.env` and fill in the keys you have; demo mode needs none.

## Documentation
Requirements, architecture, evaluation results and the design decisions live in `brain/`.

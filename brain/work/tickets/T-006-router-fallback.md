# T-006: Milestone 4: router + fallback
Index entries go in `../TASKS.md` (open) and `../DONE.md` (closed).

- **Type:** feature
- **Status:** in progress
- **Opened:** 2026-11-18 · **Closed:**
- **GitHub Issue:** none

## Summary
Choose the cheapest path that works for each request: traditional RAG for focused questions, the
LangGraph workflow for job + profile preparation. Record the route and why. When the workflow
cannot finish, return a clearly labelled partial result (what finished, what didn't, grounded RAG
help where it still applies) instead of an error. Measure routing accuracy against a labelled set
and compare adaptive routing with always-RAG and always-workflow (spec section 2A).

## Decision
Plan proposed 2026-11-18; waiting for the owner's answers (see `../MILESTONES.md`, Milestone 4).
High-risk area: the workflow's fallback limits (code-reviewer + qa-checker whatever the size).

## Changes
- Branch: `feat/t-006-router-fallback`
- PR:
- Files touched:
- Commits (hash, message):

## Verification

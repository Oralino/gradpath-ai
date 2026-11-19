# T-011: Next.js frontend (Milestone 6)
The Milestone 6 ticket: a Next.js + Tailwind UI over the existing API. Milestone story in
`../MILESTONES.md`, open items in `../TASKS.md`, look and feel in `../../design/DESIGN.md`.

- **Type:** feature
- **Status:** in progress
- **Opened:** 2026-11-19 · **Closed:**
- **GitHub Issue:** none

## Summary
Make GradPath usable without the terminal: ask a question, analyse a job description, and run the
full preparation workflow (job + profile -> gaps -> roadmap -> interview questions) from a browser.
Results show clickable citations, honest statuses (a workflow fallback and a partial answer are
shown as partial, never as complete) and clear errors. Model and retrieved text are untrusted and
rendered as plain text (`../../engineering/SECURITY.md`, "From Milestone 6").

## Decision
Open, waiting for the owner (asked 2026-11-19):
- `DESIGN.md` draft (design-advisor) for approval before any frontend code.
- Partial answers: a `partial` status from the model (backend change) or a UI label from existing
  fields.
- Long workflow runs (80-300 s): keep the synchronous call with an honest progress view, or add a
  run id with status polling (`ARCHITECTURE.md` plans the latter).
- Whether answer-quality items 2-4 (answer eval set, grounding check, eval re-runs as a release
  check) go into `TASKS.md`.

Versions checked 2026-11-19 against the npm registry and the official install guides: Next.js
16.4.6 (App Router, Turbopack default, Node >= 20.9; local Node is 24.13.1), React 19.3.1,
Tailwind CSS 4.3.5 with `@tailwindcss/postcss` 4.3.5 (`@import "tailwindcss"`, no config file),
TypeScript 7.0.2. Pinned exactly when the app is created.

## Changes
- Branch: `feat/t-011-frontend`
- PR:
- Files touched:
- Commits (hash, message):

## Verification
To do: frontend lint, type check, unit tests and build; backend tests stay green; a manual run
against the local API on the Pro plan (owner); design-advisor critique; release checks.

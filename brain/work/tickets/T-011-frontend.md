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
Owner decisions 2026-11-19:
- **Partial answers:** a backend `partial` status (the answer model also returns what the evidence
  doesn't cover; code sets the status). Rejected: a UI-only label, because nothing in `ChatAnswer`
  marks partiality, so it would mean brittle phrase matching. Own ticket (schema, prompt, tests).
- **Long runs:** a run id with status polling (real finished stages from `node_log`, survives a
  reload, matches `ARCHITECTURE.md`). Rejected: keeping the synchronous call, which can't show real
  progress and can't really stop a run. Own ticket; the workflow's limits are an always-hard area.
- **Answer-quality items 2-4** go into `TASKS.md`, to do before Milestone 7's public demo.
- **Look:** approve `DESIGN.md` after a visual mock-up (private page with fake data, not in the repo).
- **Resume:** pasted resume text fills the profile (Haiku extracts it, the owner reviews it, contact
  details dropped, nothing stored). Rejected for now: the resume as a third input to every route
  (repeats the profile, touches router, workflow and evals); PDF upload waits for Milestone 7.
- **Job posting input:** pasted text only. Rejected: a URL field (server-side fetch of visitor URLs
  is SSRF; job sites block scripts). The UI says "Paste a job posting".
- **Copy:** no motivational quotes, slogans or marketing filler anywhere in the UI.

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

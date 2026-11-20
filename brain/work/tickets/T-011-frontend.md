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
Tailwind CSS 4.3.5 (`@import "tailwindcss"`, no config file). Pinned exactly at scaffold time:
`create-next-app@16.4.6` now wires Tailwind through the `@tailwindcss/turbopack` loader in
`next.config.ts` (no PostCSS), so we kept that; TypeScript 5.9.3 (the template's major, not 7);
`@types/node` 24 (Vitest 5 needs >= 22); Vitest 5.1.1 + Testing Library 16.3.3 + jsdom 31.0.1 per
the Next.js 16 testing guide, with Vite's built-in tsconfig paths instead of `vite-tsconfig-paths`.

Step 1 decisions: the browser calls same-origin `/api/*` and Next rewrites it to FastAPI (no CORS
rule, the backend address stays server-side); one API client (`lib/api.ts`) turns every error into
a fixed message and keeps only field paths from a 422 (FastAPI echoes the input there); the only
way a citation becomes a link is `lib/safeUrl.ts` (http/https, no user:pass); the theme script is
a static file, not inline, so a strict CSP stays possible.

Step 2 (Ask screen) decisions: built before T-012 (owner, 2026-11-20) to test the stack end to end
first; the `partial` answer state is added when T-012 lands (`TODO(T-012)` in `Assistant.tsx`). A
`prepared` result shows only its status heading and badge until the Plan screen exists
(`TODO(T-011 Plan screen)`); a `prepared` response with no result shows a stopped panel rather than
a "Checked" badge. The profile in the tray is the fictional sample only, until the Profile screen.
Found: CI's type check failed on `LayoutProps` because Next generates that type during a build;
`typecheck` now runs `next typegen` first (`8122e7b`).

Safe markdown subset (owner decision 2026-11-20, after seeing raw `**` in a real answer): own
parser to data plus fixed React elements, no dependency, links reduced to text, `#` as bold text;
always-hard area, so code-reviewer and qa-checker ran. Rejected: plain-text prompt; `react-markdown`.

## Changes
- Branch: `feat/t-011-frontend`
- PR:
- Files touched:
- Commits (hash, message):

## Verification
To do: frontend lint, type check, unit tests and build; backend tests stay green; a manual run
against the local API on the Pro plan (owner); design-advisor critique; release checks.

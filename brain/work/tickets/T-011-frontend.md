# T-011: Next.js frontend (Milestone 6)
The Milestone 6 ticket: a Next.js + Tailwind UI over the existing API. Milestone story in
`../MILESTONES.md`, open items in `../TASKS.md`, look and feel in `../../design/DESIGN.md`.

- **Type:** feature
- **Status:** done (PR waiting for the owner)
- **Opened:** 2026-11-19 · **Closed:** 2026-11-20
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

Profile screen (step 7) decisions: the profile lives only in localStorage (`gradpath-profile`) and
is sent only inside an `/api/assist` request the visitor makes. A stored profile is re-validated on
load with the backend's own limits and dropped if it would be rejected (tampered or old data never
reaches the API as a 422). Lengths count Unicode code points like Python's `len()`, not UTF-16
units. Errors appear after the first save attempt and are recomputed on every edit. "Fill from a
resume" waits for its backend endpoint (TASKS). Found and fixed: a focus test raced the effect that
moves focus under full-suite load; focus checks after an async render now use `waitFor`.

Job screen (step 9) decisions: rows are a list of self-labelled items, not a table; chips are
one per page, labelled "Title: Section" so two chunks of one source stay distinguishable; the
posting is handed to the Ask tray through sessionStorage (bounded, read once) until the Plan screen
exists (`TODO(T-011 Plan screen)`). Found in the real run: duplicate-looking chips (fixed here) and
raw GitHub citation links (T-015). Commit `c160c5d`.

Plan screen (step 10, `f514780`; built in a parallel session against the T-016 contract):
- **What it does:** live stage progress from polling; honesty states for all four statuses;
  sections with in-page links; gaps grouped by status with Required before Preferred; a roadmap
  rail; interview questions; corrections (up to 10 × 500 characters) and a re-run.
- **Storage:** the last plan and the run id are kept in sessionStorage. A stored plan is
  re-validated, and size-capped, before it is shown.
- **Departures from `DESIGN.md`:**
  - the result h2 sits above its banner, to keep the heading order;
  - the input rows stay visible instead of collapsing to "Inputs: … [Edit inputs]";
  - a run started from the Ask screen lives in memory only (`/plan` resumes after a reload);
  - in-page links don't scroll smoothly yet.
- **Review fixes:**
  - a corrupted stored plan could crash every reload;
  - only the two known server error texts are shown;
  - a busy re-run keeps the old plan;
  - five failed polls in a row show "Can't reach the server" instead of a silent 5-minute wait.

Design critique (2026-11-20, design-advisor on Sonnet, from 50 screenshots of the four screens in
both themes at 1280 and 375 px, with real backend data): no blockers. Fixed in `43a4b71`:
- Plan banner issues stack under their badge below `sm`; citation chips put the hostname on its own
  line below `sm`, cut titles at a word within 60 characters (was 40, mid-word) and show the
  hostname muted without a second link colour;
- the type scale as written: every result h2 is `text-title`, Job requirement groups are
  `text-heading`;
- Ask, Job and Profile keep `max-w-3xl` but align left with the wordmark, like Plan;
- loading copy from DESIGN.md ("Searching the knowledge base and writing an answer...") instead of
  "Working on it";
- the roadmap step square fits two digits; the Job result drops its outer box below `sm`; the
  progress view is no longer a card inside the form card; "Build plan again" once a plan is shown;
- smooth scrolling for in-page links under `motion-safe`, with the plan sections focusable
  (`tabIndex=-1`), which closes the step 10 "no smooth scroll" departure.
Not changed, with the reason:
- "Medium confidence" on every gap card stays: it is the workflow's own confidence, and hiding the
  common value would hide data.
- Slashed zeros come from Atkinson Hyperlegible Next itself, a legibility choice of the font.
- Step 10 departures kept after the critique: the result h2 above its banner, the visible input
  rows, the "Partial plan: not fully checked" wording, and an Ask-started run held in memory only
  (after a reload the Ask screen has no question to show it against; `/plan` resumes its own
  runs). DESIGN.md (design-advisor, owner approves) should record the visible input rows and the
  "Build plan again" label.

## Changes
- Branch: `feat/t-011-frontend`
- PR: (waiting for the owner)
- Files touched: `frontend/` (new app), `backend/src/gradpath/api/` (runs, profile), workflow
  runs (T-016), docs in `brain/`. Related tickets T-012 to T-017 hold their own file lists.
- Commits: `git log --grep=T-011`; the last ones are `43a4b71` (design critique fixes) and
  `3edee74` (retrieval re-check).

## Verification
- Frontend: lint, type check and 189 Vitest tests clean; build runs in CI. Backend: ruff clean, 531
  tests (CI green on every push).
- Real runs through the UI against the local API: Ask, Job, Plan (step rows above); after the
  critique fixes, Job (16-17 requirements in ~26 s) and the stored Plan rechecked at 375 and
  1280 px in both themes.
- Release checks (2026-11-20, CLAUDE.md "Release checks"):
  - Secret and personal-data scan of `main...HEAD`, the commit messages and logs: no keys, no
    tracked `.env`, no AI attribution; sample data is fictional. One find: a local file path with
    the owner's Windows user name in the T-016 ticket, removed in `2be7aca` (it stays in the
    history of `af3ee4f`; rewriting pushed history needs the owner). `demo_runs/` does not exist yet.
  - Demo mode with no keys: not applicable yet. Milestone 7 builds `APP_MODE` (TASKS: the API
    still needs `VOYAGE_API_KEY` to start).
  - Visitor key in logs, traces or responses: not applicable yet. No route accepts a visitor key
    until Milestone 7; the API log of the real runs shows request lines only. Found on the way: a
    422 echoes the rejected value to its sender (TASKS, before live mode).
  - Retrieval evaluation: unchanged from the labels v1.3 baseline (Recall@5 0.961, MRR 0.987);
    recorded in `EVALUATION.md`.
  - SECURITY.md release checklist: request bodies forbid extra fields after T-017 (three did
    not); no exception text in responses (tests); untrusted text only through the delimiting
    helpers and models without tools (unchanged); limits in place, including the run store (one
    career run at a time, 20 finished runs kept for 15 minutes); model text rendered as text (no
    `dangerouslySetInnerHTML`) and links only through `safeExternalUrl`; `pip-audit`: no known
    vulnerabilities (28 pinned packages). Milestone 7 and 8 items not applicable yet.

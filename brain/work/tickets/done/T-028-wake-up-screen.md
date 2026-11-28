# T-028: an animated "waking up" screen for the API's cold start
Frontend feature found in Milestone 8 step 5 ([T-020](../in-progress/T-020-deploy.md)). The look is specified in
`../../../design/DESIGN.md`; the health check is described in `../../../engineering/ARCHITECTURE.md`.

- **Type:** feature
- **Status:** done
- **Opened:** 2026-11-28 · **Closed:** 2026-11-28
- **GitHub Issue:** none

## Summary
Render's free plan sleeps the API after 15 minutes without visitors; Render says waking takes 50
seconds or more. Today the first visitor after a quiet spell sees each screen's small "Checking the
server..." line, or a request that just hangs, with no sign that anything is happening.

## Decision
Owner decisions (2026-11-28):
- A full animated loading page, not a small banner.
- Text exactly "Waking up AI braincells..." with an elapsed-time counter (the owner rejected a
  longer explanatory sentence).

Design (lead): the shared health check (`lib/serverInfo.tsx`, one `GET /api/health` per page load)
gains a "waking" state when the server hasn't answered within about 2 seconds; it keeps retrying
with a per-attempt timeout until it answers, then the screen fades out. If the server still hasn't
woken after a few minutes, the screen says so and offers a retry instead of spinning forever. A
fast answer shows nothing. The look (animation, layout, themes, reduced motion) is drafted by
design-advisor in DESIGN.md and approved by the owner before it is built.

## Changes
- Branch: `feat/t-020-deploy` (part of the Milestone 8 PR)
- PR:
- Files touched: `frontend/lib/serverInfo.tsx` (retries, `waking`, `useServerWake`),
  `frontend/components/WakeScreen.tsx` (new), `frontend/app/layout.tsx` (wraps the site; skip
  link inside), `frontend/app/globals.css` (`--animate-fire`); tests `lib/serverInfo.test.tsx`,
  `components/WakeScreen.test.tsx` (new); DESIGN.md section and the mock-up
  `brain/design/mockups/T-028-wake-up-screen.html`; ARCHITECTURE, WALKTHROUGH.
- Commits (hash, message): `255e885` feat: show a waking-up screen while the API wakes from
  sleep (T-028); `c72686c` docs: record the waking-up screen design, mock-up and decisions
  (T-028); and the closing `docs: close the waking-up screen ticket (T-028)`.

## Verification
- Design: design-advisor drafted it in DESIGN.md and an HTML mock-up (six frames); the owner chose
  the wordmark and approved everything as shown (2026-11-28).
- Cold start measured on the deployed site after over 2 hours idle: 43.0 s for the first
  `/api/health`, 0.3 s after. So the per-attempt timeout is 60 s (Render holds the first request
  until the host is up; under Vercel's 120 s), the limit 3 minutes.
- Frontend: lint, typecheck, 330 tests, build. Tests run the real provider on fake timers
  (including animation frames): a fast answer never shows the cover; waking after 2 s; a hanging
  attempt cut off and retried; the limit holds even for an attempt started just before it;
  stopped state with the issues link and focus; "Try again" restarts at once, keeps focus,
  restarts the announcements and can succeed; the cover fades out after the 800 ms minimum.
- In the browser against a slow stand-in API: the screen as in the mock-up, timer counting, no
  console errors.
- code-reviewer: no stuck state, race or hydration issue; `inert` on the `display: contents`
  wrapper works. Taken: focus and announcements after "Try again"; the skip link moved inside the
  inert wrapper; attempt and pause capped at the time left (the limit could stretch to ~4 min);
  the retry flag reset after use; the context value memoised. Not taken: reading status through a
  ref in the cover's effect (safe while the two updates are batched); clearing "Server ready".
- Found by a test: the issues link's accessible name lacked a space ("know(opens"); fixed.
- Stopped state seen in the real app (slow stand-in API): hollow cells, the copy, the issues link,
  "Try again", focus on the headline. CI green on `c72686c`; the new bundle is live on Vercel.
- Known cosmetic limit: the stopped timer shows 2:59 rather than 3:00 (the last tick lands just
  before the cut-off).

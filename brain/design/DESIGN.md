# DESIGN.md: GradPath AI
How the Milestone 6 Next.js UI looks and behaves: tokens, components, screens, honesty states.
What the product does is in `../product/REQUIREMENTS.md`; stack, API and data flow in
`../engineering/ARCHITECTURE.md`; the XSS and output-handling rules this file turns into design rules
are in `../engineering/SECURITY.md`; the work itself is ticket `../work/tickets/T-011-frontend.md`.
Status: **approved by the owner 2026-11-19** after the visual mock-up. Owner decisions 2026-11-19: partial answers option A
(backend `partial` status), long runs option B (run id + polling), dark mode first with a toggle. Remaining "Owner decision needed" items carry a recommendation.
"Demo and live modes" (Milestone 7) was approved by the owner on 2026-11-20 (decisions 7-12).

**Identity: an annotated study notebook.** Warm paper, near-black ink, one teal ink for links. Every
claim sits next to its evidence, the way a margin note sits next to a quote: the posting's own words,
the source title and its hostname. Format follows the common
DESIGN.md section convention (Google Stitch); no palette or look is adapted from any catalogue or
real brand.

Tokens live in `app/globals.css` under `@import "tailwindcss";` in a plain `@theme { ... }` block (not
`@theme inline`, so utilities read the CSS variables). **Dark mode is the default** (owner, 2026-11-19):
the dark values sit on `:root`, and `:root[data-theme="light"]` overrides the same variables with the
light values, so components never need `dark:` prefixes. A header toggle switches the theme (see
Components, Theme toggle).
Contrast ratios below are WCAG 2.x, computed for each text/background pair (light / dark).

## Colors

### Brand / Accent
- **Ink** (`#1C1B19` / dark `#ECE8E1`) `--color-ink`: body text, headings, primary button fill.
- **Teal** (`#0F5C66` / dark `#6FC3CB`) `--color-link`: links (always underlined), the info tone.
  7.2:1 on paper, 7.7:1 on surface / dark 9.0:1, 8.2:1.
- **Focus** (`#0F5C66` / dark `#6FC3CB`) `--color-focus`: the focus outline only. 7.2:1 / 9.0:1
  against paper, well above the 3:1 needed.

### Surface
- **Paper** (`#FAF8F4` / dark `#161513`) `--color-paper`: page background.
- **Surface** (`#FFFFFF` / dark `#1F1E1B`) `--color-surface`: cards, forms, result panels.
- **Sunken** (`#F2EFE9` / dark `#121110`) `--color-sunken`: posting quotes, the composer's
  attachment tray, code-like ids.

### Text
- **Ink** (see above): ink on paper 16.2:1, ink on surface 17.2:1 / dark 14.9:1, 13.7:1. Primary
  button text (paper on ink) 16.2:1 / 14.9:1.
- **Ink muted** (`#5C5A55` / dark `#A8A39A`) `--color-ink-muted`: help text, meta lines, section
  labels in citations. Paper 6.5:1, surface 6.9:1, sunken 6.0:1 / dark 7.3:1, 6.7:1, 7.5:1.

### Borders
- **Line** (`#8A857B` / dark `#77726A`) `--color-line`: input, button and checkbox borders (meaning-
  bearing, 3:1 needed). Paper 3.5:1, surface 3.7:1 / dark 3.8:1, 3.5:1.
- **Rule** (`#E2DDD3` / dark `#2E2C28`) `--color-rule`: decorative dividers, card outlines, the
  roadmap rail. Never the only cue for anything.

### Semantic
Each tone is a text colour plus a tinted background (`--color-<tone>` and `--color-<tone>-bg`); the
text colour also draws the badge border and the banner's left bar. Colour is never the only cue:
every status has its own icon and words (see Components, Status badge).
- **Positive** (`#1E5631` on `#E6F2E9` / dark `#8FD19E` on `#1B2E21`): evidenced, covered, checked.
  7.5:1 / 8.1:1.
- **Caution** (`#6B4A00` on `#FBF1D9` / dark `#E8C36A` on `#33280F`): partly evidenced, weak
  evidence, partial, open issues, low confidence. 7.2:1 / 8.6:1.
- **Gap** (`#7A3410` on `#F7EAE1` / dark `#F0A77E` on `#3A2116`): no evidence yet: not yet
  evidenced, not covered, not covered by the knowledge base. 7.7:1 / 7.5:1.
- **Stopped** (`#8C1D18` on `#FBE9E7` / dark `#F4A3A0` on `#3D1A19`): fallback, blocking issues,
  errors, field validation. 7.8:1 / 7.8:1. On plain surface: 9.1:1 / 8.4:1.
- **Neutral** (`#5C5A55` on `#EFECE6` / dark `#A8A39A` on `#2A2925`): eligibility (not assessed),
  unsupported, minor issues, "Preferred". 5.8:1 / 5.8:1.
- **Info** (`#0F5C66` on `#E4F0F1` / dark `#6FC3CB` on `#142C2F`): needs input, busy, profile
  storage notice. 6.6:1 / 7.2:1.

## Typography
One family: **Atkinson Hyperlegible Next** (free, Google Fonts, designed for legibility) through
`next/font/google`, weights 400 and 600, exposed as `--font-atkinson`; `--font-sans:
var(--font-atkinson), ui-sans-serif, system-ui, sans-serif`. No monospace font: numbers that change
(timer, counters) use `tabular-nums`. Sentence case everywhere; no all-caps labels. Each token sets
`--text-<name>`, `--text-<name>--line-height`, `--text-<name>--letter-spacing` and
`--text-<name>--font-weight`, used as `text-<name>`.
- **display**: 28px (1.75rem) · 600 · 1.2 · -0.01em `--text-display`: the page `h1`, one per page.
- **title**: 22px (1.375rem) · 600 · 1.3 · 0 `--text-title`: `h2` (result heading, plan sections).
- **heading**: 18px (1.125rem) · 600 · 1.4 · 0 `--text-heading`: `h3` (roadmap step topic,
  requirement groups, interview question).
- **body**: 16px (1rem) · 400 · 1.6 · 0 `--text-body`: answers, reasoning, form inputs (16px also
  stops iOS zoom on focus).
- **label**: 14px (0.875rem) · 600 · 1.4 · 0 `--text-label`: field labels, buttons, badges, skill
  names in dense rows.
- **small**: 14px (0.875rem) · 400 · 1.5 · 0 `--text-small`: citation lists, help text, quotes.
- **meta**: 13px (0.8125rem) · 400 · 1.4 · 0.01em `--text-meta`: route line, hostnames, counters,
  "sources as of". Never smaller than 13px.

Reading measure: answer and reasoning text `max-w-reading` (`--container-reading: 40rem`, about 68
characters).

## Layout

### Spacing
Tailwind's default `--spacing: 0.25rem`; use these steps only.
- **1** (4px): icon to text inside badges (`gap-1`).
- **2** (8px): inside badges and chips, label to input.
- **3** (12px): rows in a citation list, help text to error text.
- **4** (16px): card padding and page gutter at 375px (`p-4`, `px-4`).
- **6** (24px): card padding from `sm`, items within a section, gutter from `sm`.
- **8** (32px): between form groups, gutter from `lg`.
- **12** (48px): between page sections and plan sections.

### Radius
- **sm** (3px) `--radius-sm`: badges, citation chips.
- **md** (6px) `--radius-md`: buttons, inputs, cards, banners, dialog.
- **full** `--radius-full`: the stage-progress dots only.
No pill-shaped buttons, no large rounded cards.

### Grid and breakpoints
- Shell: `mx-auto w-full max-w-5xl px-4 sm:px-6 lg:px-8`. Header `h-14`, footer below content.
- Single column by default; form pages (Assistant, Job analysis, Profile) use `max-w-3xl`.
- Plan result from `lg` (1024px): `lg:grid lg:grid-cols-[12rem_minmax(0,1fr)] lg:gap-12`; the left
  column is a sticky "On this page" nav (`lg:sticky lg:top-20 self-start`). Below `lg` that nav is a
  wrapping row of in-page links under the status banner.
- Breakpoints: Tailwind defaults `sm` 640, `md` 768, `lg` 1024. Base design is 375px: nothing scrolls
  sideways, badges wrap under the skill name, buttons go full width (`w-full sm:w-auto`).
- Touch targets: buttons `h-11 sm:h-10`, links in lists get `py-1` so targets reach 24px minimum.

## Components
Plain React + Tailwind and native HTML elements (see "Component library" under Guidelines). All
model and retrieved text goes in as React children (see Security rules).

- **Primary button**: `bg-ink text-paper rounded-md px-4 text-label hover:bg-ink/90
  disabled:opacity-50`. One per form ("Ask", "Analyse posting", "Build plan", "Save profile").
- **Secondary button**: `bg-surface text-ink border border-line rounded-md`. "Load sample", "Stop
  waiting", "Try again".
- **Text button**: `text-link underline underline-offset-4`. Example prompts, "Edit inputs".
- **Destructive button**: secondary style with `text-stopped border-stopped`. "Clear profile" only,
  confirmed in a native `<dialog>`.
- **Field**: label (`text-label`) above, input `bg-surface border border-line rounded-md px-3 py-2
  text-body`, help (`text-meta text-ink-muted`) below. Error: `aria-invalid`, border and message in
  `stopped`, octagon icon, linked by `aria-describedby`. Long inputs show a counter "1,240 / 20,000"
  (`text-meta tabular-nums`), caution from 90%, stopped when over (submit then shows the error).
- **Status badge**: `inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-label`,
  tone text + tone bg + tone border, icon 14px `aria-hidden`, the words carry the meaning. One glyph
  means one thing everywhere: check = evidenced, half-filled circle = partial, hollow circle = no
  evidence yet, dash = not assessed, triangle = open issues, octagon = stopped/blocking, info circle
  = needs something, question circle = low confidence.

  | Field | Value | Tone | Icon | Words on screen |
  |---|---|---|---|---|
  | workflow status | complete | positive | check | Checked |
  | | complete_with_limitations | caution | triangle | Finished with open issues |
  | | partial | caution | half circle | Partial: not fully checked |
  | | fallback | stopped | octagon | Stopped early: partial result |
  | answer status | answered | positive | check | From the knowledge base |
  | | partial (decision 1, T-012) | caution | half circle | Not fully covered (the h2 reads "Partial answer") |
  | | insufficient_evidence | gap | hollow circle | Not covered by the knowledge base |
  | gap status | demonstrated | positive | check | Demonstrated |
  | | partially_evidenced | caution | half circle | Partly evidenced |
  | | not_yet_evidenced | gap | hollow circle | Not yet evidenced |
  | | not_applicable | neutral | dash | Eligibility (not assessed) |
  | coverage | covered / weak_evidence / not_covered / not_applicable | positive / caution / gap / neutral | check / half / hollow / dash | Covered / Weak evidence / Not covered / Eligibility (not assessed) |
  | importance | required / preferred | ink outline / neutral | none | Required / Preferred |
  | issue severity | blocking / minor | stopped / neutral | octagon / info | Blocking / Minor |
  | posting quote | quote_verified false | caution | triangle | Quote not found in posting |

- **Confidence**: text, not a meter: "High confidence", "Medium confidence" in `text-meta
  text-ink-muted`; "Low confidence" in `text-caution` with the question-circle icon.
- **Effort estimate**: always "~6 h (estimate)" (`text-meta`, `tabular-nums`, round to the nearest
  hour, "<1 h" under 1). Plan total: "~34 h in total (estimate)". Never a progress bar.
- **Citation list** (under answers, study notes, fallback sources): `<ol>` with `space-y-3`. Each
  item: title as a link (`text-small text-link underline`), then `section` and the hostname in
  `text-meta text-ink-muted` ("Indexes · postgresql.org"), external-link icon plus visually hidden
  "(opens in new tab)". Duplicate `source_url` + `section` pairs shown once. Score hidden; shown
  only inside the "How this was answered" disclosure as "match 0.62".
- **Citation chip** (roadmap resources, compact): `rounded-sm border border-rule bg-sunken px-2
  py-0.5 text-small`, title truncated at 40 characters with the full title in the link's accessible
  name and `title`; hostname after it. Wraps; never a horizontal scroller.
- **Posting quote**: `border-l-2 border-line bg-sunken pl-3 py-2 text-small`, prefixed "Posting:".
  The posting's own words, shown before any interpretation.
- **Status banner** (result-level): `rounded-md border-l-4 border-<tone> bg-<tone>-bg p-4 sm:p-6`,
  icon 20px, `text-heading` headline, body `text-body`, then a "What you can do" line. Not
  dismissible. Used for the honesty states below; `complete` gets no banner.
- **Route line**: `text-meta text-ink-muted` under every assistant result: "Knowledge-base answer ·
  chosen by rules" or "Preparation workflow · chosen by the model classifier" (`default`: "chosen
  by default"). A `<details>` "How this was answered" holds the `reason` (plain text) and scores.
- **Stage list** (long runs): `<ol>`, each row a 10px dot plus label. States: done (ink filled dot +
  check, "done" in sr text), running (teal ring, `motion-safe:animate-pulse`), waiting (hollow
  `line` dot), not reached (dash). Option A shows no states at all (see Long runs).
- **Theme toggle**: header right, secondary button style (`h-11 sm:h-9`), moon or sun icon plus the
  words "Dark mode", `aria-pressed` true when dark. Dark first; the choice is saved in localStorage
  (`gradpath-theme`) and applied before first paint by a small static script, `public/theme-init.js`, loaded from
  `app/layout.tsx` (a file, not inline, so a later Content-Security-Policy stays strict), so
  there is no light flash. No system-setting detection.
- **Disclosure**: native `<details>`/`<summary>`, summary in `text-label text-link` with a chevron
  that rotates 90 degrees (`motion-safe:transition-transform duration-150`).

## Elevation
Flat, like paper. Depth comes from surface colour and rules, not shadows.
- **Level 0**: `bg-paper`, the page.
- **Level 1**: `bg-surface border border-rule rounded-md`: cards, forms, result panels. No shadow.
- **Level 2**: sticky header `bg-paper border-b border-rule` (solid, no blur or transparency).
- **Dialog**: native `<dialog>`, `bg-surface border border-line`, the only shadow in the app
  `shadow-[0_8px_24px_rgb(0_0_0/0.12)]`, backdrop `bg-ink/40`.

## Guidelines

### Principles
1. **Evidence first.** Show the posting quote and the source next to every claim; interpretation
   comes after.
2. **Mark partial results clearly.** A complete result gets a small badge; anything partial gets
   a banner, a different heading and the reason.
3. **Say what happened.** Which path ran, which stages finished, what was not checked.
4. **Estimates look like estimates.** "~", "(estimate)", no bars or percentages for things we cannot
   measure.
5. **Calm.** One accent, no decoration, no motion that isn't feedback.

### Honesty states (the most important part)
- **Result headings change with status** (the `h2` itself, not only a badge): "Preparation plan";
  "Preparation plan, with open issues"; "Partial preparation plan"; "Partial result: the run stopped
  early". The live region announces the same words.
- **complete**: positive "Checked" badge next to the heading and one meta line "The final check
  passed with no blocking issues." Minor `unresolved_issues` sit in a `<details>` "N minor notes".
- **complete_with_limitations**: caution banner. Headline "Finished with open issues". Body: "The plan
  was revised {revisions_used} times and the final check still found problems. Read these before
  relying on the plan." Blocking issues listed inline in the banner (not hidden), minor ones in a
  disclosure.
- **partial**: caution banner, half-circle icon. Headline "Partial plan: not fully checked". Body:
  "A stage failed or the final check did not run, so parts of this plan are missing or unreviewed."
  Every empty section shows an inline gap-tone row "Not produced in this run" instead of vanishing.
  `errors[]` go in a disclosure "Technical details" as plain text.
- **fallback**: stopped banner, octagon. Headline "Stopped early: partial result". Body:
  `fallback.message` (fixed server text). Then two short lists side by side from `sm` (stacked below):
  "Finished" (check) from `completed_stages` and "Not finished" (dash) from `not_completed`, using
  the stage labels below. Then a section "What still helps": `fallback.answer` as an answer card and
  `study_sources` as one citation list per skill. Gap, roadmap and question sections render only if
  they have content; never an empty "Your plan".
- **insufficient_evidence**: gap-tone panel. Headline "Not covered by the knowledge base". Body:
  "GradPath answers only from its curated sources, and none of them answer this well enough. It did
  not guess." Then `note` if present. If citations came back: "Closest sources found (they do not
  answer the question)". Then two text-button suggestions: narrow the question; paste a job posting.
- **Partial answer**: h2 "Partial answer", caution badge "Not fully covered", above the text and a line "Not covered: {what
  the sources did not cover}" (decision 1). `note` (downgrade reason) always shows as a caution line
  above the answer.
- **Stage labels**: analyze_job "Read the job posting", analyze_profile "Read your profile",
  retrieve_knowledge "Search the knowledge base", analyze_gaps "Compare requirements with your
  profile", plan_roadmap "Plan the roadmap", interview_questions "Write interview questions",
  evaluate "Check the plan", revise "Revise the plan", finalize "Assemble the result". Unknown names
  shown de-snake-cased.

### Long runs (80-300 s)
Progress view replaces the form's submit area; inputs stay visible, read-only.
```
+--------------------------------------------------------------+
| Preparing your plan                              1:42        |
| Usually 80-150 s. It stops by itself at 5:00 and returns     |
| what it finished.                                            |
|                                                              |
|  (x) Read the job posting                                    |
|  (x) Read your profile                                       |
|  (o) Search the knowledge base        <- running             |
|  ( ) Compare requirements with your profile                  |
|  ( ) Plan the roadmap  ( ) Write interview questions         |
|  ( ) Check the plan                                          |
|                                                              |
|  [ Stop waiting ]                                            |
+--------------------------------------------------------------+
```
- Timer `text-title tabular-nums`, not in a live region. No percentage bar, no spinner.
- From 150 s a meta line: "Taking longer than usual." Past 320 s with no reply: error state "No reply
  after 5 minutes. The server may still be finishing; try again in a few minutes."
- Live region (polite) announces stage changes (option B) or "Still working, 2 minutes" each 60 s
  (option A), and the final result heading.
- **Busy (503)**: info panel, not an error: "Another preparation run is in progress. Only one runs at
  a time on this server. Try again in a few minutes." One "Try again" button; no automatic retries.
- Recordings skip the progress view; see "Demo and live modes".

### Screens
Header on every page: wordmark "GradPath" (`text-label`, ink, no logo), nav "Ask", "Analyse a job",
"Plan", "Profile" (+ "Search sources" from Milestone 7) (current page `aria-current="page"`,
underlined), the mode indicator in the right-side slot (see "Demo and live modes"). At 375px the nav
wraps to a second row; no hamburger menu.
Footer: "Sources as of {date} · Preparation support only, not a hiring prediction · Answers can be
wrong: check the sources."

**1. Assistant (`/`)**, h1 "Ask GradPath"
```
Ask GradPath
Ask a backend preparation question, or paste a job posting and
a profile to get a preparation plan.
+--------------------------------------------------------------+
| [ message textarea, 4 rows                                 ] |
| 312 / 2,000                                                  |
| +-- sunken tray ------------------------------------------+  |
| | Job posting: pasted, 2,340 chars  [Edit] [Remove]       |  |
| | Profile: Sample new grad (fictional)  [Change]          |  |
| +---------------------------------------------------------+  |
|                                                 [  Ask  ]    |
+--------------------------------------------------------------+
Knowledge-base answer · chosen by rules   > How this was answered
[ result: answer card | plan result | state panel ]
```
- Empty: three example questions as text buttons that fill the box (do not submit), plus one line on
  the two paths. No hero, no illustration.
- "Paste a job posting" opens an inline textarea in the tray (pasted text only: no URLs, owner
  decision 2026-11-19, because fetching visitor URLs is an SSRF risk and job sites block scripts); profile picks the saved profile or a
  sample.
- Loading: "Searching the knowledge base and writing an answer... 0:07" for answers; the full
  progress view if the route is the workflow (decision 2, option B can report the route first).
- `answered` / `prepared`: answer card or plan result (screen 3 component), route line above it.
- `needs_input`: info panel with `message`, plus buttons that focus the missing control ("Paste a
  job posting", "Choose a profile").
- `unsupported`: neutral panel with `message` and "GradPath answers backend new-grad preparation
  questions and builds plans from a job posting." plus the example prompts.
- Errors: see "States for every screen".

**Answer card**
```
[check From the knowledge base]
Answer text, plain, whitespace-pre-line, max 68 characters wide ...
Sources
 1. PostgreSQL docs: Indexes  ->     Introduction · postgresql.org
 2. Use The Index, Luke       ->     Anatomy of an index · use-the-index-luke.com
Can be wrong: check the sources.
```

**2. Job analysis (`/job`)**, h1 "Analyse a job posting"
```
[ posting textarea, 12 rows ]        1,240 / 20,000   [Use sample posting]
                                                       [ Analyse posting ]
------------------------------------------------------------------------
Backend Software Engineer, New Grad      Entry level
12 requirements: 5 covered, 3 weak evidence, 2 not covered, 2 eligibility
> Responsibilities (6)
Required (7)                                             <- h3
 SQL and relational databases              [check Covered]
 | Posting: "Experience with SQL and relational databases"
 Study note text, plain ...
 Sources: [chip] [chip]
 ...
Preferred (3)
Eligibility, not assessed (2)
[ Build a preparation plan from this posting ]  -> /plan, posting carried over
```
- Rows are an `<ul>` of self-labelled items, not a table: each row carries its own words, so it reads
  the same at 375px and in a screen reader. Grouped by importance; eligibility last.
- Empty: textarea, "Use sample posting" (the repo's fictional sample), one line on what it returns.
- Loading: status line + timer, "Reading the posting and searching the knowledge base".

**3. Preparation plan (`/plan`)**, h1 "Preparation plan"
```
Inputs: Backend Software Engineer posting · Profile: Sample new grad   [Edit inputs]
+-- stopped banner --------------------------------------------------+
| [octagon] Stopped early: partial result                            |
| Partial result: the workflow ran past its time limit ...           |
| Finished: (x) Read the job posting (x) Read your profile ...       |
| Not finished: - Plan the roadmap - Write interview questions ...   |
+--------------------------------------------------------------------+
On this page       | Partial result: the run stopped early     <- h2
 Skills gap        | Skills gap                               <- h2
 Roadmap           |  Not yet evidenced (4) / Partly (2) / Demonstrated (3) / Eligibility
 Interview qs      |  REST API design  [Required] [hollow Not yet evidenced]
 What still helps  |  Reasoning text ...            Medium confidence
                   | Roadmap   ~34 h in total (estimate)
                   |  | Step 1 of 6 . After step -          ~6 h (estimate)
                   |  | SQL indexing                                  <- h3
                   |  | Why it matters / Objective / Exercise / Done when
                   |  | Resources: [chip] [chip]
                   | Interview questions
                   |  1. How would you ... > What a good answer shows
                   | Correct an assumption  (3 of 10)  [ Re-run with corrections ]
```
- Sections with in-page links, not tabs (decision 4): everything is visible, printable and scrolls
  for a reviewer.
- Gaps grouped by status, gaps to address first. Interview questions show "For: {skill}" from the
  matching gap.
- Roadmap: `<ol>` on a left rail (`border-l border-rule pl-6`), step number in a small square on the
  rail; `depends_on` as "After step 2".
- Corrections: textarea (1-500 chars), list of added corrections with Remove, counter "3 of 10",
  helper "A re-run takes another 1.5-5 minutes."
- Empty: two prerequisite rows, "Job posting: missing [Add]" and "Profile: missing [Choose]",
  then "Build plan" (disabled until both are set, with the reason as help text).

**4. Profile (`/profile`)**, h1 "Your profile"
```
+-- info panel ----------------------------------------------------+
| Stored only in this browser. It is sent to the GradPath server   |
| only when you build a plan. Leave out contact details.           |
+------------------------------------------------------------------+
[ Load sample profile ]  [ Clear profile ]          6,240 / 12,000
Education       [ input ]
Skills          [ one per line textarea ]     (up to 50)
Coursework      [ one per line textarea ]     (up to 30)
Projects (2 of 6)    name / description / technologies (comma-separated)  [Remove]
                     [ + Add project ]
Experience (1 of 6)  role / organisation (optional) / description          [Remove]
Weekly study hours [  ]   Timeline in weeks [  ]   (both optional)
                                                     [ Save profile ]
```
- **Import from resume** (owner decision 2026-11-19): a disclosure above the form, "Fill from a
  resume". Paste resume text (up to 15,000 chars), "Extract profile"; the fields fill in for review
  and nothing is saved until "Save profile". Info line: "Contact details are dropped. The resume
  text is sent to the model once and not stored." The Ask tray's profile row offers "Import from
  resume" too. A PDF upload comes with Milestone 7's upload work.
- No name field: `name`, `profile_id` and `note` are not needed for a plan, so the form omits them
  (less personal data). A loaded sample shows a neutral badge "Sample (fictional)".
- Empty: "No profile saved in this browser." with "Load sample profile" and "Start from blank".
- Saved: meta line "Saved in this browser, {time}". Clear asks for confirmation.

### States for every screen
| State | Treatment |
|---|---|
| Empty | One sentence of purpose plus a sample action; no illustrations |
| Loading | Status line + elapsed timer; long runs use the progress view |
| 422 validation | Error summary at the top of the form (`role="alert"`, links to fields) and per-field messages; never raw Pydantic text |
| 503 busy | Info panel with fixed copy and "Try again" |
| Other error / network | Stopped panel: "Something went wrong on the server. Nothing was saved. Try again." No exception text |
| needs_input / unsupported | Assistant only; see screen 1 |
| 401 / 403 / 429 from mode rules | See "Demo and live modes", States |

### Demo and live modes (Milestone 7, T-018): approved 2026-11-20
The server runs in one mode, read once per page load from `GET /api/health` `app_mode` and shared by
the header, footer and screens (one health request, not one per component: main session decides
how). The visitor never picks the server's mode; live mode only adds the option to bring a key.
Until health answers, each screen's input area shows the meta line "Checking the server..." (no
spinner, no form flash); if it fails, the network stopped panel. An unknown `app_mode` is treated as
`demo` (fail closed).

| | local | demo | live, no key yet | live, key set |
|---|---|---|---|---|
| Header indicator | "Local mode" (`text-meta text-ink-muted`, no badge) | neutral badge, clock, "Demo: recorded examples" | neutral badge, info circle, "Live: no key yet" | info badge, key glyph, "Live: your key" |
| Ask / Job / Plan | forms as today | mode note + recordings, no form | mode note + form, submit area replaced by the live panel + recordings | form as today + recordings |
| Profile resume import | as today | replaced by a note | live panel inside the disclosure | as today |
| Search sources | on (no limit) | on, 2/min | on, 2/min | on, 2/min |

New glyphs (one meaning each): **clock** = recorded, never live; **key** = a visitor key is held in
this tab. Both 14px in badges, 16px in strips, `aria-hidden`.

**Header (decision 7).** The indicator sits in the reserved slot left of the theme toggle,
non-interactive (a badge, not a button). Below `sm` it moves to its own row after the nav
(`order-4 w-full sm:order-none sm:w-auto`) so row 1 stays wordmark + toggle at 375px.

**Mode note** (demo and live, every model screen): one `text-small text-ink-muted` paragraph under
the page intro, no banner (it is a fact about the site, not a result status). Copy:
- Demo, Ask: "This site runs in demo mode: no model runs here, so it can't answer a new question.
  Below are recorded runs of the real app on a sample posting and a fictional profile. To try your
  own question, [search the sources]: you get the matching passages, not a written answer."
- Demo, Job / Plan: "This site runs in demo mode, so it can't analyse a new posting. Below is a
  recorded run on the sample posting{, with the fictional sample profile}."
- Live: "Live mode: use the full app with your own Anthropic API key and the passcode from the site
  owner. Without them you can still browse the recorded examples and [search the sources]."

#### Recorded examples (decision 8)
Per screen: Ask lists the `ask` recordings, Job the `job` one, Plan the `plan` one, filtered from one
`GET /api/demo`. In demo they replace the form; in live and local they sit below the form and result
as an `h2` section "Recorded examples" (local shows them too: the owner can check what visitors see).
```
Recorded examples                                              <- h2
 +--------------------------------------------------------------+
 | How do multicolumn indexes work in PostgreSQL?   (title)     |
 | A cited answer from the PostgreSQL docs.          (summary)  |
 | Recorded 20 Nov 2026                              (meta)     |
 +--------------------------------------------------------------+
 | ... one row per recording, stacked, never a grid             |
------------------------------------------------------------------
[clock] Recorded example, run on 20 Nov 2026. Not generated now.
Asked: "How do multicolumn indexes work in PostgreSQL?"
> Job posting: sample (2,340 chars)    Profile: Sample new grad (fictional)
Knowledge-base answer · chosen by rules   > How this was answered
[ the same answer card / panel / PlanResult / AnalysisResult as a live run ]
```
- Picker: `<ul>` of `<button type="button" aria-pressed>` rows, `w-full text-left rounded-md border
  border-rule bg-surface p-3`, hover `border-line`; selected `border-ink` plus a visible "Showing"
  meta word (not colour alone). Title `text-label`, summary `text-small text-ink-muted`, date
  `text-meta`. Ask: nothing preselected. Job and Plan (one recording each): no picker, the recording
  shows at once, without moving focus.
- **Recording strip** above the result: `flex items-start gap-2 rounded-md border border-rule
  bg-sunken px-3 py-2 text-small`, clock 16px, "Recorded example, run on {d MMM yyyy}. Not generated
  now." (ink on sunken about 15:1 both themes). The result `h2` keeps its status wording and gets
  `aria-describedby` = the strip, so focus reads "Answer, Recorded example, run on ...". Live region:
  "Recorded example: {heading}". Never a "Live" word or a timer near a recording.
- **Inputs block** (read-only text, never a disabled form): "Asked:" as a posting-quote block; the
  posting in a `<details>` "Job posting: sample ({n} chars)" (plain text, `whitespace-pre-line`);
  "Profile: Sample new grad (fictional)" with a link to /profile's "Load sample profile"; Plan adds
  "Corrections: none" or the list.
- Results reuse the live components unchanged, except: `needs_input` hides its action buttons and
  says "In the full app these buttons add the missing input."; Job's "Build a preparation plan"
  becomes the link "See the recorded plan for this posting" -> /plan; Plan has no Corrections
  section in demo ("Re-running with corrections needs live mode."). A workflow recording renders
  PlanResult directly (no progress view).
- Selecting a row in live/local replaces whatever is in the result slot; the strip is the only
  difference between a recording and a live result, so it must never be hidden.

#### Source search (decision 9)
Own page `/search`, nav item "Search sources" (fifth link; still wraps, no menu), in every mode.
h1 "Search the sources". Intro: "Finds passages in GradPath's curated sources that match your
question. No model runs: you get the passages, not a written answer."
```
[ Your question (input, 1 line, 16px)                    ] [ Search ]
  3-500 characters · 2 searches a minute          42 / 500
------------------------------------------------------------------
Passages for "What is a multicolumn index?"           <- h2, focused
4 passages · sources only, no written answer
If you asked this in the full app: Knowledge-base answer · chosen by rules
 1. Multicolumn Indexes  ->     Indexes · postgresql.org      <- citation link
    | An index can be defined on more than one column ...      <- excerpt
 2. ...
> How these were ranked            (match 0.64, 0.61, ... in order)
```
- Field: `<input type="search">` in a `<form role="search">`, `max-w-3xl`; local length check like
  the other forms. "Search" is the primary button.
- Hits: `<ol space-y-6>`; each item a citation (existing Citation list rules: http/https only, new
  tab, hostname) then the excerpt as **plain text**: `mt-2 border-l-2 border-line bg-sunken py-2 pl-3
  text-small whitespace-pre-wrap break-words` (pre-wrap keeps code indentation; not ModelText:
  retrieved text gets no markdown). Scores only in the closing disclosure.
- Route preview: one `text-meta text-ink-muted` line, prefixed "If you asked this in the full app:"
  then the RouteLine wording from `route_preview` (`needs_input` adds "· needs {a job posting / a
  profile}"; `unsupported`: "Not supported yet"). `route_preview` null: the server's `route_note` as
  is. Neither: no line.
- `insufficient: true`: the gap panel "Not covered by the knowledge base", body "None of GradPath's
  sources match this well enough.", then hits (if any) under "Closest passages (they do not answer
  the question)". Zero hits and not insufficient cannot be trusted as "covered": show the same panel.
- Rate limited (429): info panel "Two searches a minute", body = server text, then "You can search
  again in 0:38" (`tabular-nums`, from `Retry-After`, ticking, not announced); Search disabled
  until 0, then the live region says "You can search again." `Retry-After` over 120 s: "Try again
  after 14:30" (local clock time), no ticker. Previous results stay on screen.
- Off (503): neutral panel, server text ("Source search is off on this server..."), input and button
  disabled. Loading: "Searching the sources..." meta line, button disabled, no timer (it is fast).
  Empty: intro plus the three example questions from Ask as text buttons that fill the field.

#### Live mode panel (decisions 10, 11)
Inline where it is needed: on Ask, Job and Plan it replaces the submit row; on Profile it sits
inside "Fill from a resume". One shared in-memory state, so entering it once unlocks every screen
until reload. Not a `<form>` (no submit event, fewer password-manager prompts): a `<div
role="group" aria-labelledby="live-title">`; Enter in either field runs "Use live mode".
```
+-- bg-surface border border-rule rounded-md p-4 sm:p-6 ----------+
| Use live mode                                       <- h2/h3      |
| Runs the real app with your own Anthropic API key. Requests use   |
| your Anthropic credit; a plan makes many more calls than an answer.|
| Passcode                                                           |
| [ ••••••••••••••••••              ] [ Show ]                       |
| From the site owner.                                               |
| Anthropic API key                                                  |
| [ sk-ant-•••••••••••••••          ] [ Show ]                       |
| Sent to the GradPath server with each request, which passes it to  |
| Anthropic for that request only. Never stored, logged or shown     |
| back. Kept in this tab's memory: reloading or closing the page     |
| clears it.                                                         |
| [ Use live mode ]                       No key? Browse the examples|
+--------------------------------------------------------------------+
```
- Inputs: `type="password"`, `autoComplete="off"`, `spellCheck={false}` (stops browser cloud spell
  check when shown as text), `autoCapitalize="none"`, `autoCorrect="off"`, no paste blocking, no
  `maxLength` surprise; values trimmed. Input `flex-1`, Show button secondary `h-11 sm:h-10`
  beside it; its text and accessible name switch "Show passcode" / "Hide passcode"; both fields
  hide again on "Use live mode". Help text linked by `aria-describedby`.
- Local check only: key must start with `sk-ant-` ("This doesn't look like an Anthropic API key:
  they start with sk-ant-."); passcode non-empty ("Enter the passcode."). No length hints.
- "Use live mode" calls `POST /api/live/check` (decision 12): the server checks the passcode and
  tests the key with Anthropic (a free call), then returns a session token. Errors show in the panel
  at once (States below). The button shows "Checking..." while it waits.
- **Key set**: the panel collapses to an info strip at the top of the form (`rounded-md border-l-4
  border-info bg-info-bg p-3 text-small`, key glyph): "Live mode on. Your key is in this tab's memory
  only and clears on reload; the passcode is remembered for this tab for up to 12 hours." + text
  button "Clear key and passcode". Focus moves to the strip
  (`tabindex="-1"`); live region "Live mode on". Clear: one click, no dialog (re-entry is cheap),
  wipes both values from state, panel returns, focus to its heading, live region "Key cleared".
- **Passcode after a reload (decision 11)**: the tab keeps only the session token (sessionStorage,
  never the passcode). While it is valid, the panel shows only the key field with "Passcode
  remembered for this tab." and a "Use a different passcode" text button; an expired or refused
  token clears itself and the passcode field returns. Clear removes the token too.
- **After a reload**: if Plan has a stored run id (`usePlanRun` persist) and no key, the panel's
  first line reads "A plan run from before the reload may still be on the server. Enter the same key
  again to see it." A different key gets the run's 404: "That run belongs to another key or has
  expired."

#### States (new elements)
| Trigger | Where | Treatment |
|---|---|---|
| 401 passcode (missing or wrong) | panel reopens | passcode field error "That passcode didn't work. Check it with the person who gave it to you."; focus the field; key kept |
| 429 passcode lockout | panel | stopped line inside the panel, server text ("Too many wrong passcodes. Try again in 15 minutes."); fields stay editable |
| 401 key missing / malformed | panel reopens | key field error, server text; focus the field |
| 401 key refused by Anthropic | panel reopens | key field error "Anthropic refused this API key. Check that it is active and has credit." (server text); key field emptied, passcode kept |
| 429 visitor's Anthropic limit or our per-IP model limits | result slot | info panel "Rate limit reached", server text, `Retry-After` as in Search; key stays set |
| 403 demo (mode changed under the page) | result slot | neutral panel with server text and a link to the recordings |
| `/api/demo` list fails | recordings section | stopped panel, network or server copy, "Try again" |
| list empty | recordings section | "No recorded examples on this server." (`text-small text-ink-muted`) |
| one recording fails / 404 | result slot | stopped panel "This recording could not be loaded." + "Try again"; picker stays |
| recording loading | result slot | "Loading the recording..." meta line, no timer |

In every panel-reopening case the visitor's typed question, posting and profile stay; nothing
re-sends by itself. The api client must tell the 401 and 429 cases apart (Known gaps).

#### Accessibility and mobile (additions)
- Mode indicator text is real text, read in order after the nav; no `aria-live` on it.
- Picker rows are buttons in an `<ul>` with `aria-pressed`; Tab moves between rows (8 at most, no
  roving tabindex needed). On pick, focus moves to the result `h2`, as for live results.
- Error fields use the existing Field error pattern (`aria-invalid`, octagon, `aria-describedby`).
- At 375px: panel buttons full width (`w-full sm:w-auto`), Show buttons stay beside the input;
  excerpts wrap (`break-words`), never scroll sideways; picker rows full width.

### Accessibility (WCAG 2.2 AA)
- Landmarks: `header` with `nav aria-label="Main"`, `main`, `footer`; plan nav `aria-label="Plan
  sections"`. A "Skip to main content" link first.
- One `h1` per page; `h2` result and sections; `h3` steps, groups, questions. No skipped levels.
- Focus: `focus-visible:outline-2 outline-offset-2 outline-focus` on every interactive element; never
  removed.
- One polite live region in the layout (`sr-only`) for stage changes and "Answer ready" / the result
  heading. The timer is not announced every second.
- When a result arrives, focus moves to the result `h2` (`tabindex="-1"`). Tab order then: route
  disclosure, in-page links, citations, disclosures, corrections. All disclosures are native
  `<details>`.
- Icons are `aria-hidden`; badges speak their words. Links state "(opens in new tab)".

### Security rules (design level, from SECURITY.md)
- All model, retrieved and user text renders as React text children with `whitespace-pre-line`. No
  `dangerouslySetInnerHTML`, never linkify URLs inside model text. Model text may use a small safe markdown subset (owner
  decision 2026-11-20), rendered by `components/ModelText.tsx` as fixed React elements: paragraphs,
  lists, `#` lines shown as bold text (never `<h*>`), fenced and inline code (`bg-sunken font-mono`,
  wrapping, no horizontal scroll) and bold. Markdown links show their text only; no raw HTML ever.
- The only links to outside are citation `source_url` values, rendered as links only if `new URL()`
  parses them with protocol `http:` or `https:`; otherwise the title shows as plain text. Always
  `target="_blank" rel="noopener noreferrer"`, with the hostname visible.
- No third-party trackers, analytics, embeds or runtime font CDNs (`next/font` self-hosts).
- Browser storage holds only the profile and the theme choice (localStorage) and the current posting
  and last result (sessionStorage). Never a key: the visitor's Anthropic key lives in React state
  only (no localStorage, sessionStorage, URL, cookie or log) and the copy says it clears on reload.
  The passcode follows decision 11. Neither value is ever rendered back except in its own field.

### Motion
- Hover and colour changes `transition-colors duration-150`. Disclosure chevron 150ms.
- The running stage dot pulses (`motion-safe:animate-pulse`). Nothing else moves: results appear
  without entrance animation; smooth scroll for in-page links only under `motion-safe`.
- `prefers-reduced-motion`: every animation is `motion-safe:` only, so it switches off as a whole.

### Component library (Owner decision needed)
shadcn/ui (MIT, copied into the repo, Radix primitives, works with v4 variables) would bring
accessible tabs, dialog, tooltip and accordion. This design needs none of them in a JS form: sections
replace tabs, `<details>` replaces accordion, native `<dialog>` covers the single confirm, and
tooltips are banned (information stays visible). Adding it costs Radix packages, `class-variance-
authority`, `clsx`, `tailwind-merge` and usually `lucide-react`, plus its recognisable default look
that we would have to restyle. **Recommendation: plain hand-written components and native elements;
revisit only if a later screen needs a combobox or menu.** Icons: about ten small inline SVGs
(main session decides between hand-drawn SVGs and a free icon package).

### Owner decisions needed
1. **Partial answers. Decided 2026-11-19: A.** (A) backend `partial` status: the answer model returns what the evidence does
   not cover, code sets `status: "partial"`; precise and testable, costs a schema, prompt and eval
   change and is one more model judgement to measure. (B) UI label from existing fields: no backend
   work, but nothing in `ChatAnswer` marks partiality, so it means matching phrases in the answer
   text (brittle) or showing only the general caveat. **Recommend A**; until it ships, show the
   caveat line under every answer.
2. **Long runs. Decided 2026-11-19: B.** (A) synchronous request, timer, expected range, static step list, "Stop waiting":
   no backend work, but the list cannot show real progress (it must not tick by time) and stopping
   only stops the browser waiting; the server keeps the run and the busy slot. (B) run id + status
   polling: real finished stages from `node_log`, a real stop if the server supports it, survives a
   reload, matches `ARCHITECTURE.md`; costs a run store, a status endpoint and tests. **Recommend B**.
   The stage-list component serves both; under A it is titled "Steps this run goes through" with no
   states, and the button reads "Stop waiting" with "The run continues on the server until it
   finishes."
3. **Component library**: none (above).
4. **Plan layout**: sections with in-page nav (recommended) vs tabs.
5. **Font**: Atkinson Hyperlegible Next (recommended) vs the system stack only.
6. **Dark mode. Decided 2026-11-19:** dark by default, with a light/dark toggle in the header.

Milestone 7 (T-018), decided by the owner on 2026-11-20:
7. **Mode signal. Decided: A.** (A) header badge + one mode-note line per screen; (B) a full-width strip under
   the header on every page; (C) header badge only. **Recommend A**: always visible, explained where
   it matters, no banner competing with the result honesty banners. B repeats itself on every page;
   C leaves "why is there no form?" unanswered.
8. **Recordings. Decided: A.** (A) per screen, shown with that screen's own components; (B) one `/examples`
   page listing all 8; (C) both. **Recommend A**: each screen demonstrates itself, and a visitor
   on "Analyse a job" sees a job analysis. B is one more page that duplicates the renderers' context.
9. **Source search. Decided: A.** (A) its own `/search` page and nav link, every mode; (B) on the Ask screen in
   place of the composer in demo mode only; (C) both. **Recommend A**: one purpose per page, and its
   "passages, not an answer" framing can't be mistaken for the Ask answer card. B is closer to where
   a demo visitor types, so A adds the link in Ask's mode note.
10. **Where the key goes in. Decided: A.** (A) inline panel on each model screen, shared state; (B) a header
   button opening a native `<dialog>`; (C) a `/live` page. **Recommend A**: the copy about the key
   sits next to the form that uses it, and nothing hides behind a header control. B is tidier but
   adds a second dialog pattern and a focus trap; C needs a round trip before the first question.
11. **Passcode lifetime. Decided: B, as a token.** The owner wants the passcode to survive a
   reload without storing it: after a correct passcode the server returns a signed token that expires
   in 12 hours; the tab keeps only the token (sessionStorage), never the passcode. The key stays in
   memory only (it can't be hashed: the server needs the real key to call Anthropic). Options were: (A) memory only, like the key; (B) sessionStorage for the tab. **Recommend
   A**: one rule ("both clear on reload"), one Clear button, nothing at rest in the browser. B saves
   retyping a 16+ character passcode after a reload, at the cost of a second storage story.
12. **Pre-check. Decided: B** (with the free models-list call). (A) no check: the first real request verifies passcode and key; (B) a small
   backend `POST /api/live/check` (passcode, key shape, optionally a free Anthropic call such as
   listing models) before the panel collapses. **Recommend B** if cheap to build: errors show in the
   panel at once, and a made-up key no longer spends a Voyage search. A works with this design as
   written.

## Do's and Don'ts
Do:
- Show the posting quote and the sources before the model's interpretation.
- Change the result heading, not just a badge, when a result is partial.
- Label every estimate, and say which path ran and why.
- Keep the empty states useful: a sample action, one sentence.

Don't:
- Purple or blue gradients, glows, sparkle or "AI" icons, glassmorphism, emoji in headings.
- Skill bars, percentage meters, donut charts or scores for gaps, confidence or effort.
- A big green success screen, confetti, or "Your plan is ready!" for a non-`complete` status.
- Fake progress: percentage bars, stages ticked by a timer, "almost there".
- Tooltips that hold information, identical card grids for every list, animation on page load.
- Motivational or marketing copy (owner, 2026-11-19): no inspirational quotes, slogans, taglines,
  "Land your dream job!", "Let's crush it" or cheerful filler. Copy says what the screen does and
  what happened, plainly.
- Raw HTML, markdown beyond the safe subset (see Security rules), auto-linked URLs or retrieval scores shown as the main signal.

## Known gaps
- ~~**Sources date**~~: done in T-018 step 3. `/api/health` returns `sources_as_of` (the oldest page
  fetch in the index, from `knowledge_base/index_info.json`); the footer shows "Sources as of 19 Nov
  2026 · …" and leaves the date out when it is unavailable.
- Decision 1 option A and decision 2 option B both need backend work and their own tickets.
- `GapItem.profile_evidence_ids` (p-1, c-2) cannot be shown as text: the result does not return the
  profile facts. Showing "based on: your Study-group finder project" would strengthen the evidence
  story; needs a backend field.
- `errors[]` in a `partial` result: checked 2026-11-19, all fixed texts (`workflows/nodes.py`,
  `workflows/fallback.py`; `stopped early: {reason}` uses the `FallbackReason` literal). Keep it so.
- Milestone 7 (designed above, awaiting approval). Backend contract gaps that make it harder:
  - 401 (passcode / missing key / refused key) and 429 (passcode lockout / per-IP limits / the
    visitor's Anthropic limit / Voyage) are told apart only by `detail` text; `lib/api.ts` trusts
    `detail` only for 429/502/503. Needs a machine-readable `code` in error bodies (for example
    `passcode_invalid`, `passcode_locked`, `key_missing`, `key_refused`, `rate_limited`) so the UI
    routes each to the right field without matching strings.
  - `/api/health` has no `search_enabled`, so search shows "off" only after a query fails.
  - No credentials check (decision 12): errors surface on the first real request.
  - The key passes through the GradPath server, so the copy says "sent to the GradPath server,
    which passes it to Anthropic", not "straight to Anthropic".
  - A browser password manager may still offer to save the key; the copy promises only that
    GradPath never stores it.
  - Recording list items carry no outcome or status, so the picker relies on `summary` text.
- Milestone 8: Content-Security-Policy.
- Font: Atkinson Hyperlegible Next is on Google Fonts (checked 2026-11-19); confirm the `next/font/google`
  import at build. Icons: about ten hand-drawn inline SVGs (no icon package).

# T-014: import a profile from pasted resume text
The visitor pastes a resume and gets a draft profile to review before saving. Index: `../TASKS.md`.

- **Type:** feature
- **Status:** done
- **Opened:** 2026-11-20 · **Closed:** 2026-11-20
- **GitHub Issue:** none

## Summary
Owner decision 2026-11-19 (option A): resume text fills the profile form; the resume is not a third
input to the workflow. `POST /api/profile/from-resume` takes pasted text (100-15,000 characters)
and returns a `UserProfile` draft plus notes on anything trimmed. Nothing is saved server-side;
the Profile screen fills the form and the visitor saves it. PDF/DOCX upload is Milestone 7 (uploads
are an always-hard area).

## Decision
- **One fast-tier (Haiku) structured call** with a loose schema (`ExtractedProfile`: plain strings
  and lists), then our own code turns it into a valid `UserProfile`: trim, drop contact details,
  cut text to the field limits, de-duplicate skills, cap counts, keep the whole profile under 12,000
  characters, and say what was dropped in `notes`. Rejected: asking the model for a strict
  `UserProfile` directly (one over-long field would fail validation and waste the call; the limits
  are better enforced in code).
- **Privacy (always-hard: untrusted input, tracing).**
  - The call runs inside `langsmith.tracing_context(enabled=False)`. Resume text never reaches
    LangSmith, even when tracing is on for local development. A test with a recording client
    checks that no run is created.
  - Nothing logs the text, only counts.
  - The response never includes a name, email, phone, URL or address. The prompt says to leave them
    out, and code also scrubs emails (including non-ASCII and "at/dot" forms), 10-15 digit phone
    numbers (not year ranges), links and labelled handles from every field. Patterns are tuned so
    C#, ASP.NET, Node.js/Express, `@Transactional`, GPAs and date ranges survive. Not caught: a name
    inside a sentence and short local numbers; the visitor reviews the draft before saving.
  - Model and SDK errors are logged by exception type only (`api/main.py`), since their message can
    quote model text.
  - `weekly_hours` and `timeline_weeks` are never filled from a resume.
- **Prompt injection.** The resume is wrapped in `<resume>` tags after `neutralise_tags`. The prompt
  says it is data. The output is only a draft the visitor reviews before saving, and the code checks
  its bounds.
- **Concurrency:** the call shares the chat cap (`limits.CHAT`).
- **Size:** if the cleaned profile is over 12,000 characters, descriptions are shortened first,
  then courses and skills trimmed, and whole projects or roles dropped last (they are the stronger
  evidence). Each step adds a note. A model `null` is read as empty.
- **Frontend:** a "Fill from a resume" disclosure on the Profile screen. It replaces the draft (it
  asks first if there are unsaved edits) and keeps weekly hours and timeline. It clears the pasted
  text and is never written to browser storage. Nothing is saved until "Save profile".

## Changes
- Branch: `feat/t-011-frontend` (Milestone 6 branch)
- PR:
- Files touched: `backend/src/gradpath/profiles/` (new), `api/profile.py` (new), `api/main.py`
  (router, type-only error logging), `tests/test_resume.py` (new), `tests/test_tracing.py`,
  `evaluation/resumes/sample_resume.txt` (fictional); `frontend/components/ResumeImport.tsx` (new),
  `ProfileForm.tsx`, `lib/api.ts`, `lib/types.ts` and tests.
- Commits (hash, message): `3b4cffd` feat: import a draft profile from pasted resume text, never
  traced or stored (T-014)

## Verification
- Backend: 505 tests. The new ones cover cleaning, limits, the size order, contact scrubbing
  (removals and false positives), null fields, logs that carry counts only, error logging by type,
  the look-alike tag, and API bounds, 503 and 502.
- Tracing (always-hard): with tracing on, `import_resume` records no run with the fake model or
  with `ChatClaudeCode`, on both success and failure. Control: the same call without the guard
  records 3 runs.
- Frontend: 126 tests. The browser check filled the form from the fictional resume, showed the
  badge and announcement, cleared the pasted text, and left no email on the page or in storage.
- Real runs with the local API:
  - The fictional resume: all checks passed, and the planted "ignore previous instructions" line
    was ignored.
  - The owner's own resume (kept outside git, `.git/info/exclude`): HTTP 200, with education,
    skills, courses, 4 projects and 2 roles extracted. No email, phone, link or name in the
    output. Run three times; the skill count varied with how the model split items.
- Review: code-reviewer (two rounds; all findings fixed or noted) and qa-checker (all checks
  passed).

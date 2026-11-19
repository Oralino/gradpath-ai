# T-008: tag neutraliser misses invisible and fullwidth variants
Index entries go in `../TASKS.md` (open) and `../DONE.md` (closed).

- **Type:** bug
- **Status:** done (merged, 56fd164)
- **Opened:** 2026-11-18 · **Closed:** 2026-11-18
- **GitHub Issue:** none

## Summary
Found in the T-006 router review. `safety.neutralise_tags` matches `<`, optional whitespace, `/`
and our tag names, but not a zero-width character between them (`<​/evidence>`) or fullwidth
forms (`＜／evidence＞`, `ｅｖｉｄｅｎｃｅ`). A model may still read those as our delimiters, so
text in a job posting or a retrieved page could appear to close its block. High-risk area
(prompt-injection defences).

## Cause
`\s` doesn't cover format characters (Unicode category Cf), and the pattern is ASCII only.

## Decision
Before matching, normalise the untrusted text with NFKC (fullwidth and small-form brackets,
slashes and letters become ASCII) and remove format characters (zero-width spaces and joiners,
bidi controls, soft hyphen, BOM). Then the existing pattern applies. The text the model sees
changes only in invisible or compatibility characters; quote checks in `jobs/analyze.py` already
compare NFKC forms. Rejected: listing look-alike characters in the regex (easy to miss one).
After review: the pattern now replaces only the opener (`<`, or the look-alikes NFKC leaves
alone: `‹ 〈 ⟨ 〈`) when one of our tag names follows within 12 non-word characters (covers
combining marks, variation selectors, newlines and Hangul fillers, which are not format
characters). The same normalisation is shared (`safety.normalise_untrusted`) by
`jobs/analyze.py` quote matching and `escape_attr`, so a posting with a soft hyphen still matches
the model's quote.

## Changes
- Branch: `feat/t-006-router-fallback`
- PR: https://github.com/Oralino/gradpath-ai/pull/4
- Files touched: `backend/src/gradpath/safety.py`, `jobs/analyze.py`, `backend/tests/test_safety.py` (new)
- Commits (hash, message):

## Verification
- 30 tests in `test_safety.py` (zero-width, bidi, soft hyphen, BOM, fullwidth, small-form,
  combining marks, variation selector, fillers, newline, angle-bracket look-alikes, split names,
  quotes with invisible characters, attributes); all earlier injection tests still pass.
- code-reviewer: stripping invisible characters broke quote checks (fixed by sharing the
  normaliser); non-format invisibles and look-alike brackets still passed (fixed by the lookahead
  pattern); attributes were not normalised (fixed).

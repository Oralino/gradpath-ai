# T-005: ingestion polish from the Milestone 1 review
Index entries go in `../TASKS.md` (open) and `../DONE.md` (closed).

- **Type:** change
- **Status:** done (merged, e100ccb)
- **Opened:** 2026-11-18 · **Closed:** 2026-11-18
- **GitHub Issue:** none

## Summary
Four ingestion items deferred from the Milestone 1 code review (TASKS.md "Ingestion polish"):
1. robots.txt and the per-host gap are not re-checked when a redirect leads to another host.
2. Content-Type is not checked before cleaning (a PDF would be cleaned as HTML).
3. A document that now yields zero chunks keeps its stale `processed/<doc>.jsonl`, so its old
   chunks are still indexed.
4. The index rebuild deletes the collection before re-creating it, so a failure between the two
   (or a reader during the rebuild) sees no index.

## Decision
1. Follow redirects ourselves (client `follow_redirects=False`), at most 5 hops; before each hop,
   check robots.txt for the target and wait the per-host gap.
2. Accept HTML, XHTML, Markdown and plain text, or a missing header; skip anything else with a log
   line.
3. Zero chunks: delete the stale processed file and log a warning.
4. Build into a new collection `<name>_<timestamp>`, then point the alias `<name>` at it in one
   alias update, then delete the old collection. Local Qdrant supports aliases (checked
   2026-11-18). One-time migration: when a real collection already has the alias name, it is
   deleted after the new one is built and before the alias is created (logged).
Done in parallel with T-003 step 7 by `engineer`; tests only, no re-ingest (no Voyage tokens).

## Changes
- Branch: `feat/t-003-agentic-workflow` (shared branch, separate commit)
- PR: https://github.com/Oralino/gradpath-ai/pull/3
- Files touched: `backend/src/gradpath/ingestion/fetch.py`, `ingest.py`, `index.py`,
  `backend/tests/test_ingestion.py`
- Commits (oldest first):
  - `02cde3c fix: follow redirects politely, check content type, drop stale chunks, rebuild index atomically (T-005)`
  - `1ce7749 fix: follow robots.txt redirects, keep the index on every rebuild failure, keep processed files on fetch failure (T-005)`
  - `92e6b04 fix: sweep only rebuild collections, close the migration window, keep files on partial fetch (T-005)`

## Verification
- Built by `engineer`, reviewed by `code-reviewer` twice; 251 tests pass, ruff clean. Tests only:
  no re-ingest, no Voyage tokens. The owner's local index switches to the alias layout at the
  next `ingest` (one logged migration; embeddings come from the cache).
- Review round 1 found: robots.txt redirects counted as allow-all once automatic redirects were
  off; the migration could leave no index if the alias call failed; Ctrl-C during upsert left
  orphan collections; a fetch failure deleted the last good processed file. All fixed (`1ce7749`).
- Review round 2 (minor, fixed in `92e6b04`): the orphan sweep matched any `<name>_*` collection
  (now only `<name>_<14-digit stamp><8 hex>`); `migrated` was set after the delete started; a
  partial fetch replaced or deleted the last complete file (now kept); a robots 3xx without a
  Location counted as allow-all (now disallow).
- Known: more than 5 redirects is logged as "status 310" (an internal marker, not HTTP).

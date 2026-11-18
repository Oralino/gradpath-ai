# T-005: ingestion polish from the Milestone 1 review
Index entries go in `../TASKS.md` (open) and `../DONE.md` (closed).

- **Type:** change
- **Status:** in progress
- **Opened:** 2026-11-18 · **Closed:**
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
- Files touched:
- Commits (hash, message):

## Verification

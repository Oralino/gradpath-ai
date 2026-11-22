# T-015: citations link to raw GitHub files
Citations for some sources opened unreadable raw files. Index: `../../TASKS.md`, `../../DONE.md`.

- **Type:** bug
- **Status:** done
- **Opened:** 2026-11-20 · **Closed:** 2026-11-20
- **GitHub Issue:** none

## Summary
Found on the Job screen's first real run. Citation chips for the Tech Interview Handbook, the
System Design Primer and other GitHub-hosted sources pointed at `raw.githubusercontent.com`: plain
markdown, with that hostname shown under the title.

## Cause
Ingestion stores each chunk's `source_url` as the URL of the page it was fetched from
(`fetch_source` → `FetchedPage.url` → `chunk_page`). That is right for multi-page sources, since a
Kubernetes chunk links to its own page. But GitHub-hosted sources are fetched as raw files
(`fetch_urls` in `source_manifest.csv`) to get clean markdown, so their chunks carry the raw URL.
`rag.answer.to_citation` passed it through unchanged.

## Decision
- `readable_url()` in `rag/answer.py`, applied in `to_citation`, maps
  `https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}` to
  `https://github.com/{owner}/{repo}/blob/{ref}/{path}` (the rendered file). Every citation path
  uses `to_citation`: answers, job analysis, roadmap and fallback.
- It is done at response time, not at ingest. Rejected: changing ingestion, because re-ingesting
  would re-embed the chunks and spend free-tier Voyage tokens (owner rule) for a display change.
- Rejected: using the manifest's `source_url` (for example `techinterviewhandbook.org`). It is the
  site's home page, not the page the chunk came from.

## Changes
- Branch: `feat/t-011-frontend` (Milestone 6 branch)
- Files touched: `backend/src/gradpath/rag/answer.py`, `backend/tests/test_rag.py`
- Commits (hash, message): see `git log --grep=T-015`

## Verification
4 new tests: a raw URL is mapped, and a normal URL, an `http:` raw URL and a malformed raw URL are
left alone. 509 backend tests pass. On a real Job screen run of the sample posting, 13 citation
links went to `github.com/.../blob/...` and none to `raw.githubusercontent.com`.

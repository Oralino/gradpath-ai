# T-009: fill the knowledge-base gaps before Milestone 5
Index entries go in `../TASKS.md` (open) and `../DONE.md` (closed).

- **Type:** change
- **Status:** done (PR open)
- **Opened:** 2026-11-18 · **Closed:** 2026-11-19
- **GitHub Issue:** none

## Summary
The corpus has no Docker, Kubernetes, CI/CD or LLM/RAG tooling sources, and only one primer
section each on caching and message queues (System Design Primer) and one page on STAR
(Tech Interview Handbook). The Milestone 4 comparison showed it: "What is Docker?" was answered
"not covered". Fill these before Milestone 5, so hybrid retrieval and reranking are measured on
the final corpus (owner decision 2026-11-18: before Milestone 5, keep adding depth even where a
topic is partly covered).

## Decision
10 sources, 33 pages, proposed 2026-11-18 (manifest status `proposed`; nothing downloaded until
the owner approves). Licences checked on each repository's LICENSE or README the same day:
Apache 2.0, CC BY 4.0, MIT, CC BY-SA 4.0, CC BY-SA 2.5 (MDN, as for the approved MDN entries),
Apache 2.0 / MPL 2.0 (RabbitMQ). Pages fetched as raw files from the source repositories where
possible (clean Markdown, no site chrome). Rejected: Wikipedia (its servers refuse automated
clients unless the User-Agent carries contact details, which would put personal data in
requests), Redis docs (CC BY-NC-SA 4.0 and product-specific), Qdrant docs (no licence in the
repo), the two longest Kubernetes and RabbitMQ pages (Deployments 60 KB, publisher confirms 32 KB)
to keep Voyage use small. New collection `ai_engineering` for LLM/RAG sources.
Owner 2026-11-18: approve all 10, and include the two long pages after all (10 sources, 35
pages). The dry run showed template markup in the chunks (Kubernetes 83 of 172 chunks with Hugo
shortcodes, GitHub Docs 29 of 33 with Liquid tags), so `clean_markdown` now strips Hugo, Liquid
and line-level JSX markup outside code fences, keeping the words it stood for (tooltip text,
product names, callout labels). The dry run also found that the approved OWASP API Top 10 page
moved to `api-security.owasp.org`, which T-007 rightly refused as an unlisted host; the fetch URL
now points there (same content, no re-embedding).

## Changes
- Branch: `feat/t-009-corpus-gaps`
- PR: https://github.com/Oralino/gradpath-ai/pull/5
- Files touched: `knowledge_base/source_manifest.csv`, `backend/src/gradpath/ingestion/clean.py`,
  `backend/tests/test_ingestion.py`
- Commits (hash, message):

## Verification
- Dry run (no embedding): all 35 new pages fetched; 638 new chunks, about 126K tokens; markup left
  only inside code fences; existing sources: 10 Tech Interview Handbook chunks change (an ad
  component removed), nothing else. 14 new cleaner tests (439 total).
- Real ingest (2026-11-19): 1,592 chunks indexed, 946 from the embedding cache, 646 embedded;
  the one-time T-005 migration ran (alias `gradpath_kb` -> one rebuilt collection).
- Retrieval eval: labels updated to v1.2 with the owner (q-030 URL, q-034 now covered); Recall@5
  0.953, MRR 0.984, uncovered rejected 7/8; q-031 is a near-topic false accept at 0.520
  (EVALUATION.md, "Retrieval on corpus v2").

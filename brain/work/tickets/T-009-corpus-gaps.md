# T-009: fill the knowledge-base gaps before Milestone 5
Index entries go in `../TASKS.md` (open) and `../DONE.md` (closed).

- **Type:** change
- **Status:** in progress
- **Opened:** 2026-11-18 · **Closed:**
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

## Changes
- Branch: `feat/t-009-corpus-gaps`
- PR:
- Files touched: `knowledge_base/source_manifest.csv`
- Commits (hash, message):

## Verification

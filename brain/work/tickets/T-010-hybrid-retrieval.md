# T-010: Milestone 5, hybrid retrieval + reranking
Index entries go in `../TASKS.md` (open) and `../DONE.md` (closed).

- **Type:** feature
- **Status:** in progress
- **Opened:** 2026-11-19 · **Closed:**
- **GitHub Issue:** none

## Summary
Add keyword (sparse, BM25) search next to semantic search, fuse the two rankings, and rerank the
fused candidates. Keep each part only if the retrieval evaluation shows it helps, compared against
semantic-only on the same corpus (v2, 1,592 chunks) and labels (v1.2): Recall@K, Precision@K, MRR,
recall by tag, latency. Also test whether a reranker score separates "covered" from "near-topic
but not covered" better than the 0.45 cosine threshold, whose margin is gone (`q-031` Kubernetes
liveness probes, uncovered, best score 0.520; lowest covered 0.526).

Baseline: `evaluation/results/retrieval-20261119-024443.json` (Recall@5 0.953, Precision@5 0.631,
MRR 0.984; misses `q-001`, `q-027`, `q-034`; exact_term recall@5 already 1.0).

## Decision
Pending the owner's answers (2026-11-19): which reranker (local free cross-encoder vs Voyage
rerank tokens), whether to add harder exact-term and near-topic uncovered labels before measuring,
and how much extra latency is acceptable for a recall gain.

Constraints: zero cost (sparse vectors computed locally, re-indexing reuses the embedding cache, no
re-embedding); our own code owns fusion, reranking and evaluation (no LangChain retrievers).

## Changes
- Branch: `feat/t-010-hybrid-retrieval`
- PR:
- Files touched:
- Commits (hash, message):

## Verification

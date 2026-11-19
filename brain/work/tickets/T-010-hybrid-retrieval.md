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
Owner, 2026-11-19 (all as recommended):
- **Reranker:** local cross-encoder `Xenova/ms-marco-MiniLM-L-6-v2` via fastembed (80 MB,
  Apache-2.0); try `BAAI/bge-reranker-base` (1 GB, MIT) only if MiniLM doesn't help. No Voyage
  reranker: tokens would be cheap (measured with Voyage's local tokenizer: chunk mean 172 tokens,
  question 12, so ~3.7K tokens per question for 20 candidates, ~147K per 40-question eval), but each
  question would spend a second request of the free tier's 3 per minute.
- **Keyword search:** fastembed `Qdrant/bm25` sparse vectors (IDF modifier) stored next to the dense
  vectors; dense vectors come from the embedding cache (0 Voyage tokens). Rejected: Qdrant's
  built-in BM25 `TextQuery`, which supports only the plain word tokenizer (no stemming) in local
  mode.
- **Fusion:** our own RRF over the dense and sparse top-20 lists (Qdrant runs the two searches).
- **Labels first:** add ~6 exact-term and ~4 near-topic uncovered questions (labels v1.3, owner
  approves each) before measuring; the current exact_term questions already score 1.0.
- **Latency budget:** up to +300 ms per question (p95, owner's PC) for a clear gain (+0.03 Recall@5,
  a fixed miss, or a real covered/uncovered gap); drop any part that doesn't clear it.

Checked 2026-11-19: `qdrant-client==1.20.0` local mode supports sparse vectors with `Modifier.IDF`,
`query_points` with `prefetch`, and RRF/DBSF fusion (source read); fastembed 0.9.1 (2026-10-24)
fits qdrant-client's `fastembed>=0.9,<0.10` extra and Python 3.13.

Constraints: zero cost (sparse vectors computed locally, re-indexing reuses the embedding cache, no
re-embedding); our own code owns fusion, reranking and evaluation (no LangChain retrievers).

## Changes
- Branch: `feat/t-010-hybrid-retrieval`
- PR:
- Files touched:
- Commits (hash, message):

## Verification
- Labels v1.3 (owner approved 2026-11-19): 50 questions load and validate; 439 tests pass; ruff clean.
- Semantic baseline on v1.3 (`retrieval-20261119-062918.json`): Recall@5 0.961, MRR 0.987,
  exact_term Recall@5 1.0 (13 questions); at 0.45 covered kept 97%, uncovered rejected 67%
  (EVALUATION.md, "Semantic baseline on labels v1.3").
- Reranker (owner: reranker first). CPU speed on the owner's PC (16 threads, MiniLM-L-6, real
  chunks): 20 candidates p50 ~310 ms, p95 ~490-590 ms; 10 candidates p95 ~170-240 ms.
- Real comparison runs (EVALUATION.md, "Experiment 3: reranking"): MiniLM-L-6 @10 Recall@5 0.921,
  MRR 0.904, 94/198 ms; bge-reranker-base @10 Recall@5 0.961, MRR 0.921, 660/986 ms. Neither
  separates covered from near-topic uncovered better than cosine. 447 tests pass; ruff clean.
- Hybrid (EVALUATION.md, "Experiment 2: semantic vs hybrid"): BM25 alone Recall@5 0.855, MRR
  0.755; RRF hybrid 0.921 / 0.914 vs semantic 0.961 / 0.987; abstention unchanged; +11-15 ms per
  question. 455 tests pass; ruff clean.

"""Query embeddings behind a cache and a spending budget, for the deployed server.

Wraps the throttled Voyage embeddings (`get_retrieval_service` does this outside local mode) so
every paid call is cached first and budgeted before it is made. Queries only, never documents.
"""

from collections.abc import Callable

import voyageai.error
from langchain_core.embeddings import Embeddings

from gradpath.ingestion.embed import WindowFull
from gradpath.retrieval.budget import EmbedBudget
from gradpath.retrieval.query_cache import QueryCache

# Failures where Voyage charged nothing: our free-tier window refused before sending, or Voyage
# refused with a 429. Other errors (a timeout after sending) may have been paid for.
REFUSED = (WindowFull, voyageai.error.RateLimitError)


class GuardedEmbeddings(Embeddings):
    """Cache hits are free; misses spend budget before Voyage is called (fail closed)."""

    def __init__(self, inner, cache: QueryCache, budget: EmbedBudget) -> None:
        self.inner = inner
        self.cache = cache
        self.budget = budget

    def _guard(
        self, texts: list[str], embed_misses: Callable[[list[str]], list[list[float]]]
    ) -> list[list[float]]:
        """Cache lookup, spend for the misses only, embed them, store them, keep input order.
        The original text goes to Voyage; normalisation only builds the cache key."""
        out = self.cache.get_many(texts)
        miss = [i for i, v in enumerate(out) if v is None]
        if miss:
            self.budget.spend(len(miss))
            try:
                fresh = embed_misses([texts[i] for i in miss])
            except REFUSED:
                # Refund only what certainly cost nothing: one question, refused before or by
                # Voyage. A failed batch may have paid for its first requests: keep that spend.
                if len(miss) == 1:
                    self.budget.refund(1)
                raise
            self.cache.put_many([texts[i] for i in miss], fresh)
            for i, v in zip(miss, fresh, strict=True):
                out[i] = v
        return out  # type: ignore[return-value]

    def embed_query(self, text: str) -> list[float]:
        return self._guard([text], lambda t: [self.inner.embed_query(t[0])])[0]

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        batch = getattr(self.inner, "embed_queries", None)
        if batch is None:
            return self._guard(texts, lambda ts: [self.inner.embed_query(t) for t in ts])
        return self._guard(texts, batch)

    def embed_query_now(self, text: str) -> list[float]:
        """Never-waiting variant used by public search (see `ThrottledEmbeddings`)."""
        fn = getattr(self.inner, "embed_query_now", None) or self.inner.embed_query
        return self._guard([text], lambda t: [fn(t[0])])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("GuardedEmbeddings embeds queries only")

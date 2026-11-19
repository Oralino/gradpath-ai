"""Keyword (BM25) search and rank fusion: the hybrid half of Milestone 5 (T-010).

BM25 scores a chunk by the question's literal words: rare words count more (IDF), repeats count
with diminishing returns (k1), and long chunks are scaled down (b). fastembed's `Qdrant/bm25`
computes the per-chunk term weights locally (no API, no tokens); Qdrant applies the IDF at query
time (`Modifier.IDF`). `rrf_fuse` merges the keyword and semantic rankings by rank, so their
incompatible scores never meet. Used by the retrieval eval's hybrid variant; the retrieval service
gets it only if that comparison shows it helps.
"""

from collections.abc import Sequence

from langchain_core.documents import Document
from qdrant_client import QdrantClient, models

from gradpath.ingestion.index import point_id
from gradpath.retrieval.rerank import MODEL_CACHE_DIR
from gradpath.retrieval.service import Evidence, to_evidence

BM25_MODEL = "Qdrant/bm25"  # ~10 MB of stopword lists, Apache-2.0
SPARSE_VECTOR = "bm25"
RRF_K = 60  # the constant from the original RRF paper (Cormack et al., 2009)


class Bm25Encoder:
    """fastembed BM25: weighted term ids for chunks, plain term ids for queries.

    `avg_len` is the corpus's mean chunk length in kept tokens (after stopwords), BM25's length
    normaliser; `fit` measures it from the chunks themselves instead of fastembed's default 256.
    """

    def __init__(self, cache_dir=MODEL_CACHE_DIR):
        from fastembed.sparse.bm25 import Bm25

        self.model = Bm25(BM25_MODEL, cache_dir=str(cache_dir))

    def fit(self, texts: Sequence[str]) -> float:
        """Set avg_len to the mean kept-token count of `texts` (fastembed 0.9.1's tokeniser)."""
        if not texts:
            raise ValueError("no texts to measure")
        lengths = [len(self.model._stem(self.model.tokenizer.tokenize(t))) for t in texts]
        self.model.avg_len = max(1.0, sum(lengths) / len(lengths))
        return self.model.avg_len

    def documents(self, texts: Sequence[str]) -> list[models.SparseVector]:
        return [_to_sparse(e) for e in self.model.embed(list(texts))]

    def query(self, text: str) -> models.SparseVector:
        return _to_sparse(next(iter(self.model.query_embed(text))))


def _to_sparse(embedding) -> models.SparseVector:
    return models.SparseVector(
        indices=[int(i) for i in embedding.indices], values=[float(v) for v in embedding.values]
    )


class SparseIndex:
    """An in-memory Qdrant collection of BM25 vectors over the same chunks as the dense index.

    Built from the processed chunks (`knowledge_base/processed/`), so the experiment leaves the real
    index untouched. Point ids and payload match ingestion.index, so hits map to the same Evidence.
    """

    def __init__(self, documents: list[Document], encoder: Bm25Encoder):
        if not documents:
            raise ValueError("no documents to index")
        self.encoder = encoder
        self.avg_len = encoder.fit([d.page_content for d in documents])
        self.client = QdrantClient(":memory:")
        self.collection = "bm25"
        self.client.create_collection(
            self.collection,
            vectors_config={},
            sparse_vectors_config={
                SPARSE_VECTOR: models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )
        vectors = encoder.documents([d.page_content for d in documents])
        self.client.upsert(
            self.collection,
            points=[
                models.PointStruct(
                    id=point_id(d.metadata["chunk_id"]),
                    vector={SPARSE_VECTOR: v},
                    payload={"page_content": d.page_content, "metadata": d.metadata},
                )
                for d, v in zip(documents, vectors, strict=True)
            ],
        )
        self.size = len(documents)

    def search(self, query: str, k: int) -> list[Evidence]:
        """Top `k` chunks by BM25 score (chunks sharing no query term are not returned)."""
        hits = self.client.query_points(
            self.collection,
            query=self.encoder.query(query),
            using=SPARSE_VECTOR,
            limit=k,
            with_payload=True,
        ).points
        return [
            to_evidence(
                Document(page_content=h.payload["page_content"], metadata=h.payload["metadata"]),
                h.score,
            )
            for h in hits
        ]


def rrf_fuse(
    rankings: Sequence[Sequence[str]], k: int = RRF_K, weights: Sequence[float] | None = None
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: each id scores sum(weight / (k + rank)), rank starting at 1.

    Only ranks matter, so cosine and BM25 scores never have to be put on one scale. A larger `k`
    flattens the difference between ranks. Ties go to the id with the better single rank, then
    to the earlier list (the dense one, by the eval's convention). A repeated id counts once per
    list, at its best rank.
    """
    if weights is not None and len(weights) != len(rankings):
        raise ValueError("one weight per ranking")
    scores: dict[str, float] = {}
    best: dict[str, tuple[int, int]] = {}
    for li, ranking in enumerate(rankings):
        w = 1.0 if weights is None else weights[li]
        seen: set[str] = set()
        for rank, item in enumerate(ranking, 1):
            if item in seen:
                continue
            seen.add(item)
            scores[item] = scores.get(item, 0.0) + w / (k + rank)
            best[item] = min(best.get(item, (rank, li)), (rank, li))
    return sorted(scores.items(), key=lambda kv: (-kv[1], best[kv[0]]))

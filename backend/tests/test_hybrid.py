"""Hybrid retrieval (T-010): RRF fusion, the sparse index, cosine lookup and the hybrid eval.

A fake BM25 encoder stands in for fastembed's (no model download in tests); the in-memory Qdrant
still applies the real IDF modifier.
"""

import pytest
from conftest import KB_DOCS, KeywordEmbeddings
from qdrant_client import QdrantClient, models

from gradpath.evaluation.dataset import Question, Target
from gradpath.evaluation.retrieval_eval import run_eval, run_hybrid_eval
from gradpath.ingestion.index import rebuild_index
from gradpath.retrieval import RetrievalService
from gradpath.retrieval.sparse import SparseIndex, rrf_fuse


class FakeBm25:
    """Term counts as weights, one id per word; queries weigh every word 1."""

    def __init__(self):
        self.ids: dict[str, int] = {}

    def _id(self, word: str) -> int:
        return self.ids.setdefault(word, len(self.ids) + 1)

    def fit(self, texts):
        return sum(len(t.split()) for t in texts) / len(texts)

    def documents(self, texts):
        out = []
        for t in texts:
            counts: dict[int, float] = {}
            for w in t.lower().split():
                counts[self._id(w)] = counts.get(self._id(w), 0.0) + 1.0
            out.append(models.SparseVector(indices=list(counts), values=list(counts.values())))
        return out

    def query(self, text):
        ids = sorted({self._id(w) for w in text.lower().replace("?", " ").split()})
        return models.SparseVector(indices=ids, values=[1.0] * len(ids))


class BatchEmbeddings(KeywordEmbeddings):
    def embed_queries(self, texts):
        return [self._vec(t) for t in texts]


@pytest.fixture
def service():
    client = QdrantClient(":memory:")
    rebuild_index(client, "kb", KB_DOCS, KeywordEmbeddings())
    return RetrievalService(client, "kb", BatchEmbeddings(), k=3, min_score=0.5)


# --- fusion --------------------------------------------------------------------------------


def test_rrf_scores_by_rank_and_rewards_agreement():
    fused = rrf_fuse([["a", "b", "c"], ["c", "d"]], k=60)
    scores = dict(fused)
    assert scores["c"] == pytest.approx(1 / 63 + 1 / 61)  # in both lists: wins
    # a: 1/61; b and d: 1/62 each (both rank 2), tie goes to the first (dense) list
    assert [i for i, _ in fused] == ["c", "a", "b", "d"]


def test_rrf_ties_go_to_the_better_rank_then_the_first_list():
    assert [i for i, _ in rrf_fuse([["a"], ["b"]])] == ["a", "b"]  # same score: dense list first
    assert [i for i, _ in rrf_fuse([["x", "a"], ["b", "x"]])][0] == "x"


def test_rrf_counts_a_repeated_id_once_and_checks_weights():
    assert dict(rrf_fuse([["a", "a"]], k=0))["a"] == 1.0
    assert dict(rrf_fuse([["a"], ["b"]], k=0, weights=[2.0, 1.0])) == {"a": 2.0, "b": 1.0}
    with pytest.raises(ValueError):
        rrf_fuse([["a"]], weights=[1.0, 2.0])
    assert rrf_fuse([]) == []


# --- sparse index and cosine lookup ---------------------------------------------------------


def test_sparse_index_finds_literal_words_with_idf():
    index = SparseIndex(KB_DOCS, FakeBm25())
    hits = index.search("git", 5)
    assert [h.chunk_id for h in hits] == ["git:0:0"]  # only chunks sharing a query word come back
    assert hits[0].document_id == "git" and hits[0].text == "git branch branch"
    assert index.search("sourdough", 5) == []
    with pytest.raises(ValueError):
        SparseIndex([], FakeBm25())


def test_dense_scores_match_search_scores(service):
    vector = service.embeddings.embed_query("sql index")
    found = service.search_vectors(["sql index"], [vector], k=6)[0].evidence
    looked_up = service.dense_scores(vector, [e.chunk_id for e in found] + ["no-such-chunk"])
    assert set(looked_up) == {e.chunk_id for e in found}  # unknown ids are left out
    for e in found:
        assert looked_up[e.chunk_id] == pytest.approx(e.score, abs=1e-5)
    assert service.dense_scores(vector, []) == {}


# --- hybrid eval ---------------------------------------------------------------------------

PG = Target(document_id="pg", page="https://example.org/pg")
GIT = Target(document_id="git", page="https://example.org/git")
QUESTIONS = [
    Question(id="q-1", question="sql index", covered=True, relevant=[PG], tags=["db"]),
    Question(id="q-2", question="git branch", covered=True, relevant=[GIT], tags=["git"]),
    Question(id="q-3", question="sourdough bread", covered=False),
]


def test_hybrid_eval_reports_three_variants_on_cosine_scores(service):
    variants = run_hybrid_eval(
        service, QUESTIONS, SparseIndex(KB_DOCS, FakeBm25()), candidates=3, ks=(1, 3), report_k=3
    )
    assert list(variants) == ["semantic", "bm25", "hybrid"]

    plain = run_eval(service, QUESTIONS, ks=(1, 3), report_k=3)[0]
    assert variants["semantic"][0].recall == plain.recall
    assert variants["semantic"][0].covered_kept == plain.covered_kept

    summary, _, results = variants["hybrid"]
    assert summary.recall[3] == 1.0
    assert summary.threshold == 0.5  # the cosine threshold, unchanged
    assert summary.uncovered_rejected == 1.0  # BM25 found nothing for sourdough
    for r in results:  # every returned chunk carries a cosine score, not an RRF score
        assert all(-1.0 <= c.score <= 1.0 for c in r.ranked)
    assert summary.extra_ms_p50 is not None
    assert variants["bm25"][2][2].ranked == []  # no shared word: BM25 returns nothing


def test_hybrid_eval_refuses_chunks_missing_from_the_dense_index(service):
    extra = KB_DOCS + [
        KB_DOCS[0].model_copy(update={"metadata": {**KB_DOCS[0].metadata, "chunk_id": "x:0:0"}})
    ]
    with pytest.raises(ValueError, match="missing from the dense index"):
        run_hybrid_eval(
            service, QUESTIONS, SparseIndex(extra, FakeBm25()), candidates=6, ks=(1, 3), report_k=3
        )


def test_hybrid_eval_needs_enough_candidates(service):
    with pytest.raises(ValueError, match="candidates"):
        run_hybrid_eval(
            service, QUESTIONS, SparseIndex(KB_DOCS, FakeBm25()), candidates=2, ks=(3,), report_k=3
        )

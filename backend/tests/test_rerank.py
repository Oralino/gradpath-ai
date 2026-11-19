"""Reranking (T-010): score helpers, ordering, and the semantic-vs-rerank eval (fake reranker)."""

import pytest
from conftest import KB_DOCS, KeywordEmbeddings
from qdrant_client import QdrantClient

from gradpath.evaluation.dataset import Question, Target
from gradpath.evaluation.retrieval_eval import (
    ComparisonReport,
    EvalReport,
    format_comparison,
    format_report,
    percentile,
    run_eval,
    run_rerank_eval,
)
from gradpath.ingestion.index import rebuild_index
from gradpath.retrieval import Evidence, RetrievalService
from gradpath.retrieval.rerank import CrossEncoderReranker, rerank, sigmoid


class FakeReranker:
    """Fixed score per (query, chunk text); records calls so tests see the warm-up and batches."""

    def __init__(self, scores: dict[tuple[str, str], float], default: float = 0.05):
        self.scores = scores
        self.default = default
        self.calls: list[tuple[str, list[str]]] = []

    def score(self, query: str, texts: list[str]) -> list[float]:
        self.calls.append((query, texts))
        return [self.scores.get((query, t), self.default) for t in texts]


class BatchEmbeddings(KeywordEmbeddings):
    def __init__(self):
        self.batch_calls = 0

    def embed_queries(self, texts):
        self.batch_calls += 1
        return [self._vec(t) for t in texts]


@pytest.fixture
def service():
    client = QdrantClient(":memory:")
    rebuild_index(client, "kb", KB_DOCS, KeywordEmbeddings())
    return RetrievalService(client, "kb", BatchEmbeddings(), k=3, min_score=0.5)


PG = Target(document_id="pg", page="https://example.org/pg")
SQLITE = Target(document_id="sqlite", page="https://example.org/sqlite")
MDN = Target(document_id="mdn", page="https://example.org/mdn")
QUESTIONS = [
    Question(id="q-1", question="sql index", covered=True, relevant=[SQLITE], tags=["db"]),
    Question(id="q-2", question="http status", covered=True, relevant=[MDN], tags=["http"]),
    Question(id="q-3", question="sql sourdough", covered=False),
]
# The reranker prefers the sqlite chunk for q-1 and gives the uncovered question nothing above 0.5.
FAKE = {
    ("sql index", "index sql"): 0.9,
    ("sql index", "sql index"): 0.3,
    ("http status", "http status status"): 0.8,
}


def ev(chunk_id: str, text: str) -> Evidence:
    return Evidence(
        chunk_id=chunk_id, document_id="d", title="d", source_url="u", text=text, score=0.5
    )


# --- helpers -------------------------------------------------------------------------------


def test_sigmoid_is_bounded_and_monotonic():
    assert sigmoid(0.0) == 0.5
    assert 0.0 <= sigmoid(-1000.0) < sigmoid(-1.0) < sigmoid(1.0) < sigmoid(1000.0) <= 1.0


def test_rerank_orders_by_score_and_keeps_ties_in_semantic_order():
    chunks = [ev("a", "x"), ev("b", "y"), ev("c", "z")]
    pairs = rerank("q", chunks, FakeReranker({("q", "y"): 0.9, ("q", "x"): 0.2, ("q", "z"): 0.2}))
    assert [(e.chunk_id, s) for e, s in pairs] == [("b", 0.9), ("a", 0.2), ("c", 0.2)]
    assert pairs[0][0].score == 0.5  # evidence unchanged: score stays the cosine similarity


def test_rerank_refuses_a_score_count_mismatch():
    class Short:
        def score(self, query, texts):
            return [0.5]

    with pytest.raises(ValueError, match="2 chunks"):
        rerank("q", [ev("a", "x"), ev("b", "y")], Short())


def test_cross_encoder_loads_nothing_for_an_empty_list():
    reranker = CrossEncoderReranker()
    assert reranker.score("q", []) == []
    assert reranker._model is None  # lazy: no download or ONNX session for nothing


def test_percentile_nearest_rank():
    assert percentile([5.0, 1.0, 3.0, 2.0, 4.0], 0.5) == 3.0
    assert percentile([1.0, 2.0], 0.95) == 2.0
    assert percentile([7.0], 0.95) == 7.0


# --- eval ----------------------------------------------------------------------------------


def test_rerank_eval_compares_variants_on_one_embedding_call(service):
    reranker = FakeReranker(FAKE)
    variants = run_rerank_eval(
        service, QUESTIONS, reranker, candidates=(3, 6), ks=(1, 3), report_k=3
    )

    assert list(variants) == ["semantic", "rerank@3", "rerank@6"]
    assert service.embeddings.batch_calls == 1  # both variants share one embedding request
    assert reranker.calls[0] == ("warm up", ["warm up"])
    assert [len(texts) for _, texts in reranker.calls[1:4]] == [3, 3, 3]  # top 3 per question

    semantic = variants["semantic"][0]
    plain = run_eval(service, QUESTIONS, ks=(1, 3), report_k=3)[0]
    assert semantic.recall == plain.recall and semantic.mrr == plain.mrr
    assert semantic.extra_ms_p50 is None

    summary, sweep, results = variants["rerank@6"]
    assert (
        results[0].ranked[0].chunk_id == "sqlite:0:0"
    )  # the reranker's favourite moved to the top
    assert summary.recall[1] == 1.0 and summary.mrr[3] == 1.0
    assert summary.threshold == 0.5
    assert results[0].best_score == 0.9  # abstention judged on the reranker's score
    assert summary.uncovered_rejected == 1.0 and summary.covered_kept == 1.0
    assert summary.extra_ms_p50 is not None and summary.extra_ms_p95 >= summary.extra_ms_p50
    assert sweep[0].threshold == 0.01  # the reranker grid, not the cosine one


def test_rerank_eval_needs_enough_candidates(service):
    with pytest.raises(ValueError, match="candidate"):
        run_rerank_eval(
            service, QUESTIONS, FakeReranker(FAKE), candidates=(2,), ks=(1, 3), report_k=3
        )
    with pytest.raises(ValueError):
        run_rerank_eval(service, [], FakeReranker(FAKE), candidates=(3,), ks=(3,), report_k=3)


def test_reports_show_both_variants_and_covered_questions_below_threshold(service):
    reranker = FakeReranker(
        {("sql index", "index sql"): 0.9}
    )  # q-2's chunks all score 0.05: wrongly rejected
    variants = run_rerank_eval(service, QUESTIONS, reranker, candidates=(3,), ks=(1, 3), report_k=3)
    reports = {
        name: EvalReport(run_at="now", config={}, summary=s, threshold_sweep=w, questions=r)
        for name, (s, w, r) in variants.items()
    }
    text = format_report(reports["rerank@3"], 3)
    assert "Covered questions below the threshold (1):" in text
    assert "- q-2 best 0.050: http status" in text
    assert "added p50" in text

    table = format_comparison(ComparisonReport(run_at="now", config={}, variants=reports))
    assert "| Metric | semantic | rerank@3 |" in table
    assert "| Threshold | 0.5 | 0.5 |" in table
    assert "| Added ms p50 / p95 | - |" in table

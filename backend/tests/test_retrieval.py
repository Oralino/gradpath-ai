"""Retrieval service tests: in-memory Qdrant, keyword embeddings (no Voyage, no network)."""

import pytest

from gradpath.retrieval import Evidence, RetrievalService
from gradpath.retrieval.service import build_filter, cap_per_document


@pytest.fixture
def service(kb_service: RetrievalService) -> RetrievalService:
    return kb_service


def test_search_returns_scored_citable_evidence(service):
    result = service.search("http status")
    assert not result.insufficient
    top = result.evidence[0]
    assert top.chunk_id == "mdn:0:0"
    assert top.source_url == "https://example.org/mdn" and top.section == "Intro > Basics"
    assert top.score == pytest.approx(result.best_score) and top.score > 0.9


def test_results_are_sorted_and_limited_to_k(service):
    result = service.search("sql index")
    scores = [e.score for e in result.evidence]
    assert scores == sorted(scores, reverse=True)
    assert len(result.evidence) == 3


def test_unrelated_query_is_flagged_insufficient(service):
    result = service.search("kubernetes security clearance")
    assert result.insufficient
    assert result.evidence == []
    assert result.best_score is not None and result.best_score < 0.5


def test_filter_by_collection(service):
    # Without the filter, the sql chunks would outrank git for this query.
    query = "sql index git branch"
    assert service.search(query).evidence[0].document_id != "git"
    result = service.search(query, filters={"collection": "career_resources"})
    assert {e.document_id for e in result.evidence} == {"git"}


def test_max_per_document_spreads_sources(service):
    result = service.search("sql index", k=3, max_per_document=1)
    assert {e.document_id for e in result.evidence} == {"pg", "sqlite"}


def test_build_filter_accepts_str_or_list():
    assert build_filter(None) is None
    f = build_filter({"collection": "a", "document_id": ["x", "y"]})
    assert [c.key for c in f.must] == ["metadata.collection", "metadata.document_id"]
    assert f.must[1].match.any == ["x", "y"]


def test_cap_per_document_stops_at_k():
    ev = [
        Evidence(chunk_id=f"d{i}", document_id="d", title="", source_url="", text="", score=1.0)
        for i in range(5)
    ]
    assert len(cap_per_document(ev, k=2, cap=None)) == 2
    assert len(cap_per_document(ev, k=5, cap=1)) == 1

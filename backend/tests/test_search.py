"""Source search without a model (T-018 step 4): in-memory knowledge base, no network."""

import logging

import pytest
import voyageai.error
from conftest import plain
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_demo import use_mode

from gradpath.api import limits
from gradpath.api import main as main_module
from gradpath.api.main import SEARCH_DOWN, SEARCH_LIMITED, create_app, open_retrieval
from gradpath.api.search import SEARCH_OFF
from gradpath.config import Settings
from gradpath.ingestion.embed import ThrottledEmbeddings, WindowFull
from gradpath.rag.sources import MAX_EXCERPT_CHARS, NO_RULE, excerpt, preview_route

QUERY_SECRET = "zebra-unique-query-text"


def client(retrieval) -> TestClient:
    app = create_app(use_lifespan=False)
    app.state.retrieval = retrieval
    return TestClient(app)


@pytest.mark.parametrize("mode", ["local", "demo", "live"])
def test_returns_passages_with_citations_in_every_mode(kb_service, monkeypatch, mode):
    use_mode(monkeypatch, mode)
    resp = client(kb_service).post("/api/search", json={"query": "  sql index  "})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "sql index" and data["insufficient"] is False
    hits = data["hits"]
    assert 1 <= len(hits) <= 3
    # At most two passages per document, so other sources get a place.
    assert (
        max(sum(h["citation"]["chunk_id"].startswith(d) for h in hits) for d in ("pg", "sqlite"))
        <= 2
    )
    assert hits[0]["citation"]["source_url"].startswith("https://example.org/")
    assert "sql" in hits[0]["excerpt"]


def test_an_uncovered_query_is_flagged_insufficient(kb_service):
    data = client(kb_service).post("/api/search", json={"query": "kubernetes probes"}).json()
    assert data["hits"] == [] and data["insufficient"] is True


def test_the_route_preview_uses_rules_only():
    decision = preview_route("What is an index?")
    assert decision is not None
    assert (decision.route, decision.kind, decision.decided_by) == (
        "traditional_rag", "knowledge_question", "rules",
    )  # fmt: skip
    assert preview_route("How should a service shut down gracefully?") is None


def test_the_response_carries_the_preview_or_the_note(kb_service):
    c = client(kb_service)
    ruled = c.post("/api/search", json={"query": "What is a sql index?"}).json()
    assert ruled["route_preview"]["route"] == "traditional_rag" and ruled["route_note"] is None
    open_ = c.post("/api/search", json={"query": "sql index tips"}).json()
    assert open_["route_preview"] is None and open_["route_note"] == NO_RULE


def test_excerpts_are_cut_at_a_word_with_an_ellipsis():
    long = "word " * 400
    cut = excerpt(long)
    assert len(cut) <= MAX_EXCERPT_CHARS + 1 and cut.endswith("word…")
    assert excerpt("  short   text ") == "short text"


def test_excerpts_keep_line_breaks_for_code():
    code = "```sql\nCREATE INDEX t_ab\n    ON t (a, b);\n\n\n```"
    assert excerpt(code) == "```sql\nCREATE INDEX t_ab\nON t (a, b);\n```"


def test_a_limit_between_two_words_keeps_the_last_word():
    assert excerpt("abcd efgh", limit=4) == "abcd…"
    assert excerpt("abcd efgh", limit=6) == "abcd…"
    assert excerpt("abcdefghij", limit=4) == "abcd…"  # one long word: hard cut


@pytest.mark.parametrize(
    "body", [{"query": "  "}, {"query": "ab"}, {"query": "x" * 501}, {"query": "sql", "k": 50}, {}]
)
def test_bad_bodies_are_refused_before_any_voyage_call(body):
    class Boom:
        def search(self, *a, **k):
            raise AssertionError("must not search")

    assert client(Boom()).post("/api/search", json=body).status_code == 422


def test_without_retrieval_search_is_off():
    resp = client(None).post("/api/search", json={"query": "sql index"})
    assert resp.status_code == 503 and plain(resp.json()) == {"detail": SEARCH_OFF}


def test_it_is_capped_like_the_model_routes(kb_service):
    taken = [limits.SEARCH.acquire(blocking=False) for _ in range(2)]
    try:
        assert all(taken)
        assert (
            client(kb_service).post("/api/search", json={"query": "sql index"}).status_code == 503
        )
    finally:
        for _ in taken:
            limits.SEARCH.release()


class FailingEmbeddings:
    """Embeddings whose query call raises `exc` (its message quotes the query, as SDK text can)."""

    def __init__(self, exc):
        self.exc = exc

    def embed_query(self, text):
        raise self.exc


@pytest.mark.parametrize(
    ("exc", "status", "detail"),
    [
        (voyageai.error.RateLimitError(f"429 for {QUERY_SECRET}"), 429, SEARCH_LIMITED),
        (voyageai.error.VoyageError(f"bad request {QUERY_SECRET}"), 503, SEARCH_DOWN),
        (WindowFull(), 429, SEARCH_LIMITED),
    ],
)
def test_voyage_failures_give_fixed_messages_and_never_log_the_query(
    kb_service, caplog, monkeypatch, exc, status, detail
):
    monkeypatch.setattr(kb_service, "embeddings", FailingEmbeddings(exc))
    with caplog.at_level(logging.DEBUG):
        resp = client(kb_service).post("/api/search", json={"query": f"sql {QUERY_SECRET}"})
    assert (resp.status_code, plain(resp.json())) == (status, {"detail": detail})
    assert QUERY_SECRET not in caplog.text


def test_a_successful_search_logs_nothing_about_the_query(kb_service, caplog):
    with caplog.at_level(logging.DEBUG):
        client(kb_service).post("/api/search", json={"query": f"sql {QUERY_SECRET}"})
    assert QUERY_SECRET not in caplog.text


class Inner:
    def __init__(self):
        self.calls = 0

    def embed_query(self, text):
        self.calls += 1
        return [1.0]


def throttled(inner, rpm=1):
    sleeps = []
    emb = ThrottledEmbeddings(inner, rpm=rpm, tpm=10_000, clock=lambda: 100.0, sleep=sleeps.append)
    return emb, sleeps


def test_search_embedding_never_waits_when_the_window_is_full():
    inner = Inner()
    emb, sleeps = throttled(inner)
    assert emb.embed_query_now("sql index") == [1.0]
    with pytest.raises(WindowFull):
        emb.embed_query_now("sql index")
    assert inner.calls == 1 and sleeps == []


def test_search_embedding_does_not_retry_a_voyage_429():
    class Limited(Inner):
        def embed_query(self, text):
            self.calls += 1
            raise voyageai.error.RateLimitError("429")

    inner = Limited()
    emb, sleeps = throttled(inner, rpm=3)
    with pytest.raises(voyageai.error.RateLimitError):
        emb.embed_query_now("sql index")
    assert inner.calls == 1 and sleeps == []  # one request, no backoff


# --- opening retrieval per mode ---------------------------------------------------------------


def settings(mode: str, voyage: str | None) -> Settings:
    return Settings(
        _env_file=None, app_mode=mode, voyage_api_key=SecretStr(voyage) if voyage else None
    )


def test_demo_without_a_voyage_key_opens_nothing(monkeypatch):
    monkeypatch.setattr(main_module, "get_retrieval_service", lambda s: pytest.fail("opened"))
    assert open_retrieval(settings("demo", None)) is None
    assert open_retrieval(settings("demo", "   ")) is None


def test_demo_with_a_voyage_key_opens_retrieval_for_search(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(main_module, "get_retrieval_service", lambda s: sentinel)
    assert open_retrieval(settings("demo", "pa-test")) is sentinel


def test_demo_keeps_starting_when_retrieval_fails(monkeypatch, caplog):
    def broken(s):
        raise ConnectionError("qdrant at https://secret-host:6333 refused")

    monkeypatch.setattr(main_module, "get_retrieval_service", broken)
    with caplog.at_level(logging.ERROR):
        assert open_retrieval(settings("demo", "pa-test")) is None
    assert "ConnectionError" in caplog.text and "secret-host" not in caplog.text


@pytest.mark.parametrize("mode", ["local", "live"])
def test_local_and_live_still_fail_loudly(monkeypatch, mode):
    def broken(s):
        raise ConnectionError("down")

    monkeypatch.setattr(main_module, "get_retrieval_service", broken)
    with pytest.raises(ConnectionError):
        open_retrieval(settings(mode, None))

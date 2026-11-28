"""Cost protection for query embeddings: budget, cache, guard, off switch (no network)."""

import logging
import threading
from datetime import UTC, datetime

import pytest
from conftest import KB_DOCS, KeywordEmbeddings
from fastapi.testclient import TestClient
from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient

from gradpath.api import main as main_module
from gradpath.api import search as search_module
from gradpath.api.main import BUDGET_DAILY, BUDGET_TOTAL, create_app, open_retrieval
from gradpath.api.search import SEARCH_OFF
from gradpath.config import Settings
from gradpath.ingestion.embed import WindowFull
from gradpath.ingestion.index import rebuild_index
from gradpath.retrieval import get_retrieval_service
from gradpath.retrieval.budget import (
    BudgetSpent,
    DailyBudgetSpent,
    EmbedBudget,
    TotalBudgetSpent,
)
from gradpath.retrieval.guarded import GuardedEmbeddings
from gradpath.retrieval.query_cache import QueryCache


class Clock:
    def __init__(self, day: str = "2026-11-27") -> None:
        self.now = datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() + 3600

    def __call__(self) -> float:
        return self.now


class CountingEmbeddings(Embeddings):
    """Fake Voyage: counts the texts it was asked to embed."""

    def __init__(self) -> None:
        self.texts: list[str] = []
        self._inner = KeywordEmbeddings()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._inner.embed_query(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self.texts.append(text)
        return self._inner.embed_query(text)

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]


@pytest.fixture
def client() -> QdrantClient:
    return QdrantClient(":memory:")


def budget_for(client, daily=5, total=8, clock=None) -> EmbedBudget:
    return EmbedBudget(client, "usage", daily, total, clock=clock or Clock())


def guarded_for(client, daily=100, total=1000, max_entries=100, model="m"):
    inner = CountingEmbeddings()
    cache = QueryCache(client, "qc", model, max_entries)
    budget = budget_for(client, daily, total)
    return GuardedEmbeddings(inner, cache, budget), inner, cache, budget


# --- budget -----------------------------------------------------------------------------------


def test_budget_persists_across_a_restart(client):
    budget_for(client).spend(3)
    again = budget_for(client)  # a new process on the same Qdrant
    again.spend(2)
    with pytest.raises(BudgetSpent) as err:
        again.spend(1)
    assert err.value.which == "daily"


def test_total_cap_refuses_with_total(client):
    clock = Clock()
    budget = budget_for(client, daily=5, total=8, clock=clock)
    budget.spend(5)
    clock.now += 86400  # next UTC day: the daily count resets
    budget.spend(3)
    with pytest.raises(TotalBudgetSpent) as err:
        budget.spend(1)
    assert err.value.which == "total"


def test_new_utc_day_resets_daily_not_total(client):
    clock = Clock()
    budget = budget_for(client, daily=2, total=3, clock=clock)
    budget.spend(2)
    with pytest.raises(DailyBudgetSpent):
        budget.spend(1)
    clock.now += 86400
    budget.spend(1)  # fresh day
    with pytest.raises(TotalBudgetSpent):
        budget.spend(1)


def test_failed_upsert_rolls_back_and_raises(client, monkeypatch):
    budget = budget_for(client, daily=2, total=10)
    budget.spend(1)

    def boom(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr(client, "upsert", boom)
    with pytest.raises(ConnectionError):
        budget.spend(1)
    monkeypatch.undo()
    budget.spend(1)  # the failed spend was not counted
    with pytest.raises(BudgetSpent):
        budget.spend(1)


def test_threads_never_overspend(client):
    budget = budget_for(client, daily=50, total=1000)
    granted = []

    def worker():
        for _ in range(40):
            try:
                budget.spend(1)
                granted.append(1)
            except BudgetSpent:
                pass

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(granted) == 50


# --- cache ------------------------------------------------------------------------------------


def test_repeated_question_is_free_and_spellings_share_an_entry(client):
    g, inner, cache, budget = guarded_for(client, daily=3)
    first = g.embed_query("  What is REST? ")
    again = g.embed_query("what is rest?")
    assert again == first
    assert inner.texts == ["  What is REST? "]  # original text sent, once
    assert client.count(cache.collection).count == 1
    budget.spend(2)  # only 1 of 3 was spent by the two calls above
    with pytest.raises(BudgetSpent):
        budget.spend(1)


def test_cache_stores_no_query_text(client):
    g, _, cache, _ = guarded_for(client)
    g.embed_query("zebra-unique-query-text")
    points, _ = client.scroll(cache.collection, limit=10, with_payload=True, with_vectors=False)
    assert len(points) == 1
    assert points[0].payload == {"model": "m"}
    assert "zebra" not in repr(points[0])


def test_a_different_model_misses(client):
    g1, _, _, _ = guarded_for(client, model="m1")
    g2, inner2, _, _ = guarded_for(client, model="m2")
    g1.embed_query("sql index")
    g2.embed_query("sql index")
    assert inner2.texts == ["sql index"]


def test_max_entries_stops_inserts(client):
    g, inner, cache, _ = guarded_for(client, max_entries=1)
    g.embed_query("sql index")
    g.embed_query("http status")  # cache full: not stored
    g.embed_query("http status")
    assert inner.texts == ["sql index", "http status", "http status"]
    assert client.count(cache.collection).count == 1


def test_a_broken_client_degrades_to_uncached(caplog):
    class Broken:
        def __getattr__(self, name):
            def fail(*a, **k):
                raise ConnectionError("secret-host")

            return fail

    cache = QueryCache(Broken(), "qc", "m", 10)
    with caplog.at_level(logging.WARNING):
        assert cache.get_many(["zebra-unique-query-text"]) == [None]
        cache.put_many(["zebra-unique-query-text"], [[1.0, 0.0]])
    assert "zebra" not in caplog.text and "secret-host" not in caplog.text
    assert "ConnectionError" in caplog.text


# --- guarded ----------------------------------------------------------------------------------


def test_mixed_batch_spends_only_the_misses_in_order(client):
    g, inner, _, budget = guarded_for(client, daily=10)
    g.embed_query("sql index")  # 1 spent, cached
    out = g.embed_queries(["http status", "SQL  index", "git branch"])
    kw = KeywordEmbeddings()
    expected = [kw.embed_query(q) for q in ["http status", "sql index", "git branch"]]
    for got, want in zip(out, expected, strict=True):
        assert got == pytest.approx(want, abs=1e-6)  # cached vectors come back as float32
    assert inner.texts == ["sql index", "http status", "git branch"]
    budget.spend(7)  # 1 + 2 = 3 spent so far
    with pytest.raises(DailyBudgetSpent):
        budget.spend(1)


def test_budget_spent_raises_before_voyage(client):
    g, inner, _, _ = guarded_for(client, daily=0)
    with pytest.raises(DailyBudgetSpent):
        g.embed_queries(["sql index"])
    with pytest.raises(DailyBudgetSpent):
        g.embed_query_now("sql index")
    assert inner.texts == []


def test_a_failed_voyage_call_gives_the_budget_back(client):
    """A refused request (a full free-tier window, Voyage's 429) embeds nothing, so it must not
    burn the budget: otherwise refused requests could spend the day's searches."""
    g, inner, _, _ = guarded_for(client, daily=2)

    def refused(_text):
        raise WindowFull

    inner.embed_query = refused
    for _ in range(5):
        with pytest.raises(WindowFull):
            g.embed_query_now("sql index")
    again = budget_for(client, daily=2)  # the refunds were saved, not only kept in memory
    again.spend(2)
    with pytest.raises(DailyBudgetSpent):
        again.spend(1)


def test_failures_that_may_have_been_paid_keep_the_spend(client):
    """A timeout may come after Voyage did the work, and a batch may fail after paying for its
    first requests: neither is refunded (the safe side)."""
    g, inner, _, _ = guarded_for(client, daily=3)

    def timeout(_text):
        raise TimeoutError

    inner.embed_query = timeout
    with pytest.raises(TimeoutError):
        g.embed_query("sql index")

    def batch_refused(_texts):
        raise WindowFull

    inner.embed_queries = batch_refused
    with pytest.raises(WindowFull):
        g.embed_queries(["http status", "git branch"])
    again = budget_for(client, daily=3)  # 1 + 2 kept: nothing left today
    with pytest.raises(DailyBudgetSpent):
        again.spend(1)


def test_a_refund_that_cannot_be_saved_keeps_the_higher_count(client, monkeypatch):
    budget = budget_for(client, daily=3)
    budget.spend(2)

    def broken(*_args, **_kwargs):
        raise ConnectionError("qdrant down")

    monkeypatch.setattr(client, "upsert", broken)
    budget.refund(2)  # never raises: the refund is best effort
    monkeypatch.undo()
    budget.spend(1)
    with pytest.raises(DailyBudgetSpent):
        budget.spend(1)


def test_documents_are_refused(client):
    g, *_ = guarded_for(client)
    with pytest.raises(NotImplementedError):
        g.embed_documents(["x"])


# --- wiring and API ---------------------------------------------------------------------------


@pytest.mark.parametrize(("mode", "guarded"), [("local", False), ("demo", True), ("live", True)])
def test_only_the_deployed_server_guards_embeddings(monkeypatch, mode, guarded):
    client = QdrantClient(":memory:")
    rebuild_index(client, "gradpath_kb", KB_DOCS, KeywordEmbeddings())
    plain = CountingEmbeddings()
    monkeypatch.setattr("gradpath.ingestion.index.get_qdrant_client", lambda s: client)
    monkeypatch.setattr("gradpath.ingestion.embed.build_query_embeddings", lambda s: plain)
    url = None if mode == "local" else "https://qdrant.example.test"  # never contacted (patched)
    service = get_retrieval_service(Settings(_env_file=None, app_mode=mode, qdrant_url=url))
    assert isinstance(service.embeddings, GuardedEmbeddings) is guarded
    assert (service.embeddings is plain) is (not guarded)


@pytest.mark.parametrize("mode", ["demo", "live"])
def test_deployed_modes_refuse_a_local_qdrant_folder(mode):
    """The budget and cache need a Qdrant server: the local folder client isn't thread-safe, and
    the counters must not land in the index folder."""
    with pytest.raises(RuntimeError, match="QDRANT_URL"):
        get_retrieval_service(Settings(_env_file=None, app_mode=mode, qdrant_url=None))


def api(retrieval, monkeypatch, **settings) -> TestClient:
    s = Settings(_env_file=None, app_mode="demo", **settings)
    monkeypatch.setattr(search_module, "get_settings", lambda: s)
    monkeypatch.setattr(main_module, "get_settings", lambda: s)
    app = create_app(use_lifespan=False)
    app.state.retrieval = retrieval
    return TestClient(app)


def test_search_off_switch(kb_service, monkeypatch):
    c = api(kb_service, monkeypatch, search_enabled=False)
    resp = c.post("/api/search", json={"query": "sql index"})
    assert resp.status_code == 503
    assert resp.json() == {"detail": SEARCH_OFF, "code": "search_off"}
    assert c.get("/api/health").json()["search_enabled"] is False


def test_demo_does_not_open_retrieval_when_search_is_off():
    s = Settings(_env_file=None, app_mode="demo", search_enabled=False, voyage_api_key="k")
    assert open_retrieval(s) is None


@pytest.mark.parametrize(
    ("exc", "detail", "code"),
    [
        (DailyBudgetSpent, BUDGET_DAILY, "search_budget_daily"),
        (TotalBudgetSpent, BUDGET_TOTAL, "search_budget_spent"),
    ],
)
def test_budget_spent_during_search_is_a_503(kb_service, monkeypatch, exc, detail, code):
    class Spent:
        def embed_query(self, text):
            raise exc

    kb_service.embeddings = Spent()
    resp = api(kb_service, monkeypatch).post("/api/search", json={"query": "sql index"})
    assert resp.status_code == 503
    assert resp.json() == {"detail": detail, "code": code}

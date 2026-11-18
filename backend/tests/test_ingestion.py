"""Ingestion tests: no network, no Voyage. HTTP is `httpx.MockTransport`, vectors are fakes."""

import json
import threading
from pathlib import Path

import httpx
import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings
from qdrant_client import QdrantClient
from voyageai.error import RateLimitError

from gradpath.config import Settings
from gradpath.ingestion.chunk import chunk_page, read_processed, write_processed
from gradpath.ingestion.clean import clean_html, clean_markdown
from gradpath.ingestion.embed import (
    CachedEmbeddings,
    ThrottledEmbeddings,
    build_embeddings,
    build_query_embeddings,
)
from gradpath.ingestion.fetch import USER_AGENT, Politeness, fetch_source, load_manual
from gradpath.ingestion.index import rebuild_index
from gradpath.ingestion.manifest import SourceEntry, load_manifest, select_ingestible

HEADER = (
    "document_id,title,source_url,source_type,collection,topic,license_or_usage_notes,"
    "license_verified,status,added_by,fetch_urls\n"
)


def entry(**kw) -> SourceEntry:
    base = dict(
        document_id="doc-a",
        title="Doc A",
        source_url="https://example.org/a",
        source_type="official docs",
        collection="technical_fundamentals",
        topic="t",
        license_or_usage_notes="MIT",
        status="approved",
        fetch_urls=["https://example.org/a"],
    )
    return SourceEntry(**{**base, **kw})


# --- manifest ---------------------------------------------------------------------------------


def test_manifest_parsing(tmp_path: Path):
    csv_path = tmp_path / "m.csv"
    csv_path.write_text(
        HEADER
        + "a,A,https://x/a,docs,c,t,n,yes,approved,claude,https://x/a|https://x/b.md\n"
        + "b,B,https://x/b,docs,c,t,n,yes,link_only,claude,\n"
        + "c,C,https://x/c,docs,c,t,n,yes,approved,claude,manual\n"
        + "d,D,https://x/d,docs,c,t,n,yes,approved,claude,\n"
        + "e,E,https://x/e,docs,c,t,n,yes,rejected,claude,https://x/e\n",
        encoding="utf-8",
    )
    entries = load_manifest(csv_path)
    assert entries[0].fetch_urls == ["https://x/a", "https://x/b.md"]
    assert entries[2].manual and entries[2].fetch_urls == []
    assert entries[3].fetch_urls == [] and not entries[3].manual
    ids = [e.document_id for e in select_ingestible(entries)]
    assert ids == ["a", "c", "d"]  # link_only and rejected are never ingested
    assert [e.document_id for e in select_ingestible(entries, ["c"])] == ["c"]


# --- fetch ------------------------------------------------------------------------------------


def make_site(robots: str | None = None, status: int = 200):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(404 if robots is None else 200, text=robots or "")
        return httpx.Response(status, text="<html><body><main>hello</main></body></html>")

    client = httpx.Client(
        transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT}
    )
    return client, seen


def polite() -> Politeness:
    return Politeness(sleep=lambda s: None)


def test_fetch_caches_and_logs(tmp_path: Path):
    client, seen = make_site()
    e = entry()
    pages = fetch_source(e, tmp_path, client, politeness=polite())
    assert len(pages) == 1 and pages[0].path.read_text(encoding="utf-8").startswith("<html>")
    log = json.loads((tmp_path / "doc-a" / "fetch_log.json").read_text())
    assert log[0]["url"] == e.fetch_urls[0] and log[0]["status"] == 200
    assert len(log[0]["sha256"]) == 64 and log[0]["retrieved_at"]
    n = len(seen)
    fetch_source(e, tmp_path, client, politeness=polite())
    assert len(seen) == n  # cache hit: no new requests
    fetch_source(e, tmp_path, client, refresh=True, politeness=polite())
    assert len(seen) > n


def test_fetch_sends_user_agent(tmp_path: Path):
    client, seen = make_site()
    fetch_source(entry(), tmp_path, client, politeness=polite())
    assert seen and all(r.headers["user-agent"] == USER_AGENT for r in seen)


def test_fetch_respects_robots(tmp_path: Path):
    client, seen = make_site(robots="User-agent: *\nDisallow: /a\n")
    assert fetch_source(entry(), tmp_path, client, politeness=polite()) == []
    assert [r.url.path for r in seen] == ["/robots.txt"]


def test_fetch_skips_non_200(tmp_path: Path):
    client, _ = make_site(status=403)
    assert fetch_source(entry(), tmp_path, client, politeness=polite()) == []


def test_politeness_spaces_requests_to_one_host():
    now = [0.0]
    slept: list[float] = []

    def sleep(s: float) -> None:
        slept.append(s)
        now[0] += s

    p = Politeness(sleep=sleep, clock=lambda: now[0])
    p.wait("h")
    p.wait("h")
    p.wait("other")
    assert slept == [1.0]


def test_load_manual(tmp_path: Path):
    e = entry(fetch_urls=[], manual=True)
    assert load_manual(e, tmp_path) == []
    (tmp_path / "doc-a.html").write_text("<p>x</p>")
    pages = load_manual(e, tmp_path)
    assert len(pages) == 1 and pages[0].url == e.source_url and pages[0].kind == "html"


# --- clean ------------------------------------------------------------------------------------

PAGE = """<html><head><title>My Page</title><script>evil()</script></head><body>
<nav>Home | Docs</nav><header>Site header</header>
<div class="sidebar">Sidebar links</div>
<main><h1>Title</h1><p>Intro <b>text</b>.</p><h2>Part</h2>
<pre>def f():
    return 1
</pre><ul><li>one</li><li>two</li></ul>
<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>
<div class="breadcrumb">Home > Docs</div></main><footer>Copyright</footer></body></html>"""


def test_clean_html():
    title, text = clean_html(PAGE)
    assert title == "My Page"
    for gone in ("Home | Docs", "Site header", "Sidebar", "Copyright", "evil", "Home > Docs"):
        assert gone not in text
    assert "# Title" in text and "## Part" in text
    assert "```\ndef f():\n    return 1\n```" in text
    assert "- one\n\n- two" in text or "- one\n- two" in text
    assert "A | B" in text and "1 | 2" in text


def test_clean_html_falls_back_to_body():
    _, text = clean_html("<body><p>plain body</p></body>")
    assert "plain body" in text


def test_clean_markdown():
    md = (
        "---\ntitle: x\n---\n<!-- note -->\nimport Foo from './foo'\nexport const a = 1\n"
        "# Real Title\n\nBody text.\n\n```py\nimport os\n```\n\n\n\nEnd\n"
    )
    title, text = clean_markdown(md)
    assert title == "Real Title"
    assert "title: x" not in text and "note" not in text
    assert "Foo" not in text and "export const" not in text
    assert "import os" in text  # inside a code fence it stays
    assert "\n\n\n" not in text


# --- chunk ------------------------------------------------------------------------------------

LONG = (
    "# Top\n\n"
    + "\n\n".join(f"## Sec {i}\n\n" + ("word " * 80) for i in range(3))
    + "\n\n## Tiny\n\nx"
)


def make_chunks(**kw):
    return chunk_page(
        entry(), LONG, 0, "https://example.org/a", "2026-01-01T00:00:00+00:00", 300, 30
    )


def test_chunk_ids_stable_and_metadata_complete():
    a, b = make_chunks(), make_chunks()
    assert [d.metadata["chunk_id"] for d in a] == [d.metadata["chunk_id"] for d in b]
    ids = [d.metadata["chunk_id"] for d in a]
    assert len(set(ids)) == len(ids) > 3 and ids[0] == "doc-a:0:0"
    keys = {
        "document_id", "chunk_id", "title", "section", "source_url", "source_type",
        "collection", "topic", "license_or_usage_notes", "retrieved_at",
    }  # fmt: skip
    assert all(set(d.metadata) == keys for d in a)
    assert any(d.metadata["section"] == "Top > Sec 1" for d in a)
    assert all(len(d.page_content) >= 50 for d in a)  # the tiny section is dropped


def test_processed_jsonl_roundtrip(tmp_path: Path):
    docs = make_chunks()
    write_processed(tmp_path / "p" / "doc-a.jsonl", docs)
    assert read_processed(tmp_path / "p" / "doc-a.jsonl") == docs


# --- embed ------------------------------------------------------------------------------------


class FakeInner(Embeddings):
    def __init__(self, fail_times: int = 0):
        self.calls: list[list[str]] = []
        self.fail_times = fail_times

    def embed_documents(self, texts):
        if self.fail_times:
            self.fail_times -= 1
            raise RateLimitError("slow down")
        self.calls.append(texts)
        return [[float(len(t))] for t in texts]

    def embed_query(self, text):
        return [1.0]


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s

    def clock(self) -> float:
        return self.now


def throttled(inner, rpm=3, tpm=1000, **kw):
    t = FakeTime()
    return ThrottledEmbeddings(inner, rpm, tpm, sleep=t.sleep, clock=t.clock, **kw), t


def test_throttle_batches_under_budget_and_keeps_order():
    inner = FakeInner()
    emb, _ = throttled(inner, rpm=100, tpm=1000)  # budget 800 tokens = 3200 chars
    texts = ["a" * 1000, "b" * 1000, "c" * 1000, "d" * 1000]
    vectors = emb.embed_documents(texts)
    assert [len(c) for c in inner.calls] == [3, 1]
    assert vectors == [[1000.0]] * 4


def test_throttle_respects_rpm():
    inner = FakeInner()
    emb, t = throttled(inner, rpm=2, tpm=10_000)
    emb.embed_documents(["a" * 100])
    emb.embed_documents(["b" * 100])
    assert t.sleeps == []
    emb.embed_documents(["c" * 100])  # third request inside one minute must wait
    assert t.sleeps and t.now >= 60


def test_throttle_respects_tpm():
    inner = FakeInner()
    emb, t = throttled(inner, rpm=100, tpm=1000)
    emb.embed_documents(["a" * 3000])  # 750 tokens
    emb.embed_documents(["b" * 3000])  # would be 1500 in the window
    assert t.now >= 60


def test_throttle_retries_rate_limit_then_gives_up():
    inner = FakeInner(fail_times=2)
    emb, t = throttled(inner, rpm=100, tpm=10_000)
    assert emb.embed_documents(["abc"]) == [[3.0]]
    assert t.sleeps[:2] == [5.0, 10.0]  # exponential backoff
    emb2, _ = throttled(FakeInner(fail_times=99), rpm=100, tpm=10_000)
    with pytest.raises(RateLimitError):
        emb2.embed_documents(["abc"])


def test_build_embeddings_needs_key():
    with pytest.raises(RuntimeError, match="VOYAGE_API_KEY"):
        build_embeddings(Settings(_env_file=None, voyage_api_key=None), Path("."))


# --- index ------------------------------------------------------------------------------------


def test_rebuild_index_is_idempotent():
    client = QdrantClient(":memory:")
    docs = make_chunks()
    emb = DeterministicFakeEmbedding(size=8)
    assert rebuild_index(client, "kb", docs, emb) == len(docs)
    assert client.count("kb").count == len(docs)
    rebuild_index(client, "kb", docs, emb)
    assert client.count("kb").count == len(docs)  # rebuilt, not doubled
    point = client.scroll("kb", limit=1, with_payload=True)[0][0]
    assert point.payload["metadata"]["document_id"] == "doc-a"


class Boom(Embeddings):
    def embed_documents(self, texts):
        raise RuntimeError("embedding failed")

    def embed_query(self, text):
        raise RuntimeError("embedding failed")


def test_rebuild_failure_keeps_existing_collection():
    client = QdrantClient(":memory:")
    docs = make_chunks()
    rebuild_index(client, "kb", docs, DeterministicFakeEmbedding(size=8))
    with pytest.raises(RuntimeError):
        rebuild_index(client, "kb", docs[:2], Boom())
    assert client.count("kb").count == len(docs)


def test_rebuilt_collection_is_searchable_via_vector_store():
    from langchain_qdrant import QdrantVectorStore

    client = QdrantClient(":memory:")
    docs = make_chunks()
    emb = DeterministicFakeEmbedding(size=8)
    rebuild_index(client, "kb", docs, emb)
    store = QdrantVectorStore(client=client, collection_name="kb", embedding=emb)
    hit = store.similarity_search(docs[0].page_content, k=1)[0]
    assert hit.page_content == docs[0].page_content
    assert hit.metadata["chunk_id"] == "doc-a:0:0" and hit.metadata["document_id"] == "doc-a"


def test_cached_embeddings_skip_inner_and_persist(tmp_path: Path):
    path = tmp_path / "c" / "m.jsonl"
    inner = FakeInner()
    cache = CachedEmbeddings(inner, "m", path)
    assert cache.embed_documents(["aa", "bbb"]) == [[2.0], [3.0]]
    assert cache.embed_documents(["bbb", "cccc", "aa"]) == [[3.0], [4.0], [2.0]]
    assert inner.calls == [["aa", "bbb"], ["cccc"]]
    assert (cache.hits, cache.misses) == (2, 3)
    again = FakeInner()
    fresh = CachedEmbeddings(again, "m", path)  # a new instance reads the file
    assert fresh.embed_documents(["aa", "cccc"]) == [[2.0], [4.0]]
    assert again.calls == []
    assert CachedEmbeddings(again, "other", path).embed_documents(["aa"]) == [[2.0]]
    assert again.calls == [["aa"]]  # the key includes the model


def test_embed_query_is_throttled():
    emb, t = throttled(FakeInner(), rpm=1, tpm=10_000)
    emb.embed_query("q1")
    assert t.sleeps == []
    emb.embed_query("q2")
    assert t.now >= 60


def test_cache_keeps_vectors_embedded_before_a_failure(tmp_path):
    """A failure part-way through must not lose groups that were already embedded (and paid for)."""
    from gradpath.ingestion.embed import CACHE_FLUSH_EVERY, CachedEmbeddings

    class FailsOnSecondCall(DeterministicFakeEmbedding):
        calls: int = 0

        def embed_documents(self, texts):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("network down")
            return super().embed_documents(texts)

    texts = [f"chunk {i}" for i in range(CACHE_FLUSH_EVERY + 5)]
    path = tmp_path / "cache.jsonl"
    cached = CachedEmbeddings(FailsOnSecondCall(size=8), "m", path)
    with pytest.raises(RuntimeError):
        cached.embed_documents(texts)
    reloaded = CachedEmbeddings(DeterministicFakeEmbedding(size=8), "m", path)
    reloaded.embed_documents(texts)
    assert reloaded.hits == CACHE_FLUSH_EVERY


def test_heading_permalink_anchors_are_removed():
    from gradpath.ingestion.clean import clean_html

    html = (
        '<main><h2>9.4. Random Remarks<a class="headerlink" href="#r">¶</a></h2>'
        '<h3>11.1. Introduction <a href="#i">#</a></h3><p>See <a href="/x">the docs</a>.</p></main>'
    )
    _, text = clean_html(html)
    assert "## 9.4. Random Remarks" in text and "¶" not in text
    assert "### 11.1. Introduction" in text and "Introduction #" not in text
    assert "the docs" in text  # ordinary links keep their text


def test_markdown_heading_ids_are_removed():
    from gradpath.ingestion.clean import clean_markdown

    md = "## Pick a language {#pick-programming-language}\nBody {#not-a-heading}"
    _, text = clean_markdown(md)
    assert "## Pick a language" in text and "{#pick" not in text
    assert "Body {#not-a-heading}" in text  # only headings are touched


# --- review fixes -----------------------------------------------------------------------------


def test_throttle_is_thread_safe_and_stays_under_rpm():
    lock = threading.Lock()
    now = [0.0]
    starts: list[float] = []

    class Inner(FakeInner):
        def embed_query(self, text):
            with lock:
                starts.append(now[0])
            return [1.0]

    def sleep(s: float) -> None:
        with lock:
            now[0] += s

    def clock() -> float:
        with lock:
            return now[0]

    emb = ThrottledEmbeddings(Inner(), rpm=3, tpm=100_000, sleep=sleep, clock=clock)
    errors: list[Exception] = []

    def work():
        try:
            for _ in range(5):
                emb.embed_query("hello")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=work) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(starts) == 30
    # No 60 s window ever holds more than rpm requests.
    for i, t0 in enumerate(starts):
        assert sum(1 for t in starts if t0 <= t < t0 + 60) <= 3, i


def test_cache_skips_truncated_line(tmp_path: Path, caplog):
    path = tmp_path / "c.jsonl"
    path.write_text('{"key": "k1", "vector": [1.0]}\n{"key": "k2", "vec', encoding="utf-8")
    cache = CachedEmbeddings(FakeInner(), "m", path)
    assert list(cache._vectors) == ["k1"]
    assert "skipped 1" in caplog.text


def test_build_query_embeddings_is_uncached_and_needs_key():
    with pytest.raises(RuntimeError, match="VOYAGE_API_KEY"):
        build_query_embeddings(Settings(_env_file=None, voyage_api_key=None))
    emb = build_query_embeddings(Settings(_env_file=None, voyage_api_key="k"))
    assert isinstance(emb, ThrottledEmbeddings)


def test_fetch_reordered_urls_reuse_cache_by_url(tmp_path: Path):
    client, _ = make_site()
    a, b = "https://example.org/a", "https://example.org/b"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200, text=f"<html><body><main>page {request.url.path}</main></body></html>"
        )

    real = httpx.Client(transport=httpx.MockTransport(handler))
    fetch_source(entry(fetch_urls=[a, b]), tmp_path, real, politeness=polite())

    def fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    dead = httpx.Client(transport=httpx.MockTransport(fail))
    pages = fetch_source(entry(fetch_urls=[b, a]), tmp_path, dead, politeness=polite())
    assert [(p.index, p.url) for p in pages] == [(0, b), (1, a)]
    assert "page /b" in pages[0].path.read_text(encoding="utf-8")
    assert "page /a" in pages[1].path.read_text(encoding="utf-8")


def test_fetch_redownloads_when_cached_file_changed(tmp_path: Path):
    client, seen = make_site()
    pages = fetch_source(entry(), tmp_path, client, politeness=polite())
    pages[0].path.write_text("tampered", encoding="utf-8")
    n = len(seen)
    pages = fetch_source(entry(), tmp_path, client, politeness=polite())
    assert len(seen) > n and pages[0].path.read_text(encoding="utf-8").startswith("<html>")


def test_robots_404_allows_and_5xx_disallows(tmp_path: Path):
    client, seen = make_site()  # robots.txt 404
    assert len(fetch_source(entry(), tmp_path / "ok", client, politeness=polite())) == 1

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    down = httpx.Client(transport=httpx.MockTransport(handler))
    pol = polite()
    assert fetch_source(entry(), tmp_path / "down", down, politeness=pol) == []
    assert pol.allowed("https://example.org/zzz", down) is False  # cached for the host


def test_robots_network_error_disallows():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert polite().allowed("https://example.org/a", client) is False


def test_manifest_rejects_path_traversal_ids():
    with pytest.raises(ValueError, match="document_id"):
        entry(document_id="../evil")
    with pytest.raises(ValueError, match="document_id"):
        entry(document_id="a/b")
    assert entry(document_id="fund-mdn.http_2").document_id == "fund-mdn.http_2"

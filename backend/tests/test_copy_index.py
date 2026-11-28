"""Copying the index to the deployed Qdrant without re-embedding (T-020 step 1)."""

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from gradpath.config import Settings
from gradpath.ingestion import copy_index as copy_mod
from gradpath.ingestion.copy_index import copy_index, read_points, target_client
from gradpath.ingestion.index import rebuild_index


def docs(n: int = 300) -> list[Document]:
    # More than one scroll page (256) and several upsert batches (64).
    return [
        Document(page_content=f"chunk {i}", metadata={"chunk_id": f"doc:0:{i}", "title": "T"})
        for i in range(n)
    ]


@pytest.fixture
def source() -> QdrantClient:
    client = QdrantClient(":memory:")
    rebuild_index(client, "kb", docs(), DeterministicFakeEmbedding(size=8))
    return client


def test_copy_matches_the_source_point_for_point(source):
    target = QdrantClient(":memory:")
    assert copy_index(source, target, "kb") == 300
    src = {p.id: p for p in read_points(source, "kb")}
    dst = {p.id: p for p in read_points(target, "kb")}
    assert src.keys() == dst.keys()
    for pid, p in src.items():
        assert dst[pid].payload == p.payload
        assert dst[pid].vector == pytest.approx(p.vector)


def test_the_target_is_published_behind_the_alias_like_ingest(source):
    target = QdrantClient(":memory:")
    copy_index(source, target, "kb")
    aliases = {a.alias_name: a.collection_name for a in target.get_aliases().aliases}
    assert "kb" in aliases and aliases["kb"].startswith("kb_")


def test_copying_again_replaces_the_index_and_leaves_one_collection(source):
    target = QdrantClient(":memory:")
    copy_index(source, target, "kb")
    copy_index(source, target, "kb")
    names = [c.name for c in target.get_collections().collections]
    assert len(names) == 1 and len(read_points(target, "kb")) == 300


def test_search_gives_the_same_hits_on_both_sides(source):
    target = QdrantClient(":memory:")
    copy_index(source, target, "kb")
    query = DeterministicFakeEmbedding(size=8).embed_query("chunk 7")
    a = source.query_points("kb", query=query, limit=5).points
    b = target.query_points("kb", query=query, limit=5).points
    assert [p.id for p in a] == [p.id for p in b]


def test_an_empty_source_is_refused():
    empty = QdrantClient(":memory:")
    empty.create_collection("kb", vectors_config=VectorParams(size=8, distance=Distance.COSINE))
    with pytest.raises(ValueError, match="empty"):
        copy_index(empty, QdrantClient(":memory:"), "kb")


def test_a_copy_that_does_not_match_is_never_reported_as_done(source, monkeypatch):
    target = QdrantClient(":memory:")
    real = copy_mod.read_points

    def drop_one_from_target(client, collection):
        points = real(client, collection)
        return points[:-1] if client is target else points

    monkeypatch.setattr(copy_mod, "read_points", drop_one_from_target)
    with pytest.raises(RuntimeError, match="mismatch"):
        copy_index(source, target, "kb")


def test_the_target_must_be_set_and_https():
    with pytest.raises(SystemExit, match="QDRANT_CLOUD_URL"):
        target_client(Settings(_env_file=None, qdrant_cloud_url=None))
    with pytest.raises(SystemExit, match="https"):
        target_client(Settings(_env_file=None, qdrant_cloud_url="http://example.com:6333"))

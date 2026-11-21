"""The index summary behind "Sources as of" (T-018 step 3): no network, temp files only."""

import argparse
import json
import logging
from datetime import date

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from gradpath.api.main import create_app
from gradpath.config import REPO_ROOT, Settings
from gradpath.ingestion import ingest
from gradpath.ingestion.chunk import write_processed
from gradpath.ingestion.index_info import IndexInfo, read_index_info, summarize, write_index_info

TODAY = date(2026, 11, 20)


def chunk(doc: str, stamp: str | None) -> Document:
    meta = {"document_id": doc, "chunk_id": f"{doc}:0:0"}
    if stamp is not None:
        meta["retrieved_at"] = stamp
    return Document(page_content="text " * 20, metadata=meta)


def test_as_of_is_the_oldest_fetch_and_counts_are_right():
    info = summarize(
        [
            chunk("pg", "2026-11-19T10:00:00+00:00"),
            chunk("pg", "2026-11-17T23:30:00+00:00"),
            chunk("mdn", "2026-11-18T08:00:00"),  # no zone: read as UTC
            chunk("git", None),  # no date: counted, not dated
        ],
        written_at=TODAY,
    )
    assert info.sources_as_of == date(2026, 11, 17)
    assert info.sources_newest == date(2026, 11, 19)
    assert (info.documents, info.chunks, info.written_at) == (3, 4, TODAY)


def test_a_zone_offset_is_converted_to_utc_first():
    info = summarize([chunk("pg", "2026-11-18T01:00:00+05:00")], written_at=TODAY)
    assert info.sources_as_of == date(2026, 11, 17)


def test_manual_sources_are_counted_but_never_set_the_date():
    info = summarize(
        [chunk("saved-by-hand", "2025-01-01T00:00:00+00:00"), chunk("pg", "2026-11-19T00:00:00")],
        written_at=TODAY,
        undated={"saved-by-hand"},
    )
    assert info.sources_as_of == date(2026, 11, 19) and info.documents == 2


def test_no_dates_at_all_is_an_error():
    with pytest.raises(ValueError):
        summarize([chunk("pg", None)])


def test_write_then_read_round_trips(tmp_path):
    info = summarize([chunk("pg", "2026-11-18T00:00:00+00:00")], written_at=TODAY)
    path = tmp_path / "kb" / "index_info.json"
    write_index_info(path, info)
    assert read_index_info(path) == info
    assert not list(path.parent.glob("*.tmp"))


@pytest.mark.parametrize(
    "content",
    [
        "{broken",
        json.dumps({"written_at": "2026-11-20"}),
        json.dumps({"written_at": "2026-11-20", "sources_as_of": "2026-11-19",
                    "sources_newest": "2026-11-18", "documents": 1, "chunks": 1}),
    ],
)  # fmt: skip
def test_a_bad_file_reads_as_none(tmp_path, caplog, content):
    path = tmp_path / "index_info.json"
    path.write_text(content, encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        assert read_index_info(path) is None
    assert "2026" not in caplog.text  # the error type only, never the content


def test_a_missing_file_reads_as_none(tmp_path):
    assert read_index_info(tmp_path / "nope.json") is None


def test_info_only_rewrites_the_file_without_fetching_or_embedding(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    (kb / "processed").mkdir(parents=True)
    (kb / "source_manifest.csv").write_text(
        (REPO_ROOT / "knowledge_base" / "source_manifest.csv").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    first_id = (
        (kb / "source_manifest.csv").read_text(encoding="utf-8").splitlines()[1].split(",")[0]
    )
    write_processed(
        kb / "processed" / f"{first_id}.jsonl", [chunk(first_id, "2026-11-18T00:00:00+00:00")]
    )

    def must_not_run(*_, **__):
        raise AssertionError("--info-only must not fetch, embed or open Qdrant")

    for name in ["make_client", "build_embeddings", "get_qdrant_client", "rebuild_index"]:
        monkeypatch.setattr(ingest, name, must_not_run)
    out = tmp_path / "index_info.json"
    settings = Settings(_env_file=None, index_info_path=str(out))
    args = argparse.Namespace(info_only=True, only=None, refresh=False, dry_run=False)
    ingest.run(args, settings, kb)
    info = IndexInfo.model_validate_json(out.read_text(encoding="utf-8"))
    assert info.sources_as_of == date(2026, 11, 18) and info.chunks == 1


def test_the_committed_file_is_valid():
    info = read_index_info(REPO_ROOT / "knowledge_base" / "index_info.json")
    assert info is not None and info.chunks > 0


def test_health_returns_the_dates_or_null():
    app = create_app(use_lifespan=False)
    app.state.index_info = summarize([chunk("pg", "2026-11-18T00:00:00+00:00")], written_at=TODAY)
    body = TestClient(app).get("/api/health").json()
    assert body["sources_as_of"] == "2026-11-18" and body["sources_newest"] == "2026-11-18"
    app.state.index_info = None
    body = TestClient(app).get("/api/health").json()
    assert body["sources_as_of"] is None and body["status"] == "ok"


def full_run_setup(tmp_path, monkeypatch, *, rebuild):
    """A one-document kb and a full (non --info-only) run with fetching and Voyage stubbed."""
    kb = tmp_path / "kb"
    (kb / "processed").mkdir(parents=True)
    manifest = (REPO_ROOT / "knowledge_base" / "source_manifest.csv").read_text(encoding="utf-8")
    (kb / "source_manifest.csv").write_text(manifest, encoding="utf-8")
    doc_id = manifest.splitlines()[1].split(",")[0]
    write_processed(kb / "processed" / f"{doc_id}.jsonl", [chunk(doc_id, "2026-11-18T00:00:00Z")])

    class Client:
        def close(self):
            pass

    class Embeddings:
        hits = misses = 0

    monkeypatch.setattr(ingest, "make_client", Client)
    monkeypatch.setattr(ingest, "process_entry", lambda *a: (0, []))
    monkeypatch.setattr(ingest, "build_embeddings", lambda *a: Embeddings())
    monkeypatch.setattr(ingest, "get_qdrant_client", lambda s: None)
    monkeypatch.setattr(ingest, "rebuild_index", rebuild)
    out = tmp_path / "index_info.json"
    settings = Settings(_env_file=None, index_info_path=str(out))
    args = argparse.Namespace(info_only=False, only=[doc_id], refresh=False, dry_run=False)
    return lambda: ingest.run(args, settings, kb), out


def test_a_full_run_writes_the_file_after_the_rebuild(tmp_path, monkeypatch):
    run, out = full_run_setup(tmp_path, monkeypatch, rebuild=lambda *a, **k: 1)
    run()
    assert read_index_info(out).sources_as_of == date(2026, 11, 18)


def test_a_failed_rebuild_leaves_the_file_untouched(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("qdrant down")

    run, out = full_run_setup(tmp_path, monkeypatch, rebuild=boom)
    with pytest.raises(RuntimeError):
        run()
    assert not out.exists()

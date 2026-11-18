"""CLI: `uv run python -m gradpath.ingestion.ingest [--refresh] [--only DOC_ID ...] [--dry-run]`."""

import argparse
import logging
from pathlib import Path

import httpx
from langchain_core.documents import Document

from gradpath.config import REPO_ROOT, Settings, get_settings
from gradpath.ingestion.chunk import chunk_page, read_processed, write_processed
from gradpath.ingestion.clean import clean_page
from gradpath.ingestion.embed import build_embeddings, estimate_tokens
from gradpath.ingestion.fetch import Politeness, fetch_source, load_manual, make_client
from gradpath.ingestion.index import get_qdrant_client, rebuild_index
from gradpath.ingestion.manifest import SourceEntry, load_manifest, select_ingestible


def process_entry(
    entry: SourceEntry,
    kb: Path,
    settings: Settings,
    client: httpx.Client,
    politeness: Politeness,
    refresh: bool,
) -> tuple[int, list[Document]]:
    """Fetch (or load manual files), clean and chunk one document; writes its processed JSONL.

    Returns (page_count, chunks). A document with no pages writes nothing.
    """
    if entry.manual:
        pages = load_manual(entry, kb / "manual")
    else:
        pages = fetch_source(entry, kb / "raw", client, refresh, politeness)
    chunks: list[Document] = []
    for page in pages:
        raw = page.path.read_text(encoding="utf-8", errors="replace")
        _, text = clean_page(raw, page.kind)
        page_chunks = chunk_page(
            entry,
            text,
            page.index,
            page.url,
            page.retrieved_at,
            settings.chunk_size,
            settings.chunk_overlap,
        )
        chunks += page_chunks
    if chunks:
        write_processed(kb / "processed" / f"{entry.document_id}.jsonl", chunks)
    return len(pages), chunks


def run(args: argparse.Namespace, settings: Settings, kb: Path) -> None:
    """Orchestrate fetch -> clean -> chunk (-> embed -> index unless dry run)."""
    entries = load_manifest(kb / "source_manifest.csv")
    approved = select_ingestible(entries)
    targets = select_ingestible(entries, args.only)
    unknown = set(args.only or []) - {e.document_id for e in targets}
    if unknown:
        raise SystemExit(f"Unknown or non-approved document ids: {sorted(unknown)}")
    client, politeness = make_client(), Politeness()
    print(f"{'document_id':45} {'pages':>5} {'chunks':>6} {'est_tokens':>10}")
    total_pages = total_chunks = total_tokens = 0
    try:
        for entry in targets:
            pages, chunks = process_entry(entry, kb, settings, client, politeness, args.refresh)
            tokens = sum(estimate_tokens(c.page_content) for c in chunks)
            print(f"{entry.document_id:45} {pages:5d} {len(chunks):6d} {tokens:10d}")
            total_pages += pages
            total_chunks += len(chunks)
            total_tokens += tokens
    finally:
        client.close()
    print(f"{'TOTAL':45} {total_pages:5d} {total_chunks:6d} {total_tokens:10d}")
    if args.dry_run:
        return
    documents: list[Document] = []
    for entry in approved:
        path = kb / "processed" / f"{entry.document_id}.jsonl"
        if path.exists():
            documents += read_processed(path)
    embeddings = build_embeddings(settings, kb / "processed" / "embedding_cache")
    qdrant = get_qdrant_client(settings)
    count = rebuild_index(
        qdrant,
        settings.qdrant_collection,
        documents,
        embeddings,
        progress=lambda done, total: print(f"embedded {done}/{total} chunks", flush=True),
    )
    print(f"Embedding cache: {embeddings.hits} hits, {embeddings.misses} misses.")
    print(f"Indexed {count} chunks into '{settings.qdrant_collection}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the GradPath knowledge base.")
    parser.add_argument("--refresh", action="store_true", help="re-download cached pages")
    parser.add_argument("--only", nargs="+", metavar="DOC_ID", help="process only these documents")
    parser.add_argument("--dry-run", action="store_true", help="skip embedding and Qdrant")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(args, get_settings(), REPO_ROOT / "knowledge_base")


if __name__ == "__main__":
    main()

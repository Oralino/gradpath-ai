"""Split cleaned pages into metadata-rich LangChain Documents and write them as JSONL."""

import json
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from gradpath.ingestion.manifest import SourceEntry

MIN_CHUNK_CHARS = 50
HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]


def chunk_page(
    entry: SourceEntry,
    text: str,
    page_index: int,
    source_url: str,
    retrieved_at: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Document]:
    """Header-split then size-split one page; chunk_id is `<doc>:<page>:<n>`, stable across runs.

    Called by ingest.py. Headers are kept in the text so each chunk carries its own context.
    """
    by_header = MarkdownHeaderTextSplitter(HEADERS, strip_headers=False).split_text(text)
    pieces = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    ).split_documents(by_header)
    docs: list[Document] = []
    for piece in pieces:
        if len(piece.page_content) < MIN_CHUNK_CHARS:
            continue
        section = " > ".join(piece.metadata[k] for _, k in HEADERS if k in piece.metadata)
        docs.append(
            Document(
                page_content=piece.page_content,
                metadata={
                    "document_id": entry.document_id,
                    "chunk_id": f"{entry.document_id}:{page_index}:{len(docs)}",
                    "title": entry.title,
                    "section": section,
                    "source_url": source_url,
                    "source_type": entry.source_type,
                    "collection": entry.collection,
                    "topic": entry.topic,
                    "license_or_usage_notes": entry.license_or_usage_notes,
                    "retrieved_at": retrieved_at,
                },
            )
        )
    return docs


def write_processed(path: Path, docs: list[Document]) -> None:
    """Write one chunk per line (page_content + metadata) to `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps({"page_content": d.page_content, "metadata": d.metadata}) + "\n")


def read_processed(path: Path) -> list[Document]:
    """Load Documents back from a processed JSONL file (used to rebuild the index)."""
    docs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            docs.append(Document(page_content=row["page_content"], metadata=row["metadata"]))
    return docs

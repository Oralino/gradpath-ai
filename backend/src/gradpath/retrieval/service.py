"""Retrieval service: one place that turns a query into scored, citable evidence.

Used by traditional RAG (`POST /api/chat`), job analysis, and later the LangGraph workflow as a
tool, so there is exactly one retrieval implementation (see ARCHITECTURE.md, "Request flow").
"""

from collections.abc import Iterable
from typing import Literal

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient, models

from gradpath.config import REPO_ROOT, Settings, get_settings

FilterKey = Literal["collection", "document_id", "topic"]


class Evidence(BaseModel):
    """One retrieved chunk with everything needed to cite it."""

    chunk_id: str
    document_id: str
    title: str
    section: str = ""
    source_url: str
    collection: str = ""
    text: str
    score: float = Field(description="Cosine similarity to the query, -1..1 (higher is closer)")


class RetrievalResult(BaseModel):
    """Evidence for one query. `insufficient` means nothing cleared the score threshold."""

    query: str
    evidence: list[Evidence]
    insufficient: bool
    best_score: float | None = None


def to_evidence(doc: Document, score: float) -> Evidence:
    """Map a LangChain `Document` from Qdrant (payload written by ingestion.index) to Evidence."""
    m = doc.metadata
    return Evidence(
        chunk_id=m["chunk_id"],
        document_id=m["document_id"],
        title=m.get("title", ""),
        section=m.get("section", "") or "",
        source_url=m.get("source_url", ""),
        collection=m.get("collection", ""),
        text=doc.page_content,
        score=score,
    )


def build_filter(filters: dict[FilterKey, str | list[str]] | None) -> models.Filter | None:
    """Translate {"collection": ["a", "b"], ...} into a Qdrant payload filter on chunk metadata."""
    if not filters:
        return None
    conditions = []
    for key, value in filters.items():
        values = [value] if isinstance(value, str) else list(value)
        conditions.append(
            models.FieldCondition(key=f"metadata.{key}", match=models.MatchAny(any=values))
        )
    return models.Filter(must=conditions)


def cap_per_document(evidence: Iterable[Evidence], k: int, cap: int | None) -> list[Evidence]:
    """Keep the best `k` items, at most `cap` from any one document (None = no cap)."""
    kept: list[Evidence] = []
    per_doc: dict[str, int] = {}
    for item in evidence:
        if cap is not None and per_doc.get(item.document_id, 0) >= cap:
            continue
        kept.append(item)
        per_doc[item.document_id] = per_doc.get(item.document_id, 0) + 1
        if len(kept) == k:
            break
    return kept


class RetrievalService:
    """Semantic search over the knowledge base with a relevance threshold.

    `search` embeds the query (one Voyage request), asks Qdrant for the nearest chunks, drops
    those under `min_score`, and optionally limits chunks per document so answers can cite more
    than one source. It never invents evidence: an empty result is flagged `insufficient`, and
    callers must then say the knowledge base does not cover the question.
    """

    def __init__(
        self,
        client: QdrantClient,
        collection: str,
        embeddings: Embeddings,
        k: int = 5,
        min_score: float = 0.35,
    ):
        self.store = QdrantVectorStore(
            client=client, collection_name=collection, embedding=embeddings
        )
        self.k = k
        self.min_score = min_score

    def search(
        self,
        query: str,
        *,
        k: int | None = None,
        filters: dict[FilterKey, str | list[str]] | None = None,
        max_per_document: int | None = None,
    ) -> RetrievalResult:
        """Return up to `k` evidence chunks for `query` that clear `min_score`."""
        k = k or self.k
        # Over-fetch when capping per document, so the cap doesn't leave the result short.
        fetch_k = k * 3 if max_per_document else k
        hits = self.store.similarity_search_with_score(
            query, k=fetch_k, filter=build_filter(filters)
        )
        ranked = [to_evidence(doc, score) for doc, score in hits]
        best = ranked[0].score if ranked else None
        relevant = [e for e in ranked if e.score >= self.min_score]
        evidence = cap_per_document(relevant, k, max_per_document)
        return RetrievalResult(
            query=query, evidence=evidence, insufficient=not evidence, best_score=best
        )


def get_retrieval_service(settings: Settings | None = None) -> RetrievalService:
    """Build the service from settings: Qdrant client + Voyage query embeddings (rate-limited)."""
    from gradpath.ingestion.embed import build_embeddings
    from gradpath.ingestion.index import get_qdrant_client

    s = settings or get_settings()
    embeddings = build_embeddings(s, REPO_ROOT / "knowledge_base" / "processed" / "embedding_cache")
    return RetrievalService(
        get_qdrant_client(s),
        s.qdrant_collection,
        embeddings,
        k=s.retrieval_k,
        min_score=s.retrieval_min_score,
    )

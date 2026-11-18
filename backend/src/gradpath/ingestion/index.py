"""Qdrant storage: client factory and a full, idempotent index rebuild."""

from collections.abc import Callable
from uuid import NAMESPACE_URL, uuid5

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from gradpath.config import REPO_ROOT, Settings

ADD_BATCH = 64


def get_qdrant_client(settings: Settings) -> QdrantClient:
    """Server client if `qdrant_url` is set, else local on-disk storage under the repo root."""
    if settings.qdrant_url:
        key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
        return QdrantClient(url=settings.qdrant_url, api_key=key)
    return QdrantClient(path=str(REPO_ROOT / settings.qdrant_local_path))


def point_id(chunk_id: str) -> str:
    """Deterministic Qdrant point id for a chunk id."""
    return str(uuid5(NAMESPACE_URL, chunk_id))


def rebuild_index(
    client: QdrantClient,
    collection: str,
    documents: list[Document],
    embeddings: Embeddings,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    """Embed everything first, then drop/recreate `collection` and upsert; returns the chunk count.

    Called by ingest.py. Embedding before touching Qdrant means a failed run leaves the existing
    collection intact. Points use QdrantVectorStore's default payload layout (page_content +
    metadata) so retrieval can read them through it; ids come from chunk_id (deterministic).
    """
    if not documents:
        raise ValueError("no documents to index")
    vectors = embeddings.embed_documents([d.page_content for d in documents])
    if client.collection_exists(collection):
        client.delete_collection(collection)
    client.create_collection(
        collection, vectors_config=VectorParams(size=len(vectors[0]), distance=Distance.COSINE)
    )
    for start in range(0, len(documents), ADD_BATCH):
        end = start + ADD_BATCH
        points = [
            PointStruct(
                id=point_id(d.metadata["chunk_id"]),
                vector=v,
                payload={"page_content": d.page_content, "metadata": d.metadata},
            )
            for d, v in zip(documents[start:end], vectors[start:end], strict=True)
        ]
        client.upsert(collection, points=points)
        if progress:
            progress(start + len(points), len(documents))
    return len(documents)

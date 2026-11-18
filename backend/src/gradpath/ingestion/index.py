"""Qdrant storage: client factory and a full, idempotent index rebuild."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid4, uuid5

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient
from qdrant_client.models import (
    CreateAlias,
    CreateAliasOperation,
    DeleteAlias,
    DeleteAliasOperation,
    Distance,
    PointStruct,
    VectorParams,
)

from gradpath.config import REPO_ROOT, Settings

log = logging.getLogger(__name__)

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
    """Embed everything, build a new physical collection, then switch the alias `collection` to it.

    Called by ingest.py; retrieval reads `collection` as an alias, so readers never see a half-built
    index. Any failure before the switch deletes the new collection and re-raises, leaving the old
    index in place. Old physical collections are deleted after the switch; an old-layout real
    collection named `collection` is deleted before it (an alias cannot share its name).
    Points use QdrantVectorStore's default payload layout (page_content + metadata); ids come from
    chunk_id (deterministic).
    """
    if not documents:
        raise ValueError("no documents to index")
    vectors = embeddings.embed_documents([d.page_content for d in documents])
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    new = f"{collection}_{stamp}{uuid4().hex[:8]}"
    client.create_collection(
        new, vectors_config=VectorParams(size=len(vectors[0]), distance=Distance.COSINE)
    )
    try:
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
            client.upsert(new, points=points)
            if progress:
                progress(start + len(points), len(documents))
        aliases = client.get_aliases().aliases
        old = [a.collection_name for a in aliases if a.alias_name == collection]
        operations: list = []
        if old:
            operations.append(DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=collection)))
        elif client.collection_exists(collection):
            log.info("migrating: deleting old real collection %s for the alias", collection)
            client.delete_collection(collection)
        operations.append(
            CreateAliasOperation(
                create_alias=CreateAlias(collection_name=new, alias_name=collection)
            )
        )
        client.update_collection_aliases(change_aliases_operations=operations)
    except Exception:
        client.delete_collection(new)
        raise
    for name in old:
        client.delete_collection(name)
    return len(documents)

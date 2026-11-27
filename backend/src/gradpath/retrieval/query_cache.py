"""Persistent cache of query embeddings in Qdrant, so a repeated question costs no Voyage call.

Used by `GuardedEmbeddings`. Stores only a hash-derived id, the model name and the vector: never
the question text. Optional: any Qdrant error is logged by type and the call goes uncached.
"""

import hashlib
import logging
import threading
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

log = logging.getLogger(__name__)


def normalise(query: str) -> str:
    """Whitespace and case folded, so trivially different spellings share one entry."""
    return " ".join(query.split()).casefold()


class QueryCache:
    """One collection per embedding model (fixed vector size), keyed by a hash of the question."""

    def __init__(
        self, client: QdrantClient, collection_prefix: str, model: str, max_entries: int
    ) -> None:
        self.client = client
        self.model = model
        self.collection = f"{collection_prefix}_{model}".replace("/", "_")
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._stored: int | None = None  # entries in the collection, loaded once then tracked

    def _id(self, query: str) -> str:
        digest = hashlib.sha256((self.model + "\x00" + normalise(query)).encode()).hexdigest()
        return str(uuid.uuid5(uuid.NAMESPACE_URL, digest))

    def get_many(self, queries: list[str]) -> list[list[float] | None]:
        """Cached vectors in input order, None for a miss (one retrieve call)."""
        try:
            if not queries or not self.client.collection_exists(self.collection):
                return [None] * len(queries)
            ids = [self._id(q) for q in queries]
            found = {
                str(p.id): p.vector
                for p in self.client.retrieve(self.collection, ids=ids, with_vectors=True)
            }
            return [list(v) if isinstance(v := found.get(i), list) else None for i in ids]
        except Exception as exc:
            log.warning("query cache unavailable: %s", type(exc).__name__)
            return [None] * len(queries)

    def put_many(self, queries: list[str], vectors: list[list[float]]) -> None:
        """Store new vectors unless the cache already holds `max_entries`."""
        if not queries:
            return
        try:
            with self._lock:
                if not self.client.collection_exists(self.collection):
                    self.client.create_collection(
                        self.collection,
                        vectors_config=VectorParams(size=len(vectors[0]), distance=Distance.COSINE),
                    )
                    self._stored = 0
                if self._stored is None:
                    self._stored = self.client.count(self.collection, exact=True).count
                if self._stored + len(queries) > self.max_entries:
                    return
                self.client.upsert(
                    self.collection,
                    points=[
                        PointStruct(id=self._id(q), vector=v, payload={"model": self.model})
                        for q, v in zip(queries, vectors, strict=True)
                    ],
                )
                self._stored += len(queries)
        except Exception as exc:
            log.warning("query cache unavailable: %s", type(exc).__name__)

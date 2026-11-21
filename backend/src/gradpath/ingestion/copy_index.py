"""Copy the local index to the deployed Qdrant (T-020 step 1), without re-embedding.

Run from `backend/` (stop the API first: local Qdrant allows one process):
  uv run python -m gradpath.ingestion.copy_index [--dry-run]

Reads every point (vector + payload) from the local collection and publishes them into
QDRANT_CLOUD_URL with `index.publish_points`, the same new-collection-then-alias switch ingest uses,
so the deployed index is never half-built. Spends no Voyage tokens (the free ones don't refresh).
Also how to rebuild the cloud index if Qdrant Cloud ever deletes an idle cluster.
"""

import argparse
import sys

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from gradpath.config import REPO_ROOT, Settings, get_settings
from gradpath.ingestion.index import publish_points

SCROLL_BATCH = 256


def read_points(client: QdrantClient, collection: str) -> list[PointStruct]:
    """Every point of `collection` (an alias works) with its vector and payload, in id order.
    Called by `copy_index`; scrolls in pages so a large index never needs one huge request."""
    points: list[PointStruct] = []
    offset = None
    while True:
        records, offset = client.scroll(
            collection, limit=SCROLL_BATCH, offset=offset, with_payload=True, with_vectors=True
        )
        points += [PointStruct(id=r.id, vector=r.vector, payload=r.payload) for r in records]
        if offset is None:
            return points


def copy_index(source: QdrantClient, target: QdrantClient, collection: str, progress=None) -> int:
    """Copy `collection` from source to target, then check the target holds the same points.
    Called by `main`; raises if the source is empty or the copy doesn't match (count, ids, a sample
    of vectors), so a bad copy is never reported as done."""
    points = read_points(source, collection)
    if not points:
        raise ValueError(f"the source collection {collection!r} is empty")
    publish_points(target, collection, points, progress)
    copied = {p.id: p for p in read_points(target, collection)}
    if set(copied) != {p.id for p in points}:
        raise RuntimeError(f"copy mismatch: {len(copied)} points in the target, {len(points)} sent")
    for p in points[:: max(1, len(points) // 20)]:  # about 20 spread-out samples
        got = copied[p.id]
        if got.payload != p.payload or not _same_vector(got.vector, p.vector):
            raise RuntimeError(f"copy mismatch at point {p.id}")
    return len(points)


def _same_vector(a, b, tol: float = 1e-6) -> bool:
    """Vectors equal within float tolerance (a server may round-trip them as float32)."""
    return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


def target_client(settings: Settings) -> QdrantClient:
    """The deployed Qdrant from QDRANT_CLOUD_URL / QDRANT_CLOUD_API_KEY (never printed)."""
    if not settings.qdrant_cloud_url:
        sys.exit("set QDRANT_CLOUD_URL (and QDRANT_CLOUD_API_KEY) in .env first")
    if not settings.qdrant_cloud_url.startswith("https://"):
        sys.exit("QDRANT_CLOUD_URL must start with https:// (the API key goes with each request)")
    key = (
        settings.qdrant_cloud_api_key.get_secret_value() if settings.qdrant_cloud_api_key else None
    )
    return QdrantClient(url=settings.qdrant_cloud_url, api_key=key)


def main() -> None:
    """Parse arguments, open both clients, copy, close the local one (it holds a file lock)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="count the local points only")
    args = parser.parse_args()
    settings = get_settings()
    source = QdrantClient(path=str(REPO_ROOT / settings.qdrant_local_path))
    try:
        if args.dry_run:
            count = len(read_points(source, settings.qdrant_collection))
            print(f"local {settings.qdrant_collection}: {count} points (nothing copied)")
            return
        target = target_client(settings)
        n = copy_index(
            source,
            target,
            settings.qdrant_collection,
            progress=lambda done, total: print(f"  {done}/{total}", end="\r"),
        )
        print(f"\ncopied {n} points to the deployed index and checked them")
    finally:
        source.close()


if __name__ == "__main__":
    main()

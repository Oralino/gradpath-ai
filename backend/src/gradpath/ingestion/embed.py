"""Rate-limited embeddings: batches and spaces requests inside Voyage's rpm and tpm limits."""

import hashlib
import json
import logging
import math
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_voyageai import VoyageAIEmbeddings
from voyageai.error import RateLimitError

from gradpath.config import Settings

log = logging.getLogger(__name__)

WINDOW_S = 60.0
MAX_TEXTS_PER_REQUEST = 128  # Voyage's per-request text cap; keeps one batch = one API call
BACKOFF_BASE_S = 5.0
CACHE_FLUSH_EVERY = 32  # texts per cache write; a failed run loses at most one group


def estimate_tokens(text: str) -> int:
    """Cheap token estimate: characters / 4, rounded up."""
    return math.ceil(len(text) / 4)


class ThrottledEmbeddings(Embeddings):
    """Wrap any `Embeddings`; keep requests under `rpm` and `tpm` per rolling minute.

    Used by index.py via build_embeddings. Batches stay under 80% of tpm (the token estimate is
    rough); a sliding 60 s window of (time, tokens) decides how long to wait before each request.
    Rate-limit errors are retried with exponential backoff.
    """

    def __init__(
        self,
        inner: Embeddings,
        rpm: int,
        tpm: int,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        max_tries: int = 5,
    ):
        self.inner = inner
        self.rpm = rpm
        self.tpm = tpm
        self._sleep = sleep
        self._clock = clock
        self.max_tries = max_tries
        self._window: deque[tuple[float, int]] = deque()

    def _batches(self, texts: list[str]) -> list[list[str]]:
        budget = self.tpm * 0.8
        batches: list[list[str]] = []
        current: list[str] = []
        used = 0
        for text in texts:
            tokens = estimate_tokens(text)
            if current and (used + tokens > budget or len(current) >= MAX_TEXTS_PER_REQUEST):
                batches.append(current)
                current, used = [], 0
            current.append(text)
            used += tokens
        if current:
            batches.append(current)
        return batches

    def _wait_for_slot(self, tokens: int) -> None:
        """Block until one more request of `tokens` fits in both the rpm and tpm windows."""
        while True:
            now = self._clock()
            while self._window and self._window[0][0] <= now - WINDOW_S:
                self._window.popleft()
            used = sum(t for _, t in self._window)
            if len(self._window) < self.rpm and used + tokens <= self.tpm:
                return
            if not self._window:  # a single oversized batch can never fit; send it alone
                return
            self._sleep(self._window[0][0] + WINDOW_S - now)

    def _call(self, fn: Callable, arg, tokens: int):
        """Run one API call through the rpm/tpm window, retrying rate-limit errors with backoff."""
        for attempt in range(self.max_tries):
            self._wait_for_slot(tokens)
            self._window.append((self._clock(), tokens))
            try:
                return fn(arg)
            except RateLimitError:
                if attempt == self.max_tries - 1:
                    raise
                delay = BACKOFF_BASE_S * 2**attempt
                log.warning("Voyage rate limit; retrying in %.0fs", delay)
                self._sleep(delay)
        raise AssertionError("unreachable")

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        tokens = sum(estimate_tokens(t) for t in batch)
        return self._call(self.inner.embed_documents, batch, tokens)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for batch in self._batches(texts):
            vectors.extend(self._embed_batch(batch))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        # Queries count against the same rpm/tpm limits, so they use the shared window too.
        return self._call(self.inner.embed_query, text, estimate_tokens(text))


class CachedEmbeddings(Embeddings):
    """On-disk vector cache in front of `inner` so already-paid embeddings are never re-bought.

    Key = sha256(model + text); the file is append-only JSONL loaded into a dict at start. Only
    documents are cached (queries pass through). Used by build_embeddings, called by index.py.
    """

    def __init__(self, inner: Embeddings, model: str, path: Path):
        self.inner = inner
        self.model = model
        self.path = path
        self.hits = 0
        self.misses = 0
        self._vectors: dict[str, list[float]] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._vectors[row["key"]] = row["vector"]

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model}\n{text}".encode()).hexdigest()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        keys = [self._key(t) for t in texts]
        missing = {k: t for k, t in zip(keys, texts, strict=True) if k not in self._vectors}
        self.hits += len(texts) - len(missing)
        self.misses += len(missing)
        # Embed and persist in small groups, so a failure part-way through keeps what was paid for.
        pending = list(missing.items())
        for start in range(0, len(pending), CACHE_FLUSH_EVERY):
            group = pending[start : start + CACHE_FLUSH_EVERY]
            vectors = self.inner.embed_documents([t for _, t in group])
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                for (key, _), vec in zip(group, vectors, strict=True):
                    self._vectors[key] = vec
                    f.write(json.dumps({"key": key, "vector": vec}) + "\n")
        return [self._vectors[k] for k in keys]

    def embed_query(self, text: str) -> list[float]:
        return self.inner.embed_query(text)


def build_embeddings(settings: Settings, cache_dir: Path) -> CachedEmbeddings:
    """Cache(Throttle(Voyage)); raises without a key (called by ingest.py)."""
    if settings.voyage_api_key is None:
        raise RuntimeError("VOYAGE_API_KEY is not set; add it to .env to embed and index.")
    inner = VoyageAIEmbeddings(
        model=settings.embed_model,
        voyage_api_key=settings.voyage_api_key,
        batch_size=MAX_TEXTS_PER_REQUEST,
    )
    throttled = ThrottledEmbeddings(inner, rpm=settings.voyage_rpm, tpm=settings.voyage_tpm)
    safe_model = settings.embed_model.replace("/", "_")
    return CachedEmbeddings(throttled, settings.embed_model, cache_dir / f"{safe_model}.jsonl")

"""Rate-limited embeddings: batches and spaces requests inside Voyage's rpm and tpm limits."""

import hashlib
import json
import logging
import math
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

import voyageai
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


class WindowFull(Exception):
    """The free-tier request window is full right now (`ThrottledEmbeddings.embed_query_now`)."""


class ThrottledEmbeddings(Embeddings):
    """Wrap any `Embeddings`; keep requests under `rpm` and `tpm` per rolling minute.

    Used by index.py via build_embeddings. Batches stay under 80% of tpm (the token estimate is
    rough); a sliding 60 s window of (time, tokens) decides how long to wait before each request.
    Rate-limit errors are retried with exponential backoff. Thread-safe: API routes run in a
    threadpool and share one instance, so the window is guarded by a lock (never held in sleep).
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
        self._lock = threading.Lock()

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

    def _try_reserve(self, tokens: int) -> float | None:
        """Record one request of `tokens` if it fits the rpm and tpm windows now (returns None),
        else return the seconds until it would. Check and record happen under one lock so
        concurrent threads cannot both take the last slot."""
        with self._lock:
            now = self._clock()
            while self._window and self._window[0][0] <= now - WINDOW_S:
                self._window.popleft()
            used = sum(t for _, t in self._window)
            fits = len(self._window) < self.rpm and used + tokens <= self.tpm
            # a single oversized batch can never fit; send it alone
            if fits or not self._window:
                self._window.append((now, tokens))
                return None
            return self._window[0][0] + WINDOW_S - now

    def _reserve_slot(self, tokens: int) -> None:
        """Block until one more request fits the windows, then record it (called by `_call`).
        The sleep happens outside the lock so other threads are not blocked."""
        while (wait := self._try_reserve(tokens)) is not None:
            self._sleep(wait)

    def embed_query_now(self, text: str) -> list[float]:
        """One attempt that never waits (T-018 step 4, public source search): raises
        `WindowFull` when the shared window has no room, and a Voyage 429 is not retried, so a
        visitor's request can't hold a worker thread or spend more than one Voyage request."""
        if self._try_reserve(estimate_tokens(text)) is not None:
            raise WindowFull
        return self.inner.embed_query(text)

    def _call(self, fn: Callable, arg, tokens: int):
        """Run one API call through the rpm/tpm window, retrying rate-limit errors with backoff."""
        for attempt in range(self.max_tries):
            self._reserve_slot(tokens)
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

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Embed many queries in as few requests as possible (used by RetrievalService.search_many).

        Uses the inner model's batched `embed_queries` when it has one (one request per token-budget
        batch instead of one per query: 20 queries = 1 request, not 7 minutes at 3 RPM).
        """
        batch_fn = getattr(self.inner, "embed_queries", None)
        if batch_fn is None:
            return [self.embed_query(t) for t in texts]
        vectors: list[list[float]] = []
        for batch in self._batches(texts):
            vectors.extend(self._call(batch_fn, batch, sum(estimate_tokens(t) for t in batch)))
        return vectors


class CachedEmbeddings(Embeddings):
    """On-disk vector cache in front of `inner` so already-paid embeddings are never re-bought.

    Key = sha256(model + text); the file is append-only JSONL loaded into a dict at start. Only
    documents are cached (queries pass through). Used by build_embeddings, called by index.py.
    Unparseable lines (a crash mid-append leaves a truncated one) are skipped with a warning.
    """

    def __init__(self, inner: Embeddings, model: str, path: Path):
        self.inner = inner
        self.model = model
        self.path = path
        self.hits = 0
        self.misses = 0
        self._vectors: dict[str, list[float]] = {}
        if path.exists():
            bad = 0
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    self._vectors[row["key"]] = row["vector"]
                except (json.JSONDecodeError, KeyError, TypeError):
                    bad += 1
            if bad:
                log.warning("embedding cache %s: skipped %d unreadable line(s)", path, bad)

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

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Queries are not cached; pass the batch through (or fall back to one at a time)."""
        batch_fn = getattr(self.inner, "embed_queries", None)
        return batch_fn(texts) if batch_fn else [self.inner.embed_query(t) for t in texts]


class VoyageEmbeddings(VoyageAIEmbeddings):
    """`VoyageAIEmbeddings` plus `embed_queries`: many queries in one request.

    LangChain's class embeds queries one request at a time; the public `voyageai.Client.embed`
    accepts a list with `input_type="query"`, which matters on the 3-requests-a-minute free tier.
    """

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        client = voyageai.Client(api_key=self.voyage_api_key.get_secret_value())
        return client.embed(texts, model=self.model, input_type="query").embeddings


def _voyage(settings: Settings) -> VoyageEmbeddings:
    if settings.voyage_api_key is None:
        raise RuntimeError("VOYAGE_API_KEY is not set; add it to .env to embed and index.")
    return VoyageEmbeddings(
        model=settings.embed_model,
        voyage_api_key=settings.voyage_api_key,
        batch_size=MAX_TEXTS_PER_REQUEST,
    )


def build_query_embeddings(settings: Settings) -> ThrottledEmbeddings:
    """Throttle(Voyage) without the document cache (called by get_retrieval_service).

    Retrieval only embeds queries, so it must not load the large document-vector cache file.
    """
    return ThrottledEmbeddings(_voyage(settings), rpm=settings.voyage_rpm, tpm=settings.voyage_tpm)


def build_embeddings(settings: Settings, cache_dir: Path) -> CachedEmbeddings:
    """Cache(Throttle(Voyage)); raises without a key (called by ingest.py)."""
    throttled = build_query_embeddings(settings)
    safe_model = settings.embed_model.replace("/", "_")
    return CachedEmbeddings(throttled, settings.embed_model, cache_dir / f"{safe_model}.jsonl")

"""Cross-encoder reranking: rescore retrieved chunks by reading question and chunk together.

Milestone 5 experiment (T-010). Semantic search compares two vectors made separately; a
cross-encoder reads the pair at once, so it judges "does this chunk answer this question" rather
than "is it about the same topic". The retrieval eval compares it with semantic-only; the retrieval
service uses it only if that comparison shows it helps. Runs locally (fastembed + ONNX on the
CPU): no API, no tokens.
"""

import math
import threading
from pathlib import Path
from typing import Protocol

from gradpath.config import REPO_ROOT
from gradpath.retrieval.service import Evidence

DEFAULT_RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"  # 80 MB, Apache-2.0
MODEL_CACHE_DIR = REPO_ROOT / "backend" / "data" / "models"  # gitignored (backend/data/)


class Reranker(Protocol):
    """Scores how well each text answers `query`, 0..1, higher is better (one score per text)."""

    def score(self, query: str, texts: list[str]) -> list[float]: ...


def sigmoid(x: float) -> float:
    """Logit -> 0..1 without overflow for large negative logits."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


class CrossEncoderReranker:
    """fastembed's ONNX cross-encoder, scores squashed to 0..1 with a sigmoid.

    The MS MARCO models return raw logits (unbounded, roughly -11..+11); the sigmoid keeps the order
    and gives a fixed 0..1 scale to put an abstention threshold on. The model (downloaded once from
    Hugging Face into `MODEL_CACHE_DIR`) loads lazily on the first call, so importing this costs
    nothing. A lock serialises calls: one ONNX session is shared by API threads.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_RERANK_MODEL,
        cache_dir: Path = MODEL_CACHE_DIR,
        threads: int | None = None,
    ):
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.threads = threads
        self._model = None
        self._lock = threading.Lock()

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        with self._lock:
            if self._model is None:
                from fastembed.rerank.cross_encoder import TextCrossEncoder

                self._model = TextCrossEncoder(
                    self.model_name, cache_dir=str(self.cache_dir), threads=self.threads
                )
            logits = list(self._model.rerank(query, texts, batch_size=len(texts)))
        return [sigmoid(float(x)) for x in logits]


def rerank(
    query: str, evidence: list[Evidence], reranker: Reranker
) -> list[tuple[Evidence, float]]:
    """Pair each chunk with its reranker score, best first (ties keep the semantic order).

    Called by the retrieval eval on the semantic top-N candidates. Evidence is returned unchanged
    (its `score` stays the cosine similarity) so callers can report both scores.
    """
    scores = reranker.score(query, [e.text for e in evidence])
    if len(scores) != len(evidence):
        raise ValueError(f"reranker returned {len(scores)} scores for {len(evidence)} chunks")
    order = sorted(range(len(evidence)), key=lambda i: -scores[i])
    return [(evidence[i], scores[i]) for i in order]

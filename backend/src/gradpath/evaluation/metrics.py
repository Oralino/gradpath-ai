"""Retrieval metrics: pure functions over a ranked list of Evidence and a question's targets.

Definitions match EVALUATION.md: Recall@K counts targets found, Precision@K counts relevant chunks
among the K slots, MRR uses the rank of the first relevant chunk. Called by `retrieval_eval`.
"""

from gradpath.evaluation.dataset import Target
from gradpath.retrieval import Evidence

SECTION_SEPARATOR = " > "


def matches(chunk: Evidence, target: Target) -> bool:
    """True if the chunk is on the target's page and, if a section is named, under that heading.

    The heading must equal one whole component of the section path, so "Cache" matches
    "Primer > Cache > Client caching" but not "Primer > Cache-control headers".
    """
    if chunk.document_id != target.document_id or chunk.source_url != target.page:
        return False
    if target.section is None:
        return True
    return target.section in chunk.section.split(SECTION_SEPARATOR)


def is_relevant(chunk: Evidence, targets: list[Target]) -> bool:
    return any(matches(chunk, t) for t in targets)


def recall_at_k(ranked: list[Evidence], targets: list[Target], k: int) -> float:
    """Share of targets with at least one matching chunk in the top k."""
    if not targets:
        raise ValueError("recall is undefined for a question with no targets")
    top = ranked[:k]
    found = sum(1 for t in targets if any(matches(c, t) for c in top))
    return found / len(targets)


def precision_at_k(ranked: list[Evidence], targets: list[Target], k: int) -> float:
    """Share of the k slots filled by a relevant chunk (empty slots count as misses)."""
    if k <= 0:
        raise ValueError("k must be positive")
    return sum(1 for c in ranked[:k] if is_relevant(c, targets)) / k


def reciprocal_rank(ranked: list[Evidence], targets: list[Target], k: int) -> float:
    """1 / rank of the first relevant chunk within the top k, or 0 if there is none."""
    for rank, chunk in enumerate(ranked[:k], 1):
        if is_relevant(chunk, targets):
            return 1.0 / rank
    return 0.0

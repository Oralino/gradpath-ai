"""Source search without a model (T-018 step 4): the retrieval half of RAG, for visitors with no
key.

`search_sources` runs one real retrieval and returns the matching passages with citations, plus a
rules-only route preview. It calls no model: the passages are shown as found, never summarised,
and the preview uses only `router/rules.py`, saying "a model would decide" when the rules can't.
Called by `api/search.py`.
"""

from pydantic import BaseModel, Field

from gradpath.rag.answer import Citation, to_citation
from gradpath.retrieval import RetrievalService
from gradpath.router.route import decide
from gradpath.router.rules import rule_kind
from gradpath.router.schemas import RouteDecision, RouteRequest

MAX_EXCERPT_CHARS = 600
MAX_PER_DOCUMENT = 2  # a few sources, not five chunks of one page
NO_RULE = "The rules can't decide this one; the full app asks a small model to classify it."


class SourceHit(BaseModel):
    """One passage: where it is from (as a citation) and the start of its text. `excerpt` is
    retrieved text: untrusted, rendered as plain text only."""

    citation: Citation
    excerpt: str


class SourceSearch(BaseModel):
    """What `POST /api/search` returns. `insufficient` means nothing cleared the relevance
    threshold, so the knowledge base doesn't cover the query."""

    query: str
    hits: list[SourceHit]
    insufficient: bool
    route_preview: RouteDecision | None = Field(
        description="The route the rules alone pick; null when only the model could decide."
    )
    route_note: str | None = None


def excerpt(text: str, limit: int = MAX_EXCERPT_CHARS) -> str:
    """The start of a chunk, cut at a word boundary with an ellipsis when it is longer. Line
    breaks are kept (one per line, no blank lines), so code stays readable."""
    lines = [" ".join(line.split()) for line in text.splitlines()]
    flat = "\n".join(line for line in lines if line)
    if len(flat) <= limit:
        return flat
    head = flat[: limit + 1]
    if head[-1].isspace():  # the limit falls between two words: keep the last one whole
        cut = head[:limit]
    else:
        parts = head.rsplit(None, 1)
        cut = parts[0] if len(parts) == 2 else head[:limit]  # one long word: hard cut
    return f"{cut.rstrip()}…"


def preview_route(query: str) -> RouteDecision | None:
    """The rules-only decision for a bare query (no posting or profile attached), or None."""
    req = RouteRequest(message=query)
    hit = rule_kind(req)
    return None if hit is None else decide(hit[0], hit[1], req, "rules")


def embed_now(retrieval: RetrievalService, query: str) -> list[float]:
    """Embed without waiting or retrying when the embeddings support it (the throttled Voyage
    client does; test doubles may not): see `ThrottledEmbeddings.embed_query_now`."""
    now = getattr(retrieval.embeddings, "embed_query_now", None)
    return now(query) if now is not None else retrieval.embeddings.embed_query(query)


def search_sources(query: str, retrieval: RetrievalService) -> SourceSearch:
    """One retrieval (at most one Voyage request, never queued), no model call."""
    vector = embed_now(retrieval, query)
    result = retrieval.search_vectors([query], [vector], max_per_document=MAX_PER_DOCUMENT)[0]
    hits = [SourceHit(citation=to_citation(e), excerpt=excerpt(e.text)) for e in result.evidence]
    preview = preview_route(query)
    return SourceSearch(
        query=query,
        hits=hits,
        insufficient=result.insufficient,
        route_preview=preview,
        route_note=None if preview else NO_RULE,
    )

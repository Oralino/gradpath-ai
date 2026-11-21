"""`POST /api/search`: source passages for a query, with no model call (T-018 step 4).

Open in every mode, because it never calls a model: it is what a visitor without a key can run
live. It needs retrieval (the owner's Voyage key and Qdrant), so it answers 503 when the server
started without it (demo mode with no Voyage key). The query is never logged. Concurrency is
capped (`limits.SEARCH`); per-IP limits come with T-018 step 7.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StringConstraints

from gradpath.api import limits
from gradpath.rag.sources import SourceSearch, search_sources
from gradpath.retrieval import RetrievalService

router = APIRouter(prefix="/api", tags=["search"])

SEARCH_OFF = "Source search is off on this server. Browse the recorded examples instead."


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown fields are a 422, not silently dropped
    # Stripped first, so spaces can't spend a Voyage request.
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


def get_search_retrieval(request: Request) -> RetrievalService:
    """The shared retrieval service, or 503 when this server runs without one."""
    retrieval = getattr(request.app.state, "retrieval", None)
    if retrieval is None:
        raise HTTPException(status_code=503, detail=SEARCH_OFF)
    return retrieval


@router.post("/search", response_model=SourceSearch)
def search(
    body: SearchRequest,
    retrieval: Annotated[RetrievalService, Depends(get_search_retrieval)],
) -> SourceSearch:
    """A plain `def` route: the blocking Voyage and Qdrant calls run in a worker thread."""
    with limits.slot(limits.SEARCH):
        return search_sources(body.query, retrieval)

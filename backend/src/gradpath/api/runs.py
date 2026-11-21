"""`POST /api/career/runs` and `GET /api/career/runs/{run_id}`: a preparation run in the
background, polled by the browser for live stage progress (T-016, DESIGN.md decision 2 option B).

The run itself is `workflows/runs.py`; this module only maps it to HTTP. One run at a time
(`limits.CAREER`, shared with `/api/career/prepare` and the assist route): a second start gets
503 at once.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.language_models.chat_models import BaseChatModel

from gradpath.api import limits
from gradpath.api.career import BUSY
from gradpath.api.deps import (
    get_answer_model,
    get_extraction_model,
    get_retrieval,
    require_model_routes,
    run_owner,
)
from gradpath.api.ratelimit import limit
from gradpath.config import get_settings
from gradpath.retrieval import RetrievalService
from gradpath.workflows import WorkflowContext
from gradpath.workflows.runs import RunBusy, RunStarted, RunStatus, RunStore
from gradpath.workflows.schemas import WorkflowInput

router = APIRouter(
    prefix="/api/career", tags=["career"], dependencies=[Depends(require_model_routes)]
)

NOT_FOUND = "This run was not found. It may have expired; start a new one."

# The process-wide store; tests replace it through `get_run_store`.
RUNS = RunStore(limits.CAREER)


def get_run_store() -> RunStore:
    """The run store (a dependency, so tests can swap in their own)."""
    return RUNS


@router.post(
    "/runs", status_code=202, response_model=RunStarted, dependencies=[Depends(limit("workflow"))]
)
def start_run(
    body: WorkflowInput,
    retrieval: Annotated[RetrievalService, Depends(get_retrieval)],
    fast: Annotated[BaseChatModel, Depends(get_extraction_model)],
    smart: Annotated[BaseChatModel, Depends(get_answer_model)],
    store: Annotated[RunStore, Depends(get_run_store)],
    owner: Annotated[str | None, Depends(run_owner)],
) -> RunStarted:
    """Start a run and return its id at once. The body is validated before anything starts; the
    revision limit and time budget come from settings, never from the request."""
    try:
        run_id = store.start(
            body,
            context=WorkflowContext(retrieval=retrieval, fast_llm=fast, smart_llm=smart),
            settings=get_settings(),
            owner=owner,
        )
    except RunBusy:
        raise HTTPException(status_code=503, detail=BUSY) from None
    return RunStarted(run_id=run_id)


@router.get("/runs/{run_id}", response_model=RunStatus, dependencies=[Depends(limit("poll"))])
def get_run(
    run_id: str,
    store: Annotated[RunStore, Depends(get_run_store)],
    owner: Annotated[str | None, Depends(run_owner)],
) -> RunStatus:
    """Stages so far and, once done, the result. 404 for an unknown, expired or malformed id,
    and in live mode for a run started with another key (the same answer, so ids can't be
    probed)."""
    status = store.get(run_id, owner)
    if status is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return status

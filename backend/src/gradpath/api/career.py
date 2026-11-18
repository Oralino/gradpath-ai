"""`POST /api/career/prepare`: job description + profile -> gaps, roadmap, interview questions.

Runs the LangGraph workflow (`workflows.run_workflow`) once, synchronously (about 5 model calls,
a few minutes on Claude Code). Owner decision 2026-11-18: synchronous for this milestone; a job
id with status polling comes with the frontend. Errors are mapped to fixed messages in
`api/main.py`; no exception text reaches the client.
"""

import threading
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.language_models.chat_models import BaseChatModel

from gradpath.api.deps import get_answer_model, get_extraction_model, get_retrieval
from gradpath.config import get_settings
from gradpath.retrieval import RetrievalService
from gradpath.workflows import CareerPrepResult, WorkflowContext, run_workflow
from gradpath.workflows.schemas import WorkflowInput

router = APIRouter(prefix="/api/career", tags=["career"])

# One workflow at a time per process: each run holds a worker thread for minutes, may start
# Claude Code processes, and shares Voyage's 3-requests-a-minute free tier. A second request gets
# 503 at once instead of queueing. Per-IP limits and auth come before deploy (TASKS.md).
_RUNNING = threading.BoundedSemaphore(1)
BUSY = "A preparation run is already in progress. Try again in a few minutes."


@router.post("/prepare", response_model=CareerPrepResult)
def prepare(
    body: WorkflowInput,
    retrieval: Annotated[RetrievalService, Depends(get_retrieval)],
    fast: Annotated[BaseChatModel, Depends(get_extraction_model)],
    smart: Annotated[BaseChatModel, Depends(get_answer_model)],
) -> CareerPrepResult:
    """The body is the same `WorkflowInput` that `run_workflow` validates (size limits, unknown
    fields refused). The revision limit comes from settings, never from the request."""
    if not _RUNNING.acquire(blocking=False):
        raise HTTPException(status_code=503, detail=BUSY)
    try:
        return run_workflow(
            body.job_description,
            body.profile,
            context=WorkflowContext(retrieval=retrieval, fast_llm=fast, smart_llm=smart),
            max_revisions=get_settings().workflow_max_revisions,
            corrections=body.corrections,
        )
    finally:
        _RUNNING.release()

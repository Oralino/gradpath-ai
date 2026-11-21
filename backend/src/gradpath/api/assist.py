"""`POST /api/assist`: one message (plus an optional job description and profile), routed to
traditional RAG or the career workflow (T-006).

The router's decision comes back with the result, so the client can show which path ran and
why. `/api/chat` and `/api/career/prepare` stay for direct use. Every request writes one line to
the route log (`router/route_log.py`), including requests that fail.
"""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.language_models.chat_models import BaseChatModel

from gradpath.api import limits
from gradpath.api.career import BUSY as CAREER_BUSY
from gradpath.api.deps import (
    get_answer_model,
    get_extraction_model,
    get_retrieval,
    require_model_routes,
)
from gradpath.api.runs import get_run_store
from gradpath.config import get_settings
from gradpath.retrieval import RetrievalService
from gradpath.router import route_log
from gradpath.router.assist import (
    AssistRequest,
    AssistResponse,
    decide,
    respond,
    route_log_entry,
)
from gradpath.router.schemas import RouteDecision
from gradpath.workflows import WorkflowContext
from gradpath.workflows.runs import RunBusy, RunStore
from gradpath.workflows.schemas import WorkflowInput

router = APIRouter(prefix="/api", tags=["assist"], dependencies=[Depends(require_model_routes)])


@router.post("/assist", response_model=AssistResponse)
def assist(
    body: AssistRequest,
    retrieval: Annotated[RetrievalService, Depends(get_retrieval)],
    fast: Annotated[BaseChatModel, Depends(get_extraction_model)],
    smart: Annotated[BaseChatModel, Depends(get_answer_model)],
    store: Annotated[RunStore, Depends(get_run_store)],
) -> AssistResponse:
    """Route, then run the chosen path under that path's concurrency cap: the routing call and
    a RAG answer share the chat cap. The workflow starts in the background (T-016): it takes the
    career cap (one at a time) for the whole run, and the response carries the run id to poll."""
    settings = get_settings()
    start = time.monotonic()
    decision: RouteDecision | None = None
    response: AssistResponse | None = None
    error: str | None = None
    # Known limit (TASKS, Milestone 7): if a workflow is already running, a request routed to
    # the workflow spends its routing call before the career cap answers 503. Per-IP limits
    # come with auth before deploy.
    try:
        with limits.slot(limits.CHAT):
            decision = decide(body, fast)
            if not (decision.route == "agentic_workflow" and decision.action == "run"):
                response = respond(
                    body, decision, retrieval=retrieval, fast_llm=fast, smart_llm=smart,
                    settings=settings,
                )  # fmt: skip
        if response is None:
            # The route table only allows a workflow run with both inputs attached; check
            # anyway (not `assert`, which `python -O` removes).
            if body.job_description is None or body.profile is None:
                raise RuntimeError("workflow route chosen without both inputs")
            data = WorkflowInput(
                job_description=body.job_description,
                profile=body.profile,
                corrections=list(body.corrections),
            )
            try:
                run_id = store.start(
                    data,
                    context=WorkflowContext(retrieval=retrieval, fast_llm=fast, smart_llm=smart),
                    settings=settings,
                )
            except RunBusy:
                raise HTTPException(status_code=503, detail=CAREER_BUSY) from None
            response = AssistResponse(decision=decision, outcome="started", run_id=run_id)
        return response
    except HTTPException as exc:
        error = "busy" if exc.status_code == 503 else f"http_{exc.status_code}"
        raise
    except Exception as exc:
        error = type(exc).__name__
        raise
    finally:
        route_log.record(
            route_log.log_path(settings),
            route_log_entry(decision, response, time.monotonic() - start, error),
        )

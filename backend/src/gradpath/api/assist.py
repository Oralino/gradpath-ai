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
from gradpath.api.deps import get_answer_model, get_extraction_model, get_retrieval
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

router = APIRouter(prefix="/api", tags=["assist"])


@router.post("/assist", response_model=AssistResponse)
def assist(
    body: AssistRequest,
    retrieval: Annotated[RetrievalService, Depends(get_retrieval)],
    fast: Annotated[BaseChatModel, Depends(get_extraction_model)],
    smart: Annotated[BaseChatModel, Depends(get_answer_model)],
) -> AssistResponse:
    """Route, then run the chosen path under that path's concurrency cap: the routing call and
    a RAG answer share the chat cap; a workflow run takes the career cap (one at a time)."""
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
            with limits.slot(limits.CAREER, CAREER_BUSY):
                response = respond(
                    body, decision, retrieval=retrieval, fast_llm=fast, smart_llm=smart,
                    settings=settings,
                )  # fmt: skip
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

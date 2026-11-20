"""FastAPI application. Run from `backend/`: uv run uvicorn gradpath.api.main:app --reload"""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anthropic
import pydantic
import voyageai.error
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from langgraph.errors import GraphRecursionError

from gradpath.api.assist import router as assist_router
from gradpath.api.career import router as career_router
from gradpath.api.chat import router as chat_router
from gradpath.api.jobs import router as jobs_router
from gradpath.api.profile import router as profile_router
from gradpath.api.runs import router as runs_router
from gradpath.config import get_settings
from gradpath.providers import ClaudeCodeError
from gradpath.retrieval import get_retrieval_service
from gradpath.tracing import configure_tracing, flush

log = logging.getLogger(__name__)

LLM_DOWN = "The language model is unavailable. Try again later."
LLM_INVALID = "The language model returned an invalid response. Try again."
SEARCH_LIMITED = "Search is rate limited on the free tier. Try again in a minute."
SEARCH_DOWN = "Search is unavailable. Try again later."
WORKFLOW_LIMIT = "The preparation workflow stopped at its step limit. Try again."


def _error_handler(status: int, detail: str):
    """Handler that logs the exception server-side and returns a fixed message.

    Used by `create_app`; the response never carries exception text, keys or prompts.
    """

    async def handler(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, pydantic.ValidationError):
            # Its message quotes the model's reply, which can echo posting or profile text.
            log.error(
                "%s on %s (%d errors)", type(exc).__name__, request.url.path, exc.error_count()
            )
        elif isinstance(exc, (ClaudeCodeError, anthropic.APIError)):
            # Their messages can carry model or SDK text, which can quote a resume or profile
            # (T-014): log the type only, no message or traceback.
            log.error("%s on %s", type(exc).__name__, request.url.path)
        else:
            log.error("%s on %s", type(exc).__name__, request.url.path, exc_info=exc)
        return JSONResponse({"detail": detail}, status_code=status)

    return handler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the retrieval service once per process and close it on shutdown.

    Qdrant's local (file) mode allows one open client per folder, so routes share this one
    instead of creating their own. Tests set `app.state.retrieval` themselves and skip this.
    Tracing is decided here, once per process (see `tracing.py`).
    """
    configure_tracing(get_settings())
    if getattr(app.state, "retrieval", None) is None:
        app.state.retrieval = get_retrieval_service()
    try:
        yield
    finally:
        try:
            app.state.retrieval.store.client.close()
        finally:
            flush()


def create_app(*, use_lifespan: bool = True) -> FastAPI:
    """Build the app; tests pass `use_lifespan=False` and provide their own dependencies."""
    app = FastAPI(
        title="GradPath AI",
        version="0.1.0",
        summary="Adaptive RAG + agentic career preparation for new-grad engineers.",
        lifespan=lifespan if use_lifespan else None,
    )
    # Subclasses are matched first (voyageai.error.RateLimitError before VoyageError).
    for exc_type, status, detail in [
        (ClaudeCodeError, 502, LLM_DOWN),
        (anthropic.APIError, 502, LLM_DOWN),
        (voyageai.error.RateLimitError, 429, SEARCH_LIMITED),
        (voyageai.error.VoyageError, 503, SEARCH_DOWN),
        (pydantic.ValidationError, 502, LLM_INVALID),
        (json.JSONDecodeError, 502, LLM_INVALID),
        # Anything not listed (a guard error, a missing service) gets FastAPI's default 500,
        # "Internal Server Error", which carries no exception text either.
        (GraphRecursionError, 500, WORKFLOW_LIMIT),
    ]:
        app.add_exception_handler(exc_type, _error_handler(status, detail))
    app.include_router(chat_router)
    app.include_router(jobs_router)
    app.include_router(career_router)
    app.include_router(assist_router)
    app.include_router(profile_router)
    app.include_router(runs_router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, str]:
        s = get_settings()
        return {"status": "ok", "llm_provider": s.llm_provider, "app_mode": s.app_mode}

    return app


app = create_app()

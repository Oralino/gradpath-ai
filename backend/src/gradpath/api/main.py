"""FastAPI application. Run from `backend/`: uv run uvicorn gradpath.api.main:app --reload"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from gradpath.api.chat import router as chat_router
from gradpath.config import get_settings
from gradpath.retrieval import get_retrieval_service


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the retrieval service once per process and close it on shutdown.

    Qdrant's local (file) mode allows one open client per folder, so routes share this one
    instead of creating their own. Tests set `app.state.retrieval` themselves and skip this.
    """
    if getattr(app.state, "retrieval", None) is None:
        app.state.retrieval = get_retrieval_service()
    try:
        yield
    finally:
        app.state.retrieval.store.client.close()


def create_app(*, use_lifespan: bool = True) -> FastAPI:
    """Build the app; tests pass `use_lifespan=False` and provide their own dependencies."""
    app = FastAPI(
        title="GradPath AI",
        version="0.1.0",
        summary="Adaptive RAG + agentic career preparation for new-grad engineers.",
        lifespan=lifespan if use_lifespan else None,
    )
    app.include_router(chat_router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, str]:
        s = get_settings()
        return {"status": "ok", "llm_provider": s.llm_provider, "app_mode": s.app_mode}

    return app


app = create_app()

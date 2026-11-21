"""FastAPI dependencies: the shared retrieval service, the chat model, the demo recordings, and
the mode guard on routes that call models.

Routes depend on these functions (not on globals), so tests swap in fakes with
`app.dependency_overrides`.
"""

from fastapi import HTTPException, Request
from langchain_core.language_models.chat_models import BaseChatModel

from gradpath.config import get_settings
from gradpath.demo import DemoLibrary
from gradpath.providers import get_chat_model
from gradpath.retrieval import RetrievalService

MODEL_ROUTES_OFF = "This site runs in demo mode: browse the recorded examples instead."


def require_model_routes() -> None:
    """Router-level guard on every route that calls a model or Voyage (chat, jobs, career, runs,
    assist, profile). Deny by default: only `APP_MODE=local` (the owner's machine and credentials)
    passes. Demo never does; live opens here once visitor keys are wired in (T-018 step 4).
    Runs before the route's other dependencies and body checks, so a refused request builds
    no model and touches no retrieval."""
    if get_settings().app_mode != "local":
        raise HTTPException(status_code=403, detail=MODEL_ROUTES_OFF)


def get_retrieval(request: Request) -> RetrievalService:
    """The retrieval service opened once at startup (see `main.lifespan`)."""
    return request.app.state.retrieval


def get_demo_library(request: Request) -> DemoLibrary:
    """The recordings loaded once at startup (see `main.lifespan`)."""
    return request.app.state.demo


def get_answer_model() -> BaseChatModel:
    """The "smart" tier model (Sonnet by default) for writing grounded answers."""
    return get_chat_model("smart")


def get_extraction_model() -> BaseChatModel:
    """The "fast" tier model (Haiku by default) for extraction and routing."""
    return get_chat_model("fast")

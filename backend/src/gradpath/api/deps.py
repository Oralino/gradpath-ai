"""FastAPI dependencies: the shared retrieval service and the chat model.

Routes depend on these functions (not on globals), so tests swap in fakes with
`app.dependency_overrides`.
"""

from fastapi import Request
from langchain_core.language_models.chat_models import BaseChatModel

from gradpath.providers import get_chat_model
from gradpath.retrieval import RetrievalService


def get_retrieval(request: Request) -> RetrievalService:
    """The retrieval service opened once at startup (see `main.lifespan`)."""
    return request.app.state.retrieval


def get_answer_model() -> BaseChatModel:
    """The "smart" tier model (Sonnet by default) for writing grounded answers."""
    return get_chat_model("smart")

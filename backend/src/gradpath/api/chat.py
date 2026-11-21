"""`POST /api/chat`: a focused question answered by the traditional RAG path."""

from typing import Annotated

from fastapi import APIRouter, Depends
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, ConfigDict, Field

from gradpath.api import limits
from gradpath.api.deps import get_answer_model, get_retrieval, require_model_routes
from gradpath.api.ratelimit import limit
from gradpath.rag import ChatAnswer, answer_question
from gradpath.retrieval import RetrievalService

router = APIRouter(prefix="/api", tags=["chat"], dependencies=[Depends(require_model_routes)])


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown fields are a 422, not silently dropped
    question: str = Field(min_length=3, max_length=2000, description="A focused question.")


@router.post("/chat", response_model=ChatAnswer, dependencies=[Depends(limit("model"))])
def chat(
    body: ChatRequest,
    retrieval: Annotated[RetrievalService, Depends(get_retrieval)],
    llm: Annotated[BaseChatModel, Depends(get_answer_model)],
) -> ChatAnswer:
    """Answer from the knowledge base with citations, or say it isn't covered.

    A plain `def` route: FastAPI runs it in a worker thread, so the blocking Voyage/Qdrant calls
    and the model call don't stall the server's event loop. At most 2 at a time (`limits`).
    """
    with limits.slot(limits.CHAT):
        return answer_question(body.question.strip(), retrieval, llm)

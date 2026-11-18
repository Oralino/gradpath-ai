"""Retrieval: the single search path shared by traditional RAG and the agentic workflow."""

from gradpath.retrieval.service import (
    Evidence,
    RetrievalResult,
    RetrievalService,
    get_retrieval_service,
)

__all__ = ["Evidence", "RetrievalResult", "RetrievalService", "get_retrieval_service"]

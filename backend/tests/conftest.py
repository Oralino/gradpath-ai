"""Shared test helpers: a predictable keyword embedding and a tiny in-memory knowledge base."""

import math

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient

from gradpath.ingestion.index import rebuild_index
from gradpath.retrieval import RetrievalService

VOCAB = ["sql", "index", "http", "status", "git", "branch"]


class KeywordEmbeddings(Embeddings):
    """Bag-of-keywords vectors, so cosine scores are predictable in tests (no Voyage)."""

    def _vec(self, text: str) -> list[float]:
        words = text.lower().replace("?", " ").split()
        v = [float(words.count(w)) for w in VOCAB] + [0.01]  # tiny constant: never a zero vector
        norm = math.sqrt(sum(x * x for x in v))
        return [x / norm for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


def kb_doc(chunk_id: str, text: str, document_id: str, collection: str) -> Document:
    return Document(
        page_content=text,
        metadata={
            "chunk_id": chunk_id,
            "document_id": document_id,
            "title": document_id.title(),
            "section": "Intro > Basics",
            "source_url": f"https://example.org/{document_id}",
            "collection": collection,
        },
    )


KB_DOCS = [
    kb_doc("pg:0:0", "sql index index", "pg", "backend_engineering"),
    kb_doc("pg:0:1", "sql index", "pg", "backend_engineering"),
    kb_doc("pg:0:2", "sql sql index", "pg", "backend_engineering"),
    kb_doc("sqlite:0:0", "index sql", "sqlite", "backend_engineering"),
    kb_doc("mdn:0:0", "http status status", "mdn", "technical_fundamentals"),
    kb_doc("git:0:0", "git branch branch", "git", "career_resources"),
]


@pytest.fixture
def kb_service() -> RetrievalService:
    """A RetrievalService over KB_DOCS (in-memory Qdrant, k=3, threshold 0.5)."""
    client = QdrantClient(":memory:")
    rebuild_index(client, "kb", KB_DOCS, KeywordEmbeddings())
    return RetrievalService(client, "kb", KeywordEmbeddings(), k=3, min_score=0.5)


@pytest.fixture(autouse=True)
def _local_mode(monkeypatch):
    """API tests run in local mode (model routes on), whatever `.env` or CI sets. Demo and live
    tests patch `gradpath.api.deps.get_settings` again themselves."""
    from gradpath.api import deps
    from gradpath.config import Settings

    monkeypatch.setattr(deps, "get_settings", lambda: Settings(_env_file=None, app_mode="local"))


@pytest.fixture(autouse=True)
def _fresh_rate_limits(monkeypatch):
    """Rate limits start empty and off (local mode) in every test; `test_rate_limits.py` turns
    them on itself."""
    from gradpath.api import ratelimit
    from gradpath.config import Settings

    ratelimit.LIMITER.reset()
    monkeypatch.setattr(
        ratelimit, "get_settings", lambda: Settings(_env_file=None, app_mode="local")
    )
    yield
    ratelimit.LIMITER.reset()


@pytest.fixture(autouse=True)
def _no_tracing():
    """Tests never send traces, even if the developer's shell sets LANGSMITH_TRACING=true."""
    import langsmith

    langsmith.configure(client=None, enabled=False)
    yield
    langsmith.configure(client=None, enabled=False)


def placeholder_nodes(**real):
    """A workflow NodeSet whose model/Voyage nodes are placeholders returning valid empty output,
    so graph tests need no services. Pass real nodes (or test doubles) as keyword arguments."""
    from gradpath.workflows import NodeSet
    from gradpath.workflows.schemas import Critique, JobSummary

    placeholders = {
        "analyze_job": lambda s: {
            "job": JobSummary(title="", seniority="unknown", responsibilities=[], requirements=[])
        },
        "retrieve_knowledge": lambda s: {"knowledge": []},
        "analyze_gaps": lambda s: {"gaps": []},
        "plan_roadmap": lambda s: {"roadmap": []},
        "interview_questions": lambda s: {"interview_questions": []},
        "evaluate": lambda s: {"critique": Critique(passed=True)},
        "revise": lambda s: {"roadmap": s.get("roadmap", [])},
    }
    return NodeSet(**{**placeholders, **real})

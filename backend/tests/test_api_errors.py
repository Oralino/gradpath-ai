"""API error mapping: provider and search failures become clean 5xx/429 with fixed messages."""

import json

import anthropic
import httpx
import pydantic
import pytest
from conftest import plain
from fastapi.testclient import TestClient
from voyageai.error import AuthenticationError, RateLimitError

from gradpath.api.deps import get_answer_model, get_extraction_model, get_retrieval
from gradpath.api.main import create_app
from gradpath.providers import ClaudeCodeError, FakeChatModel
from gradpath.retrieval import RetrievalService


class Boom:
    """Stands in for the chat model: any use raises `exc`."""

    def __init__(self, exc: Exception):
        self.exc = exc

    def __getattr__(self, name: str):
        raise self.exc


class _Schema(pydantic.BaseModel):
    x: int


def _validation_error() -> pydantic.ValidationError:
    try:
        _Schema(x="not a number")  # type: ignore[arg-type]
    except pydantic.ValidationError as e:
        return e
    raise AssertionError


def _anthropic_error() -> anthropic.APIError:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIError("secret-key-sk-123 leaked", req, body=None)


LLM_DOWN = "The language model is unavailable. Try again later."
LLM_INVALID = "The language model returned an invalid response. Try again."
CASES = [
    (ClaudeCodeError("prompt text and sk-secret"), 502, LLM_DOWN),
    (_anthropic_error(), 502, LLM_DOWN),
    (
        RateLimitError("sk-secret"),
        429,
        "Search is rate limited on the free tier. Try again in a minute.",
    ),
    (AuthenticationError("sk-secret"), 503, "Search is unavailable. Try again later."),
    (_validation_error(), 502, LLM_INVALID),
    (json.JSONDecodeError("bad sk-secret", "doc", 0), 502, LLM_INVALID),
]


def make_client(kb_service: RetrievalService, model) -> TestClient:
    app = create_app(use_lifespan=False)
    app.dependency_overrides[get_retrieval] = lambda: kb_service
    app.dependency_overrides[get_answer_model] = lambda: model
    app.dependency_overrides[get_extraction_model] = lambda: FakeChatModel()
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(("exc", "status", "detail"), CASES)
def test_errors_map_to_clean_responses(kb_service, exc, status, detail):
    client = make_client(kb_service, Boom(exc))
    resp = client.post("/api/chat", json={"question": "what is a sql index"})
    assert resp.status_code == status
    assert plain(resp.json()) == {"detail": detail}
    assert "secret" not in resp.text


def test_analyze_rejects_oversized_description(kb_service):
    client = make_client(kb_service, FakeChatModel())
    resp = client.post("/api/jobs/analyze", json={"job_description": "x" * 20_001})
    assert resp.status_code == 422


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/chat", {"question": "what is a sql index"}),
        ("/api/jobs/analyze", {"job_description": "Backend engineer, Python and SQL. " * 3}),
        ("/api/profile/from-resume", {"resume_text": "Python developer with SQL experience. " * 5}),
    ],
)
def test_request_bodies_reject_unknown_fields(kb_service, path, body):
    # Release checklist: every request body forbids extra fields (T-017).
    client = make_client(kb_service, FakeChatModel())
    resp = client.post(path, json={**body, "api_key": "sk-should-not-be-accepted"})
    assert resp.status_code == 422
    assert [e["type"] for e in resp.json()["detail"]] == ["extra_forbidden"]

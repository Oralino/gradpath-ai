"""`POST /api/career/prepare` and the workflow CLI report: fake models, in-memory knowledge base."""

import pytest
from fastapi.testclient import TestClient
from langgraph.errors import GraphRecursionError
from test_workflow_planning import (
    EXTRACTION,
    GAPS_REPLY,
    JD,
    QUESTIONS,
    ROADMAP_FULL,
)

from gradpath.api import career as career_module
from gradpath.api import limits
from gradpath.api.deps import get_answer_model, get_extraction_model, get_retrieval
from gradpath.api.main import create_app
from gradpath.config import Settings
from gradpath.providers import FakeChatModel
from gradpath.workflows import graph as graph_module
from gradpath.workflows.cli import report
from gradpath.workflows.graph import MODEL_RETRY
from gradpath.workflows.schemas import MAX_MODEL_TEXT_CHARS, CritiqueIssue

PROFILE = {"skills": ["SQL (SQLite)"], "weekly_hours": 8, "timeline_weeks": 6}


@pytest.fixture(autouse=True)
def _fast_retry(monkeypatch):
    monkeypatch.setattr(graph_module, "MODEL_RETRY", MODEL_RETRY._replace(initial_interval=0.0))


def client(kb_service, fast, smart) -> TestClient:
    app = create_app(use_lifespan=False)
    app.dependency_overrides[get_retrieval] = lambda: kb_service
    app.dependency_overrides[get_extraction_model] = lambda: fast
    app.dependency_overrides[get_answer_model] = lambda: smart
    return TestClient(app)


def happy(kb_service) -> TestClient:
    fast = FakeChatModel(responses=[EXTRACTION, QUESTIONS, {"issues": []}])
    smart = FakeChatModel(responses=[GAPS_REPLY, ROADMAP_FULL])
    return client(kb_service, fast, smart)


def test_prepare_returns_the_full_result(kb_service):
    body = {"job_description": JD, "profile": PROFILE, "corrections": ["I used HTTP status codes"]}
    resp = happy(kb_service).post("/api/career/prepare", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "complete"
    assert {g["requirement_id"] for g in data["gaps"]} == {"r-1", "r-2", "r-3", "r-4"}
    assert [i["order"] for i in data["roadmap"]] == [1, 2]
    assert data["interview_questions"][0]["requirement_id"] == "r-2"
    assert data["node_log"][-1] == "finalize"


@pytest.mark.parametrize(
    "body",
    [
        {"job_description": JD, "profile": PROFILE, "max_revisions": 3},  # can't set the limit
        {"job_description": JD, "profile": {**PROFILE, "salary": 1}},
        {"job_description": "too short", "profile": PROFILE},
        {"job_description": JD, "profile": PROFILE, "corrections": ["c"] * 11},
        {"job_description": JD},
    ],
)
def test_bad_requests_are_rejected_before_any_model_call(kb_service, body):
    fast, smart = FakeChatModel(), FakeChatModel()
    resp = client(kb_service, fast, smart).post("/api/career/prepare", json=body)
    assert resp.status_code == 422
    assert fast.calls == [] and smart.calls == []


def test_revision_limit_comes_from_settings(kb_service, monkeypatch):
    seen = {}
    real = career_module.run_workflow

    def spy(*args, **kwargs):
        seen["max_revisions"] = kwargs["max_revisions"]
        return real(*args, **kwargs)

    monkeypatch.setattr(career_module, "run_workflow", spy)
    monkeypatch.setattr(
        career_module, "get_settings", lambda: Settings(_env_file=None, workflow_max_revisions=0)
    )
    resp = happy(kb_service).post(
        "/api/career/prepare", json={"job_description": JD, "profile": PROFILE}
    )
    assert resp.status_code == 200 and seen["max_revisions"] == 0


def test_step_limit_gives_a_fixed_message(kb_service, monkeypatch):
    def boom(*a, **k):
        raise GraphRecursionError("internal details sk-secret")

    monkeypatch.setattr(career_module, "run_workflow", boom)
    resp = happy(kb_service).post(
        "/api/career/prepare", json={"job_description": JD, "profile": PROFILE}
    )
    assert resp.status_code == 500
    assert resp.json() == {
        "detail": "The preparation workflow stopped at its step limit. Try again."
    }


def test_invalid_model_output_twice_gives_502_without_echoing_it(kb_service):
    leaked = "MODEL REPLY WITH POSTING TEXT"
    fast = FakeChatModel(responses=[leaked])
    resp = client(kb_service, fast, FakeChatModel()).post(
        "/api/career/prepare", json={"job_description": JD, "profile": PROFILE}
    )
    assert resp.status_code == 502
    assert leaked not in resp.text
    assert len(fast.calls) == 2  # one retry, then the clean error


def test_long_model_text_is_truncated_not_rejected():
    issue = CritiqueIssue(code="x", message="m" * 5000, severity="minor")
    assert len(issue.message) == MAX_MODEL_TEXT_CHARS and issue.message.endswith("…")


def test_cli_report_shows_every_section(kb_service):
    fast = FakeChatModel(responses=[EXTRACTION, QUESTIONS, {"issues": []}])
    smart = FakeChatModel(responses=[GAPS_REPLY, ROADMAP_FULL])
    from gradpath.workflows import UserProfile, WorkflowContext, run_workflow

    ctx = WorkflowContext(retrieval=kb_service, fast_llm=fast, smart_llm=smart)
    result = run_workflow(JD, UserProfile(**PROFILE), context=ctx, max_revisions=1)
    text = report(result, 12.0)
    for part in ("status: complete", "Gaps:", "Roadmap:", "Interview questions:", "estimate"):
        assert part in text
    assert "(no source in the knowledge base)" in text  # item 2 (r-2) cites nothing


def test_second_concurrent_run_gets_503(kb_service, monkeypatch):
    """While one run holds the slot, another request is refused at once (no model call)."""
    assert limits.CAREER.acquire(blocking=False)
    try:
        fast = FakeChatModel()
        resp = client(kb_service, fast, FakeChatModel()).post(
            "/api/career/prepare", json={"job_description": JD, "profile": PROFILE}
        )
    finally:
        limits.CAREER.release()
    assert resp.status_code == 503 and "already in progress" in resp.json()["detail"]
    assert fast.calls == []


def test_slot_is_released_after_a_failed_run(kb_service):
    bad = client(kb_service, FakeChatModel(responses=["not json"]), FakeChatModel())
    assert (
        bad.post(
            "/api/career/prepare", json={"job_description": JD, "profile": PROFILE}
        ).status_code
        == 502
    )
    ok = happy(kb_service).post(
        "/api/career/prepare", json={"job_description": JD, "profile": PROFILE}
    )
    assert ok.status_code == 200


def test_claude_code_failure_gives_a_fixed_502(kb_service):
    from gradpath.providers import ClaudeCodeError

    class Failing(FakeChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self.calls.append(list(messages))
            raise ClaudeCodeError("prompt text and sk-secret")

    fast = Failing()
    resp = client(kb_service, fast, FakeChatModel()).post(
        "/api/career/prepare", json={"job_description": JD, "profile": PROFILE}
    )
    assert resp.status_code == 502 and "sk-secret" not in resp.text
    assert len(fast.calls) == 2  # retried once


@pytest.mark.parametrize(
    "path,limit,body",
    [
        ("/api/chat", "CHAT", {"question": "What is an index?"}),
        ("/api/jobs/analyze", "JOBS", {"job_description": JD}),
    ],
)
def test_other_model_routes_are_capped(kb_service, path, limit, body):
    sem = getattr(limits, limit)
    held = []
    while sem.acquire(blocking=False):  # take every slot
        held.append(1)
    try:
        fast, smart = FakeChatModel(), FakeChatModel()
        resp = client(kb_service, fast, smart).post(path, json=body)
    finally:
        for _ in held:
            sem.release()
    assert resp.status_code == 503 and fast.calls == [] and smart.calls == []


def test_retry_log_keeps_the_type_but_not_the_reply(caplog, kb_service):
    import logging

    from gradpath.workflows.graph import RETRY_LOGGER

    leaked = "MODEL REPLY WITH POSTING TEXT"
    fast = FakeChatModel(responses=[leaked])
    with caplog.at_level(logging.INFO, logger=RETRY_LOGGER):
        client(kb_service, fast, FakeChatModel()).post(
            "/api/career/prepare", json={"job_description": JD, "profile": PROFILE}
        )
    retries = [r for r in caplog.records if r.name == RETRY_LOGGER]
    assert retries, "langgraph's retry logger name changed: update RETRY_LOGGER"
    assert all(leaked not in r.getMessage() and r.exc_info is None for r in retries)
    assert "ValidationError" in retries[0].getMessage()
    assert all(leaked not in r.getMessage() for r in caplog.records)


def test_cli_out_only_saves_real_profiles_under_private(tmp_path):
    from gradpath.config import REPO_ROOT
    from gradpath.workflows import UserProfile
    from gradpath.workflows.cli import out_allowed

    real = UserProfile(skills=["Python"])
    sample = UserProfile(profile_id="sample-new-grad-v1", skills=["Python"])
    assert not out_allowed(REPO_ROOT / "demo_runs" / "x.json", real)
    assert not out_allowed(tmp_path / "x.json", real)
    assert out_allowed(REPO_ROOT / "private" / "runs" / "x.json", real)
    assert out_allowed(REPO_ROOT / "demo_runs" / "x.json", sample)

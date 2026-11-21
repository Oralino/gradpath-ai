"""Live mode with a visitor's own Anthropic key (T-018 step 5, always-hard area).

No real model call is ever made: the key is a fake with the right shape, and the routes' work is
replaced by spies or by simulated Anthropic errors. What is checked is where the key goes: into
the model client, and nowhere else (not logs, responses, run records or other visitors' runs).
"""

import logging
import time

import anthropic
import httpx
import pytest
from conftest import placeholder_nodes
from fastapi.testclient import TestClient
from langchain_anthropic import ChatAnthropic
from pydantic import SecretStr
from test_runs import CTX, SETTINGS, data

from gradpath.api import chat as chat_module
from gradpath.api import deps, limits
from gradpath.api import main as main_module
from gradpath.api.deps import KEY_HEADER, KEY_NEEDED, get_retrieval, run_owner
from gradpath.api.main import KEY_LIMITED, KEY_REFUSED, check_live_settings, create_app
from gradpath.api.runs import get_run_store
from gradpath.config import Settings
from gradpath.providers import factory
from gradpath.rag import ChatAnswer
from gradpath.workflows.runs import RunStore

KEY_A = "sk-ant-api03-" + "A" * 40
KEY_B = "sk-ant-api03-" + "B" * 40
LIVE = Settings(_env_file=None, app_mode="live", llm_provider="anthropic_api")
ANSWER = ChatAnswer(
    question="What is an index?", status="answered", answer="It helps.", citations=[]
)


@pytest.fixture(autouse=True)
def _no_host_redirect(monkeypatch):
    """Start every test with no Anthropic host override (a developer shell, Claude Code's
    included, may set one; live mode refuses to start with it)."""
    for var in main_module.REDIRECT_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def live(monkeypatch, kb_service):
    """A live-mode app: settings patched where the guard and the model factory read them."""
    monkeypatch.setattr(deps, "get_settings", lambda: LIVE)
    monkeypatch.setattr(factory, "get_settings", lambda: LIVE)
    app = create_app(use_lifespan=False)
    app.dependency_overrides[get_retrieval] = lambda: kb_service
    return app


def spy_answer(monkeypatch):
    """Replace the RAG answer with a spy that records the model it was given."""
    seen = []

    def answer(question, retrieval, llm):
        seen.append(llm)
        return ANSWER

    monkeypatch.setattr(chat_module, "answer_question", answer)
    return seen


def status_error(cls, status: int):
    """An Anthropic SDK error as the client raises it (with a response)."""
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("refused", response=httpx.Response(status, request=request), body=None)


# --- the key reaches the model client, and only it ----------------------------------------------


def test_the_visitor_key_builds_the_model(live, monkeypatch):
    seen = spy_answer(monkeypatch)
    resp = TestClient(live).post(
        "/api/chat", json={"question": "What is an index?"}, headers={KEY_HEADER: f"  {KEY_A} "}
    )
    assert resp.status_code == 200
    (llm,) = seen
    assert isinstance(llm, ChatAnthropic)
    assert llm.anthropic_api_key.get_secret_value() == KEY_A  # stripped, used as given
    assert KEY_A not in resp.text


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "   ",
        "sk-proj-" + "x" * 40,
        "sk-ant-short",
        "sk-ant-" + "x" * 201,
        "sk-ant-" + "x" * 30 + "!",
        "sk-ant-" + "x" * 30 + " extra",
    ],
)
def test_a_missing_or_malformed_key_is_refused_before_any_model(live, monkeypatch, header):
    seen = spy_answer(monkeypatch)
    headers = {} if header is None else {KEY_HEADER: header}
    resp = TestClient(live).post("/api/chat", json={"question": "What?"}, headers=headers)
    assert (resp.status_code, resp.json()) == (401, {"detail": KEY_NEEDED})
    assert seen == []


def test_the_key_in_the_wrong_place_is_never_used(live, monkeypatch):
    """A key sent as a query parameter or another header doesn't count (and isn't echoed)."""
    spy_answer(monkeypatch)
    c = TestClient(live)
    resp = c.post(
        f"/api/chat?key={KEY_A}", json={"question": "What?"}, headers={"X-Api-Key": KEY_A}
    )
    assert resp.status_code == 401 and KEY_A not in resp.text


def test_local_mode_ignores_the_header(monkeypatch):
    local = Settings(_env_file=None, app_mode="local", llm_provider="fake")
    monkeypatch.setattr(deps, "get_settings", lambda: local)
    monkeypatch.setattr(factory, "get_settings", lambda: local)
    assert deps.get_answer_model(deps.visitor_key(request_with(KEY_A))).__class__.__name__ == (
        "FakeChatModel"
    )


def test_non_ascii_header_bytes_are_refused(monkeypatch):
    """A raw client can send bytes httpx won't; Starlette decodes them as latin-1."""
    monkeypatch.setattr(deps, "get_settings", lambda: LIVE)
    from fastapi import HTTPException, Request

    raw = Request(
        {"type": "http", "headers": [(b"x-anthropic-key", b"sk-ant-" + bytes([0xE9]) * 30)]}
    )
    with pytest.raises(HTTPException) as err:
        deps.visitor_key(raw)
    assert err.value.status_code == 401


def request_with(key: str | None):
    from fastapi import Request

    headers = [] if key is None else [(KEY_HEADER.lower().encode(), key.encode())]
    return Request({"type": "http", "headers": headers})


# --- refused keys and the visitor's own limits ----------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "status", "detail"),
    [
        (status_error(anthropic.AuthenticationError, 401), 401, KEY_REFUSED),
        (status_error(anthropic.PermissionDeniedError, 403), 401, KEY_REFUSED),
        (status_error(anthropic.RateLimitError, 429), 429, KEY_LIMITED),
    ],
)
def test_a_refused_key_gets_a_fixed_message(live, monkeypatch, caplog, exc, status, detail):
    def refuse(question, retrieval, llm):
        raise exc

    monkeypatch.setattr(chat_module, "answer_question", refuse)
    with caplog.at_level(logging.DEBUG):
        resp = TestClient(live).post(
            "/api/chat", json={"question": "What is an index?"}, headers={KEY_HEADER: KEY_A}
        )
    assert (resp.status_code, resp.json()) == (status, {"detail": detail})
    assert type(exc).__name__ in caplog.text
    assert KEY_A not in caplog.text and KEY_A not in resp.text


# --- the key never reaches logs ---------------------------------------------------------------


def test_a_full_request_logs_nothing_with_the_key(live, monkeypatch, caplog):
    spy_answer(monkeypatch)
    with caplog.at_level(logging.DEBUG):
        TestClient(live).post(
            "/api/chat", json={"question": "What is an index?"}, headers={KEY_HEADER: KEY_A}
        )
        TestClient(live).post("/api/chat", json={"question": "What?"}, headers={KEY_HEADER: "bad"})
    assert KEY_A not in caplog.text and "AAAAAAAAAA" not in caplog.text


def test_the_model_repr_masks_the_key():
    llm = factory.get_chat_model("smart", settings=LIVE, api_key=SecretStr(KEY_A))
    assert KEY_A not in repr(llm) and KEY_A not in str(llm.model_dump())


# --- runs belong to the key that started them --------------------------------------------------


@pytest.fixture
def live_runs(live):
    store = RunStore(limits.CAREER)
    live.dependency_overrides[get_run_store] = lambda: store
    return TestClient(live), store


def finish(store, run_id: str, owner: str | None = None, timeout_s: float = 10.0):
    """Poll the store until the run is no longer running (as its owner)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status = store.get(run_id, owner)
        if status is not None and status.status != "running":
            return status
        time.sleep(0.01)
    raise AssertionError("run did not finish")


def started_run(store, key: str | None) -> str:
    """A finished run in `store`, owned by `key` (started directly, placeholder nodes, no model)."""
    owner = run_owner(SecretStr(key)) if key else None
    run_id = store.start(
        data(), context=CTX, settings=SETTINGS, impl=placeholder_nodes(), owner=owner
    )
    finish(store, run_id, owner)
    return run_id


def test_a_run_is_visible_only_with_the_key_that_started_it(live_runs):
    c, store = live_runs
    run_id = started_run(store, KEY_A)
    url = f"/api/career/runs/{run_id}"
    assert c.get(url, headers={KEY_HEADER: KEY_A}).status_code == 200
    other = c.get(url, headers={KEY_HEADER: KEY_B})
    unknown = c.get(
        "/api/career/runs/00000000-0000-4000-8000-000000000000", headers={KEY_HEADER: KEY_B}
    )
    assert other.status_code == unknown.status_code == 404
    assert other.json() == unknown.json()  # a foreign run looks exactly like a missing one
    assert c.get(url).status_code == 401


def test_the_run_record_keeps_no_key(live_runs):
    _, store = live_runs
    run_id = started_run(store, KEY_A)
    record = store._runs[run_id]
    assert KEY_A not in repr(record) and record.owner == run_owner(SecretStr(KEY_A))
    assert run_owner(SecretStr(KEY_A)) != run_owner(SecretStr(KEY_B))


def test_local_runs_are_not_bound():
    assert run_owner(None) is None
    store = RunStore(limits.CAREER)
    run_id = started_run(store, None)
    assert store.get(run_id) is not None and store.get(run_id, "anything") is not None


# --- live mode only starts when no server key can be used --------------------------------------


def test_live_needs_the_api_provider_and_no_server_key(restore_logger_levels):
    check_live_settings(LIVE)  # fine
    with pytest.raises(RuntimeError, match="LLM_PROVIDER=anthropic_api"):
        check_live_settings(Settings(_env_file=None, app_mode="live", llm_provider="claude_code"))
    with pytest.raises(RuntimeError, match="must not have ANTHROPIC_API_KEY") as err:
        check_live_settings(
            Settings(_env_file=None, app_mode="live", llm_provider="anthropic_api",
                     anthropic_api_key="sk-ant-server-" + "z" * 30)
        )  # fmt: skip
    assert "zzzz" not in str(err.value)


@pytest.fixture
def restore_logger_levels():
    """Put the SDK loggers back after a test that changes their levels."""
    saved = {n: logging.getLogger(n).level for n in main_module.QUIET_IN_LIVE}
    yield
    for name, level in saved.items():
        logging.getLogger(name).setLevel(level)


def test_live_quiets_the_sdk_loggers(restore_logger_levels):
    for name in main_module.QUIET_IN_LIVE:
        logging.getLogger(name).setLevel(logging.DEBUG)
    check_live_settings(LIVE)
    assert all(logging.getLogger(n).level == logging.WARNING for n in main_module.QUIET_IN_LIVE)


@pytest.mark.parametrize("var", ["ANTHROPIC_BASE_URL", "ANTHROPIC_API_URL"])
def test_live_refuses_a_redirected_anthropic_host(monkeypatch, restore_logger_levels, var):
    monkeypatch.setenv(var, "https://collector.example.com")
    with pytest.raises(RuntimeError, match=var) as err:
        check_live_settings(LIVE)
    assert "collector" not in str(err.value)


def test_other_modes_start_without_those_checks(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://elsewhere.example.com")
    check_live_settings(Settings(_env_file=None, app_mode="local", llm_provider="claude_code"))
    check_live_settings(Settings(_env_file=None, app_mode="demo", anthropic_api_key="x"))


# --- through the routes: every model is built with the key, runs are bound -------------------


class Built(Exception):
    """Raised by the spy factory so a route stops right after building its first model."""


MODEL_POSTS = [
    ("/api/chat", {"question": "What is an index?"}),
    ("/api/jobs/analyze", {"job_description": "x" * 60}),
    ("/api/career/prepare", None),
    ("/api/career/runs", None),
    ("/api/assist", {"message": "What is an index?"}),
    ("/api/profile/from-resume", {"resume_text": "r" * 120}),
]


@pytest.mark.parametrize(("path", "body"), MODEL_POSTS)
def test_every_model_route_builds_its_models_with_the_visitor_key(live, monkeypatch, path, body):
    keys = []

    def spy(tier="smart", *, settings=None, api_key=None):
        keys.append(api_key.get_secret_value() if api_key else None)
        raise Built

    monkeypatch.setattr(deps, "get_chat_model", spy)
    payload = body if body is not None else data().model_dump()
    c = TestClient(live, raise_server_exceptions=False)
    resp = c.post(path, json=payload, headers={KEY_HEADER: KEY_A})
    assert resp.status_code == 500 and KEY_A not in resp.text
    assert keys and set(keys) == {KEY_A}


@pytest.fixture
def placeholder_runs(live_runs, monkeypatch):
    """The live app with runs that finish at once on placeholder nodes (no model call)."""
    c, store = live_runs
    real_start = store.start
    monkeypatch.setattr(
        store, "start", lambda d, **kw: real_start(d, **{**kw, "impl": placeholder_nodes()})
    )
    return c, store


def assert_bound(c, store, run_id):
    owner_a = run_owner(SecretStr(KEY_A))
    finish(store, run_id, owner_a)
    url = f"/api/career/runs/{run_id}"
    assert c.get(url, headers={KEY_HEADER: KEY_A}).json()["status"] == "done"
    foreign = c.get(url, headers={KEY_HEADER: KEY_B})
    missing = c.get(
        "/api/career/runs/00000000-0000-4000-8000-000000000000", headers={KEY_HEADER: KEY_B}
    )
    assert (foreign.status_code, foreign.json()) == (missing.status_code, missing.json())
    assert foreign.status_code == 404


def test_a_run_started_through_the_runs_route_is_bound(placeholder_runs):
    c, store = placeholder_runs
    resp = c.post("/api/career/runs", json=data().model_dump(), headers={KEY_HEADER: KEY_A})
    assert resp.status_code == 202
    assert_bound(c, store, resp.json()["run_id"])


def test_a_run_started_through_assist_is_bound(placeholder_runs, monkeypatch):
    from gradpath.api import assist as assist_module
    from gradpath.router.schemas import RouteDecision

    decision = RouteDecision(
        route="agentic_workflow", action="run", kind="job_preparation", missing=[],
        reason="Plan request.", requires_user_profile=True, requires_multi_step_workflow=True,
        decided_by="rules",
    )  # fmt: skip
    monkeypatch.setattr(assist_module, "decide", lambda body, fast: decision)
    c, store = placeholder_runs
    payload = {"message": "Make me a plan", **data().model_dump(exclude={"corrections"})}
    resp = c.post("/api/assist", json=payload, headers={KEY_HEADER: KEY_A})
    assert resp.status_code == 200 and resp.json()["outcome"] == "started"
    assert_bound(c, store, resp.json()["run_id"])

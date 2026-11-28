"""`POST /api/live/check` and error codes (T-018 step 9; behind GitHub sign-in since T-026,
always-hard area).

No real Anthropic call: `live.verify_key` is replaced by a stub that records the key it got or
raises a simulated SDK error.
"""

import logging
import re

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_rate_limits import Clock, ip, settings_for, use
from test_visitor_key import KEY_A, LOGIN, PASS

from gradpath.api import deps, live, ratelimit
from gradpath.api.deps import KEY_HEADER
from gradpath.api.main import create_app, error_codes
from gradpath.api.ratelimit import Limiter


@pytest.fixture
def checked(monkeypatch):
    """Keys `verify_key` was called with (it succeeds unless a test swaps it)."""
    seen = []
    monkeypatch.setattr(live, "verify_key", lambda key: seen.append(key.get_secret_value()))
    monkeypatch.setattr(ratelimit, "LIMITER", Limiter(clock=Clock()))
    return seen


def client(monkeypatch, kb_service=None, mode="live", **extra) -> TestClient:
    use(monkeypatch, settings_for(mode, **extra))
    monkeypatch.setattr(live, "get_settings", lambda: settings_for(mode, **extra))
    app = create_app(use_lifespan=False)
    if kb_service is not None:
        app.dependency_overrides[deps.get_retrieval] = lambda: kb_service
    return TestClient(app)


def check(c, signed_in=True, key=KEY_A, n=1):
    headers = {**ip(n)}
    if signed_in:
        headers.update(PASS)
    if key is not None:
        headers[KEY_HEADER] = key
    return c.post("/api/live/check", headers=headers)


def sdk_error(cls, status):
    request = httpx.Request("GET", "https://api.anthropic.com/v1/models")
    return cls("x", response=httpx.Response(status, request=request), body=None)


# --- the check --------------------------------------------------------------------------------


def test_a_signed_in_visitor_with_a_good_key_passes(monkeypatch, checked):
    resp = check(client(monkeypatch))
    assert resp.status_code == 200 and resp.json() == {"ok": True} and checked == [KEY_A]
    assert KEY_A not in resp.text and LOGIN not in resp.text


@pytest.mark.parametrize(
    ("signed_in", "key", "code"),
    [
        (False, KEY_A, "signin_required"),
        (False, None, "signin_required"),
        (True, None, "key_required"),
        (True, "sk-proj-" + "x" * 40, "key_required"),
    ],
)
def test_problems_are_reported_before_any_anthropic_call(
    monkeypatch, checked, signed_in, key, code
):
    resp = check(client(monkeypatch), signed_in, key)
    assert resp.status_code == 401 and resp.json()["code"] == code and checked == []


def test_an_anonymous_check_spends_no_model_limit(monkeypatch, checked):
    """T-026 review: refused before `limit("model")` counts, so anonymous calls can't use up a
    shared network's model limit; the signed-in check is still counted."""
    c = client(monkeypatch)
    for _ in range(20):
        assert check(c, signed_in=False).status_code == 401
    assert len(ratelimit.LIMITER._events) == 0
    assert check(c).status_code == 200
    assert ("model", "gh:4242") in ratelimit.LIMITER._events


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (sdk_error(anthropic.AuthenticationError, 401), 401, "key_refused"),
        (sdk_error(anthropic.PermissionDeniedError, 403), 401, "key_refused"),
        (sdk_error(anthropic.RateLimitError, 429), 429, "key_rate_limited"),
        (anthropic.APIConnectionError(request=httpx.Request("GET", "https://x")), 502,
         "llm_unavailable"),
    ],
)  # fmt: skip
def test_anthropic_refusals_map_to_fixed_answers(monkeypatch, checked, caplog, exc, status, code):
    def refuse(key):
        raise exc

    monkeypatch.setattr(live, "verify_key", refuse)
    with caplog.at_level(logging.DEBUG):
        resp = check(client(monkeypatch))
    assert (resp.status_code, resp.json()["code"]) == (status, code)
    assert KEY_A not in caplog.text and LOGIN not in caplog.text


@pytest.mark.parametrize(
    ("mode", "status", "code"), [("demo", 403, "demo_mode"), ("local", 404, "live_off")]
)
def test_only_live_mode_has_a_check(monkeypatch, checked, mode, status, code):
    resp = check(client(monkeypatch, mode=mode))
    assert (resp.status_code, resp.json()["code"]) == (status, code) and checked == []


def test_verify_key_makes_one_call_without_retries(monkeypatch):
    calls = []

    class FakeModels:
        def list(self, **kwargs):
            calls.append(kwargs)

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.models = FakeModels()

        def close(self):
            calls.append("closed")

    monkeypatch.setattr(live.anthropic, "Anthropic", FakeClient)
    live.verify_key(SecretStr(KEY_A))
    assert calls[0]["max_retries"] == 0 and calls[0]["api_key"] == KEY_A
    assert calls[1] == {"limit": 1} and calls[2] == "closed"


# --- error codes and health ---------------------------------------------------------------------


def test_every_fixed_error_message_has_a_code():
    """Every `detail=` constant raised in api/ maps to a real code (not the "error" fallback)."""
    import importlib
    from pathlib import Path

    from gradpath.api import main as main_module

    codes = error_codes()
    api_dir = Path(main_module.__file__).parent
    found = 0
    for path in api_dir.glob("*.py"):
        module = importlib.import_module(f"gradpath.api.{path.stem}")
        for name in re.findall(r"detail=([A-Z_]+)", path.read_text(encoding="utf-8")):
            value = getattr(module, name)
            assert value in codes, f"{path.name}: {name} has no code"
            found += 1
    for name in ("LLM_DOWN", "LLM_INVALID", "SEARCH_LIMITED", "SEARCH_DOWN", "WORKFLOW_LIMIT",
                 "KEY_REFUSED", "KEY_LIMITED"):  # fmt: skip
        assert getattr(main_module, name) in codes
    assert found >= 10 and all(re.fullmatch(r"[a-z_]+", c) for c in codes.values())


def test_errors_carry_a_code(monkeypatch, checked):
    demo = client(monkeypatch, mode="demo")
    assert demo.post("/api/chat", json={"question": "What?"}).json()["code"] == "demo_mode"
    assert demo.get("/api/nowhere").json() == {"detail": "Not Found", "code": "not_found"}
    local = client(monkeypatch, mode="local")
    local.app.dependency_overrides[deps.get_answer_model] = object
    local.app.dependency_overrides[deps.get_retrieval] = object
    assert local.post("/api/chat", json={"bad": 1}).json()["code"] == "validation"


@pytest.mark.parametrize("retrieval", [None, object()])
def test_health_says_whether_search_works(retrieval):
    app = create_app(use_lifespan=False)
    app.state.retrieval = retrieval
    assert TestClient(app).get("/api/health").json()["search_enabled"] is (retrieval is not None)

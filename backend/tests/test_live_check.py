"""`POST /api/live/check`, the session token and error codes (T-018 step 9, always-hard area).

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
from test_visitor_key import KEY_A, PASSCODE, spy_answer

from gradpath.api import deps, live, ratelimit
from gradpath.api.deps import KEY_HEADER, PASSCODE_HEADER
from gradpath.api.live import TOKEN_HEADER, TOKEN_TTL_S, issue_token, token_valid
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


def check(c, passcode=PASSCODE, key=KEY_A, n=1):
    headers = {**ip(n)}
    if passcode is not None:
        headers[PASSCODE_HEADER] = passcode
    if key is not None:
        headers[KEY_HEADER] = key
    return c.post("/api/live/check", headers=headers)


def sdk_error(cls, status):
    request = httpx.Request("GET", "https://api.anthropic.com/v1/models")
    return cls("x", response=httpx.Response(status, request=request), body=None)


# --- the check --------------------------------------------------------------------------------


def test_a_good_passcode_and_key_get_a_token(monkeypatch, checked):
    resp = check(client(monkeypatch))
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"token", "expires_at"} and checked == [KEY_A]
    assert re.fullmatch(r"\d+\.[0-9a-f]{64}", body["token"])
    assert KEY_A not in resp.text and PASSCODE not in resp.text


@pytest.mark.parametrize(
    ("passcode", "key", "code"),
    [
        (None, KEY_A, "passcode_required"),
        ("wrong-passcode-" + "w" * 20, KEY_A, "passcode_required"),
        (PASSCODE, None, "key_required"),
        (PASSCODE, "sk-proj-" + "x" * 40, "key_required"),
    ],
)
def test_problems_are_reported_before_any_anthropic_call(monkeypatch, checked, passcode, key, code):
    resp = check(client(monkeypatch), passcode, key)
    assert resp.status_code == 401 and resp.json()["code"] == code and checked == []


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
    assert KEY_A not in caplog.text and PASSCODE not in caplog.text


def test_wrong_passcodes_at_the_check_count_towards_the_lock(monkeypatch, checked):
    c = client(monkeypatch)
    for _ in range(5):
        check(c, passcode="nope")
    locked = check(c)
    assert locked.status_code == 429 and locked.json()["code"] == "passcode_locked"


def test_a_token_cannot_get_another_token(monkeypatch, checked):
    """Only the passcode issues tokens, so a token can't extend itself."""
    c = client(monkeypatch)
    token = check(c).json()["token"]
    resp = c.post("/api/live/check", headers={TOKEN_HEADER: token, KEY_HEADER: KEY_A, **ip(1)})
    assert resp.status_code == 401 and resp.json()["code"] == "passcode_required"


@pytest.mark.parametrize(
    ("mode", "status", "code"), [("demo", 403, "demo_mode"), ("local", 404, "live_off")]
)
def test_only_live_mode_has_a_check(monkeypatch, checked, mode, status, code):
    resp = check(client(monkeypatch, mode=mode))
    assert (resp.status_code, resp.json()["code"]) == (status, code) and checked == []


# --- the token stands in for the passcode -------------------------------------------------------


def test_the_token_replaces_the_passcode_on_model_routes(monkeypatch, checked, kb_service):
    c = client(monkeypatch, kb_service)
    spy_answer(monkeypatch)
    token = check(c).json()["token"]
    resp = c.post(
        "/api/chat", json={"question": "What is an index?"},
        headers={TOKEN_HEADER: token, KEY_HEADER: KEY_A, **ip(1)},
    )  # fmt: skip
    assert resp.status_code == 200


def test_a_bad_token_is_refused_and_counts(monkeypatch, checked, kb_service):
    c = client(monkeypatch, kb_service)
    spy_answer(monkeypatch)
    token = check(c).json()["token"]
    forged = token[:-1] + ("0" if token[-1] != "0" else "1")
    for _ in range(5):
        r = c.post("/api/chat", json={"question": "What?"},
                   headers={TOKEN_HEADER: forged, KEY_HEADER: KEY_A, **ip(1)})  # fmt: skip
        assert r.status_code == 401
    good = c.post("/api/chat", json={"question": "What?"},
                  headers={TOKEN_HEADER: token, KEY_HEADER: KEY_A, **ip(1)})  # fmt: skip
    assert good.status_code == 429  # locked like wrong passcodes


def test_tokens_expire_and_die_with_a_new_passcode_or_another_key():
    now = 1_000_000.0
    token, expires = issue_token(PASSCODE, KEY_A, now=lambda: now)
    assert expires == int(now) + TOKEN_TTL_S
    assert token_valid(token, PASSCODE, KEY_A, now=lambda: now + 10)
    assert live.token_status(token, PASSCODE, KEY_A, now=lambda: now + TOKEN_TTL_S + 1) == "expired"
    assert not token_valid(token, "a-new-passcode-" + "n" * 20, KEY_A, now=lambda: now + 10)
    assert not token_valid(token, PASSCODE, "sk-ant-api03-" + "Z" * 40, now=lambda: now + 10)
    for junk in ["", ".", "abc.def", f"{expires}.", f"{expires * 10}.{'0' * 64}", "1" * 40 + ".x",
                 f"²{expires}.{'0' * 64}", f"{expires}.{'é' * 64}", f"{expires}.{'A' * 64}",
                 f" {token} extra"]:  # fmt: skip
        assert live.token_status(junk, PASSCODE, KEY_A, now=lambda: now) == "invalid"


def test_a_token_far_in_the_future_is_refused():
    """Even a correctly signed token can't claim a lifetime longer than TOKEN_TTL_S."""
    far = int(1_000_000 + 10 * TOKEN_TTL_S)
    sig = live._signature(far, PASSCODE, KEY_A)
    assert not token_valid(f"{far}.{sig}", PASSCODE, KEY_A, now=lambda: 1_000_000.0)


@pytest.mark.parametrize(
    "raw_token", [b"1795000000." + bytes([0xE9]), bytes([0xB2, 0xB3]) + b"." + b"0" * 64]
)
def test_odd_tokens_get_401_not_a_crash(monkeypatch, checked, raw_token):
    """Latin-1 header bytes Starlette decodes into non-ASCII text must not raise (review bug)."""
    from fastapi import HTTPException, Request

    s = settings_for("live")
    headers = [(b"x-gradpath-token", raw_token), (b"x-anthropic-key", KEY_A.encode())]
    request = Request({"type": "http", "headers": headers, "client": ("10.0.0.1", 1)})
    with pytest.raises(HTTPException) as err:
        deps.check_passcode(request, s)
    assert err.value.status_code == 401


def test_a_token_only_works_with_the_key_it_was_issued_for(monkeypatch, checked, kb_service):
    c = client(monkeypatch, kb_service)
    spy_answer(monkeypatch)
    token = check(c).json()["token"]
    other_key = "sk-ant-api03-" + "Z" * 40
    resp = c.post("/api/chat", json={"question": "What?"},
                  headers={TOKEN_HEADER: token, KEY_HEADER: other_key, **ip(1)})  # fmt: skip
    assert resp.status_code == 401 and resp.json()["code"] == "passcode_required"


def test_an_expired_token_is_refused_without_counting_as_a_guess(monkeypatch, checked, kb_service):
    c = client(monkeypatch, kb_service)
    old, _ = issue_token(PASSCODE, KEY_A, now=lambda: 1_000.0)  # long expired
    monkeypatch.setattr(live, "token_status", lambda *a, **k: "expired")
    for _ in range(8):
        r = c.post("/api/chat", json={"question": "What?"},
                   headers={TOKEN_HEADER: old, KEY_HEADER: KEY_A, **ip(1)})  # fmt: skip
        assert r.status_code == 401  # never 429: expired tokens don't lock the visitor out


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

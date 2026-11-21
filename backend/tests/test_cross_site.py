"""CORS and CSRF (T-018 step 8; SECURITY.md 01): cross-site requests can't act or read.

The defences, each tested: no CORS headers anywhere (cross-origin reads stay blocked), FastAPI
refuses the content types an HTML form can send, and a POST naming a foreign Origin is refused
before anything runs.
"""

import pytest
from conftest import plain
from fastapi.testclient import TestClient

from gradpath.api import main as main_module
from gradpath.api import search as search_module
from gradpath.api.main import create_app
from gradpath.config import Settings

EVIL = "https://evil.example"
BODY = '{"query": "sql index"}'


@pytest.fixture
def app_and_calls(monkeypatch):
    """A local-mode app whose search records each call instead of calling Voyage."""
    s = Settings(_env_file=None, app_mode="local")
    monkeypatch.setattr(main_module, "get_settings", lambda: s)
    calls = []

    def fake_search(query, retrieval):
        calls.append(query)
        return {"query": query, "hits": [], "insufficient": True, "route_preview": None}

    monkeypatch.setattr(search_module, "search_sources", fake_search)
    app = create_app(use_lifespan=False)
    app.state.retrieval = object()
    return TestClient(app), calls


@pytest.mark.parametrize(
    "content_type",
    ["text/plain", "text/plain; charset=utf-8", "application/x-www-form-urlencoded",
     "multipart/form-data; boundary=x", None],
)  # fmt: skip
def test_a_form_post_with_a_json_body_never_runs(app_and_calls, content_type):
    """What a cross-site HTML form can send (no Origin check involved: same-origin here)."""
    c, calls = app_and_calls
    headers = {"Content-Type": content_type} if content_type else {}
    assert c.post("/api/search", content=BODY, headers=headers).status_code == 422
    assert calls == []


@pytest.mark.parametrize(
    "path", ["/api/search", "/api/chat", "/api/assist", "/api/jobs/analyze", "/api/career/runs",
             "/api/career/prepare", "/api/profile/from-resume"],
)  # fmt: skip
@pytest.mark.parametrize("origin", [EVIL, "null", "http://localhost:3001", "http://localhost"])
def test_a_foreign_origin_is_refused_before_anything_runs(app_and_calls, path, origin):
    c, calls = app_and_calls
    resp = c.post(
        path, content=BODY, headers={"Origin": origin, "Content-Type": "application/json"}
    )
    assert (resp.status_code, plain(resp.json())) == (
        403,
        {"detail": "Cross-site requests are not accepted."},
    )
    assert calls == []


@pytest.mark.parametrize(
    "origin", ["http://localhost:3000", "http://127.0.0.1:3000", "HTTP://LOCALHOST:3000/", None]
)
def test_the_frontend_and_non_browser_clients_pass(app_and_calls, origin):
    c, calls = app_and_calls
    headers = {"Content-Type": "application/json", **({"Origin": origin} if origin else {})}
    assert c.post("/api/search", content=BODY, headers=headers).status_code == 200
    assert calls == ["sql index"]


def test_the_deployed_origin_comes_from_settings(app_and_calls, monkeypatch):
    c, _ = app_and_calls
    s = Settings(_env_file=None, allowed_origins="https://gradpath.example.app")
    monkeypatch.setattr(main_module, "get_settings", lambda: s)

    def post(origin: str) -> int:
        headers = {"Origin": origin, "Content-Type": "application/json"}
        return c.post("/api/search", content=BODY, headers=headers).status_code

    ok, local = post("https://gradpath.example.app"), post("http://localhost:3000")
    assert (ok, local) == (200, 403)


def test_reads_are_not_blocked_but_carry_no_cors_headers(app_and_calls):
    """GETs are read-only; without CORS headers a cross-origin page can't read the answer."""
    c, _ = app_and_calls
    resp = c.get("/api/health", headers={"Origin": EVIL})
    assert resp.status_code == 200 and "access-control-allow-origin" not in resp.headers


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_other_unsafe_methods_are_checked_too(app_and_calls, method):
    c, _ = app_and_calls
    resp = c.request(method.upper(), "/api/search", headers={"Origin": EVIL})
    assert resp.status_code == 403


def test_two_origin_headers_are_refused(app_and_calls):
    c, calls = app_and_calls
    resp = c.post(
        "/api/search", content=BODY,
        headers=[("Origin", "http://localhost:3000"), ("Origin", EVIL),
                 ("Content-Type", "application/json")],
    )  # fmt: skip
    assert resp.status_code == 403 and calls == []


def test_a_foreign_origin_is_refused_before_the_body_is_read(app_and_calls):
    from gradpath.api.main import MAX_BODY_BYTES

    c, _ = app_and_calls
    big = b"x" * (MAX_BODY_BYTES + 10)
    resp = c.post("/api/search", content=big, headers={"Origin": EVIL})
    assert resp.status_code == 403  # not 413: the origin check runs first


def test_a_preflight_gets_no_permission(app_and_calls):
    c, calls = app_and_calls
    resp = c.options(
        "/api/search",
        headers={"Origin": EVIL, "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type, x-anthropic-key"},
    )  # fmt: skip
    assert resp.status_code == 405
    assert not any(h.startswith("access-control-") for h in resp.headers)
    assert calls == []

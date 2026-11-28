"""Sign in with GitHub (T-026, always-hard area): the OAuth flow against a fake GitHub.

No network: `auth.github_client` is replaced by an httpx client on a `MockTransport` that plays
GitHub's token endpoint and `/user`. Cookies are passed by hand because they are `Secure` (the
test client speaks http) and so the tests see exactly what the browser would send.
"""

import base64
import hashlib
import logging
import time
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from test_rate_limits import Clock, ip, use
from test_visitor_key import CLIENT_SECRET, LIVE, PASS, SESSION_SECRET

from gradpath.api import auth, ratelimit
from gradpath.api.main import create_app
from gradpath.api.ratelimit import Limiter

SITE = "https://site.example"
CALLBACK = f"{SITE}/api/auth/github/callback"
GITHUB_TOKEN = "gho_test" + "t" * 30
CODE = "code" + "c" * 16
SETTINGS = LIVE.model_copy(update={"trusted_proxy_hops": 1})


class FakeGitHub:
    """GitHub's two endpoints; records every request it gets."""

    def __init__(self, *, age_days: float = 400, profile: dict | None = None) -> None:
        created = datetime.now(UTC) - timedelta(days=age_days)
        self.profile = profile or {
            "id": 98765,
            "login": "octo-visitor",
            "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.token_reply: httpx.Response | None = None
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url == auth.TOKEN_URL:
            return self.token_reply or httpx.Response(
                200, json={"access_token": GITHUB_TOKEN, "token_type": "bearer", "scope": ""}
            )
        if request.url == auth.USER_URL:
            if request.headers.get("Authorization") != f"Bearer {GITHUB_TOKEN}":
                return httpx.Response(401, json={"message": "Bad credentials"})
            return httpx.Response(200, json=self.profile)
        return httpx.Response(404)


@pytest.fixture
def github(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(
        auth, "github_client", lambda: httpx.Client(transport=httpx.MockTransport(fake.handler))
    )
    return fake


@pytest.fixture
def app_client(monkeypatch):
    use(monkeypatch, SETTINGS)
    monkeypatch.setattr(auth, "get_settings", lambda: SETTINGS)
    monkeypatch.setattr(ratelimit, "LIMITER", Limiter(clock=Clock()))
    return TestClient(create_app(use_lifespan=False), follow_redirects=False)


def set_cookies(resp: httpx.Response) -> dict[str, SimpleCookie]:
    """Each Set-Cookie header parsed, by cookie name."""
    out = {}
    for header in resp.headers.get_list("set-cookie"):
        jar = SimpleCookie()
        jar.load(header)
        for name in jar:
            out[name] = jar
    return out


def start(c: TestClient, n: int = 1) -> tuple[str, str]:
    """Begin a sign-in: (state from GitHub's URL, the gp_oauth cookie value)."""
    resp = c.get("/api/auth/github/login", headers=ip(n))
    assert resp.status_code == 302
    state = parse_qs(urlparse(resp.headers["location"]).query)["state"][0]
    return state, set_cookies(resp)[auth.OAUTH_COOKIE][auth.OAUTH_COOKIE].value


def finish(
    c: TestClient, state: str, oauth: str | None, code: str = CODE, **query
) -> httpx.Response:
    params = {"code": code, "state": state, **query}
    headers = {**ip(1)}
    if oauth is not None:
        headers["Cookie"] = f"{auth.OAUTH_COOKIE}={oauth}"
    return c.get("/api/auth/github/callback", params=params, headers=headers)


def outcome(resp: httpx.Response) -> str:
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert location.startswith(f"{SITE}/?signin=")  # always the site's own home page
    return location.split("=", 1)[1]


# --- starting a sign-in ------------------------------------------------------------------------


def test_login_sends_the_visitor_to_github_with_state_and_pkce(app_client):
    resp = app_client.get("/api/auth/github/login", headers=ip(1))
    assert resp.status_code == 302 and resp.headers["cache-control"] == "no-store"
    url = urlparse(resp.headers["location"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == auth.AUTHORIZE_URL
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert q["client_id"] == LIVE.github_client_id and q["redirect_uri"] == CALLBACK
    assert q["code_challenge_method"] == "S256" and len(q["code_challenge"]) == 43
    assert len(q["state"]) >= 40 and q["allow_signup"] == "false" and "scope" not in q
    assert CLIENT_SECRET not in resp.headers["location"]
    morsel = set_cookies(resp)[auth.OAUTH_COOKIE][auth.OAUTH_COOKIE]
    assert morsel["httponly"] and morsel["secure"] and morsel["samesite"].lower() == "lax"
    assert morsel["path"] == auth.OAUTH_PATH and int(morsel["max-age"]) == auth.OAUTH_TTL_S


def test_each_login_gets_its_own_state(app_client):
    assert start(app_client)[0] != start(app_client)[0]


# --- the callback ---------------------------------------------------------------------------


def test_a_good_sign_in_sets_a_session_cookie(app_client, github):
    state, oauth = start(app_client)
    resp = finish(app_client, state, oauth)
    assert outcome(resp) == "ok"
    cookies = set_cookies(resp)
    session = cookies[auth.SESSION_COOKIE][auth.SESSION_COOKIE]
    assert session["httponly"] and session["secure"] and session["samesite"].lower() == "lax"
    assert session["path"] == "/" and int(session["max-age"]) == LIVE.session_ttl_s
    assert cookies[auth.OAUTH_COOKIE][auth.OAUTH_COOKIE]["max-age"] == "0"  # sign-in cookie gone
    me = app_client.get(
        "/api/auth/me", headers={"Cookie": f"{auth.SESSION_COOKIE}={session.value}"}
    )
    assert me.json()["signed_in"] is True and me.json()["login"] == "octo-visitor"
    assert me.headers["cache-control"] == "no-store"


def test_the_code_exchange_sends_the_pkce_verifier_and_secret(app_client, github):
    resp = app_client.get("/api/auth/github/login", headers=ip(1))
    query = parse_qs(urlparse(resp.headers["location"]).query)
    oauth = set_cookies(resp)[auth.OAUTH_COOKIE][auth.OAUTH_COOKIE].value
    finish(app_client, query["state"][0], oauth)
    token_request, user_request = github.requests
    form = {k: v[0] for k, v in parse_qs(token_request.content.decode()).items()}
    assert form["client_secret"] == CLIENT_SECRET and form["code"] == CODE
    assert form["redirect_uri"] == CALLBACK and form["client_id"] == LIVE.github_client_id
    challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest())
    assert challenge.rstrip(b"=").decode() == query["code_challenge"][0]
    assert token_request.headers["accept"] == "application/json"
    assert user_request.headers["authorization"] == f"Bearer {GITHUB_TOKEN}"


@pytest.mark.parametrize("case", ["wrong_state", "no_cookie", "other_cookie", "bad_code"])
def test_a_callback_that_does_not_match_its_login_fails_without_calling_github(
    app_client, github, case
):
    state, oauth = start(app_client)
    _, other_oauth = start(app_client)
    if case == "wrong_state":
        resp = finish(app_client, state[::-1], oauth)
    elif case == "no_cookie":
        resp = finish(app_client, state, None)
    elif case == "other_cookie":
        resp = finish(app_client, state, other_oauth)  # login CSRF: someone else's flow
    else:
        resp = finish(app_client, state, oauth, code="bad code!")
    assert outcome(resp) == "failed" and github.requests == []
    assert auth.SESSION_COOKIE not in set_cookies(resp)


def test_a_sign_in_cookie_expires_after_ten_minutes(app_client, github, monkeypatch):
    state, oauth = start(app_client)
    monkeypatch.setattr(auth, "now", lambda: time.time() + auth.OAUTH_TTL_S + 1)
    assert outcome(finish(app_client, state, oauth)) == "failed" and github.requests == []


def test_a_session_cookie_cannot_stand_in_for_a_sign_in_cookie(app_client, github):
    state, _ = start(app_client)
    session_value = PASS["Cookie"].split("=", 1)[1]
    assert outcome(finish(app_client, state, session_value)) == "failed"
    assert auth.unsign(SESSION_SECRET, "oauth", session_value, auth.OAUTH_TTL_S) is None


def test_cancelling_on_github_is_reported_as_denied(app_client, github):
    state, oauth = start(app_client)
    resp = app_client.get(
        "/api/auth/github/callback",
        params={"error": "access_denied", "state": state},
        headers={"Cookie": f"{auth.OAUTH_COOKIE}={oauth}", **ip(1)},
    )
    assert outcome(resp) == "denied" and github.requests == []


@pytest.mark.parametrize(("age", "expected"), [(29, "too_new"), (29.9, "too_new"), (31, "ok")])
def test_accounts_younger_than_thirty_days_are_refused(app_client, monkeypatch, age, expected):
    fake = FakeGitHub(age_days=age)
    monkeypatch.setattr(
        auth, "github_client", lambda: httpx.Client(transport=httpx.MockTransport(fake.handler))
    )
    state, oauth = start(app_client)
    resp = finish(app_client, state, oauth)
    assert outcome(resp) == expected
    assert (auth.SESSION_COOKIE in set_cookies(resp)) is (expected == "ok")


def test_a_blocked_user_cannot_sign_in(app_client, github, monkeypatch):
    blocked = SETTINGS.model_copy(update={"github_blocked_users": "OCTO-visitor"})
    monkeypatch.setattr(auth, "get_settings", lambda: blocked)
    state, oauth = start(app_client)
    assert outcome(finish(app_client, state, oauth)) == "blocked"


@pytest.mark.parametrize(
    "reply",
    [
        httpx.Response(200, json={"error": "bad_verification_code"}),
        httpx.Response(500, text="oops"),
        httpx.Response(200, text="not json"),
    ],
)
def test_a_refused_code_exchange_fails_cleanly(app_client, github, reply):
    github.token_reply = reply
    state, oauth = start(app_client)
    assert outcome(finish(app_client, state, oauth)) == "failed"


def test_a_network_error_fails_cleanly(app_client, monkeypatch):
    def broken(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    monkeypatch.setattr(
        auth, "github_client", lambda: httpx.Client(transport=httpx.MockTransport(broken))
    )
    state, oauth = start(app_client)
    assert outcome(finish(app_client, state, oauth)) == "failed"


@pytest.mark.parametrize(
    "profile",
    [
        {"id": "98765", "login": "octo", "created_at": "2020-01-01T00:00:00Z"},
        {"id": 98765, "login": "<script>", "created_at": "2020-01-01T00:00:00Z"},
        {"id": 98765, "login": "octo", "created_at": "yesterday"},
        {"id": 98765, "login": "octo", "created_at": "2020-01-01T00:00:00"},  # no timezone
        {"id": True, "login": "octo", "created_at": "2020-01-01T00:00:00Z"},
        {"login": "octo"},
    ],
)
def test_an_unexpected_profile_fails_cleanly(app_client, monkeypatch, profile):
    fake = FakeGitHub(profile=profile)
    monkeypatch.setattr(
        auth, "github_client", lambda: httpx.Client(transport=httpx.MockTransport(fake.handler))
    )
    state, oauth = start(app_client)
    assert outcome(finish(app_client, state, oauth)) == "failed"


def test_the_redirect_ignores_any_address_the_caller_supplies(app_client, github):
    state, oauth = start(app_client)
    resp = finish(
        app_client, state, oauth, redirect_uri="https://evil.example", next="https://evil.example"
    )
    assert outcome(resp) == "ok" and "evil" not in resp.headers["location"]


def test_nothing_identifying_is_logged(app_client, github, caplog):
    with caplog.at_level(logging.DEBUG):
        state, oauth = start(app_client)
        resp = finish(app_client, state, oauth)
    session = set_cookies(resp)[auth.SESSION_COOKIE][auth.SESSION_COOKIE].value
    # The test client's own httpx logger prints the URLs it requests; only the server's count.
    server_logs = "\n".join(
        r.getMessage() for r in caplog.records if not r.name.startswith(("httpx", "httpcore"))
    )
    for secret in (state, oauth, CODE, GITHUB_TOKEN, CLIENT_SECRET, "octo-visitor", "98765",
                   session, SESSION_SECRET):  # fmt: skip
        assert secret not in server_logs
    assert "github sign-in: ok" in server_logs


def test_the_access_log_hides_the_callback_query():
    """uvicorn's access line for the callback would carry the code and state (Render keeps it)."""
    from gradpath.api.main import RedactAuthQuery

    def access(path):
        return logging.LogRecord(
            "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
            ("203.0.113.1:5000", "GET", path, "1.1", 303), None,
        )  # fmt: skip

    callback = access(f"/api/auth/github/callback?code={CODE}&state=abc")
    other = access("/api/demo?x=1")
    assert RedactAuthQuery().filter(callback) and RedactAuthQuery().filter(other)
    assert CODE not in callback.getMessage() and "?[redacted]" in callback.getMessage()
    assert other.getMessage().endswith('"GET /api/demo?x=1 HTTP/1.1" 303')
    create_app(use_lifespan=False)
    create_app(use_lifespan=False)  # installed once, however many apps are built
    filters = logging.getLogger("uvicorn.access").filters
    assert sum(isinstance(f, RedactAuthQuery) for f in filters) == 1


def test_sign_in_routes_are_rate_limited_per_ip(app_client):
    codes = [app_client.get("/api/auth/github/login", headers=ip(1)).status_code for _ in range(11)]
    assert codes == [302] * 10 + [429]
    assert app_client.get("/api/auth/github/login", headers=ip(2)).status_code == 302


# --- me, logout, other modes ----------------------------------------------------------------


def test_me_without_a_session_says_signed_out(app_client):
    assert app_client.get("/api/auth/me").json() == {
        "signed_in": False,
        "login": None,
        "expires_at": None,
    }


def test_logout_clears_the_session_cookie(app_client):
    resp = app_client.post("/api/auth/logout", json={}, headers=PASS)
    assert resp.status_code == 204
    morsel = set_cookies(resp)[auth.SESSION_COOKIE][auth.SESSION_COOKIE]
    assert morsel["max-age"] == "0" and morsel.value == ""


def test_a_cross_site_post_with_the_session_cookie_is_refused(app_client):
    """Cookies arrive with T-026: OriginCheck still refuses a foreign Origin before anything runs
    (SameSite=Lax stops browsers sending the cookie on such a POST in the first place)."""
    evil = {"Origin": "https://evil.example", **PASS}
    assert app_client.post("/api/auth/logout", json={}, headers=evil).status_code == 403
    chat = app_client.post("/api/chat", json={"question": "What?"}, headers=evil)
    assert chat.status_code == 403 and chat.json()["code"] == "cross_site"


@pytest.mark.parametrize("mode", ["demo", "local"])
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/auth/github/login"),
        ("get", "/api/auth/github/callback"),
        ("get", "/api/auth/me"),
        ("post", "/api/auth/logout"),
    ],
)
def test_sign_in_exists_only_in_live_mode(monkeypatch, mode, method, path):
    other = SETTINGS.model_copy(update={"app_mode": mode})
    use(monkeypatch, other)
    monkeypatch.setattr(auth, "get_settings", lambda: other)
    c = TestClient(create_app(use_lifespan=False), follow_redirects=False)
    resp = getattr(c, method)(path)
    assert resp.status_code == 404 and resp.json()["code"] == "auth_off"


def test_signed_values_reject_tampering_and_long_lives():
    value = auth.sign(SESSION_SECRET, "session", {"exp": int(time.time()) + 60, "id": 1})
    assert auth.unsign(SESSION_SECRET, "session", value, 3600) is not None
    body, mac = value.split(".")
    assert auth.unsign(SESSION_SECRET, "session", f"{body}x.{mac}", 3600) is None
    assert auth.unsign("another-secret", "session", value, 3600) is None
    far = auth.sign(SESSION_SECRET, "session", {"exp": int(time.time()) + 10 * 86_400, "id": 1})
    assert auth.unsign(SESSION_SECRET, "session", far, 86_400) is None  # claims too long a life
    for odd in ("", "x" * 2000, "é.é", f"{body}.{mac}.extra"):
        assert auth.unsign(SESSION_SECRET, "session", odd, 3600) is None

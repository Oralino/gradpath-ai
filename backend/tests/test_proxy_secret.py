"""The site's shared secret and the visitor address it vouches for (T-020 step 4; always-hard:
proxy trust), plus the temporary /api/debug/forwarded measuring page. No network."""

import logging

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr

from gradpath.api import debug
from gradpath.api.main import create_app
from gradpath.api.ratelimit import CLIENT_IP_HEADER, PROXY_SECRET_HEADER, client_ip, from_site
from gradpath.config import Settings

SECRET = "proxy-secret-for-tests-" + "Q" * 20


def settings(**extra) -> Settings:
    return Settings(_env_file=None, **{"proxy_shared_secret": SecretStr(SECRET), **extra})


def request(headers: list[tuple[str, str]], host: str = "127.0.0.1") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers]
    return Request({"type": "http", "headers": raw, "client": (host, 1234)})


def site(ip: str, secret: str = SECRET) -> list[tuple[str, str]]:
    return [(CLIENT_IP_HEADER, ip), (PROXY_SECRET_HEADER, secret)]


# --- which address is the client --------------------------------------------------------------


def test_the_site_vouches_for_the_visitor_address():
    assert client_ip(request(site("198.51.100.7")), settings()) == "198.51.100.7"
    # IPv6 visitors are keyed by their /64, like every other address.
    assert client_ip(request(site("2001:db8:1:2::9")), settings()) == "2001:db8:1:2::/64"


@pytest.mark.parametrize(
    "headers",
    [
        site("198.51.100.7", secret="wrong-" + "Q" * 40),  # a guess
        site("198.51.100.7", secret=SECRET[:-1]),  # one character short
        site("198.51.100.7", secret=""),
        [(CLIENT_IP_HEADER, "198.51.100.7")],  # no secret at all
        # Two secret headers (one right, one wrong): ambiguous, refused.
        [*site("198.51.100.7"), (PROXY_SECRET_HEADER, "other")],
    ],
)
def test_without_the_exact_secret_the_claimed_address_is_ignored(headers):
    assert client_ip(request(headers), settings()) == "127.0.0.1"
    assert not from_site(request(headers), settings())


def test_an_unset_secret_trusts_nobody():
    for value in (None, SecretStr("")):
        s = settings(proxy_shared_secret=value)
        assert client_ip(request(site("198.51.100.7", secret="")), s) == "127.0.0.1"
        assert client_ip(request(site("198.51.100.7")), s) == "127.0.0.1"


def test_a_bad_vouched_address_falls_back_to_the_proxy_hops():
    """The secret matched but the address is unusable (missing, not an IP, sent twice): the
    usual TRUSTED_PROXY_HOPS rule decides, never the header's text."""
    s = settings(trusted_proxy_hops=1)
    xff = ("x-forwarded-for", "203.0.113.5")
    for headers in (
        [(PROXY_SECRET_HEADER, SECRET), xff],
        [*site("not-an-ip" * 20), xff],
        [*site("198.51.100.7"), (CLIENT_IP_HEADER, "198.51.100.8"), xff],
    ):
        assert client_ip(request(headers), s) == "203.0.113.5"


def test_a_direct_caller_cannot_pick_its_bucket():
    """Straight at the API (no secret), forged headers of every kind give the same key."""
    s = settings(trusted_proxy_hops=0)
    keys = {
        client_ip(
            request([(CLIENT_IP_HEADER, f"203.0.113.{n}"), ("x-forwarded-for", "6.6.6.6")]), s
        )
        for n in range(5)
    }
    assert keys == {"127.0.0.1"}


# --- the measuring page -----------------------------------------------------------------------


@pytest.fixture
def page(monkeypatch):
    """A client for the app with settings the test sets through the returned function."""

    def use(**extra):
        s = settings(**extra)
        monkeypatch.setattr(debug, "get_settings", lambda: s)
        return TestClient(create_app(use_lifespan=False))

    return use


def test_the_page_is_hidden_unless_switched_on(page):
    reply = page().get("/api/debug/forwarded")
    assert reply.status_code == 404
    assert reply.json()["detail"] == "Not Found"
    app = create_app(use_lifespan=False)
    assert "/api/debug/forwarded" not in str(app.openapi())


def test_the_page_shows_the_chain_and_never_the_secret(page, caplog):
    caplog.set_level(logging.DEBUG)
    client = page(debug_forwarded=True, trusted_proxy_hops=1)
    reply = client.get(
        "/api/debug/forwarded",
        headers={
            "X-Forwarded-For": "6.6.6.6, 198.51.100.7",
            CLIENT_IP_HEADER: "203.0.113.9",
            PROXY_SECRET_HEADER: SECRET,
            "Cookie": "gp_session=cookie-value-not-to-show",
        },
    )
    assert reply.status_code == 200
    assert reply.headers["cache-control"] == "no-store"
    body = reply.json()
    assert body["x_forwarded_for"] == ["6.6.6.6", "198.51.100.7"]
    assert body["proxy_secret_matches"] is True
    assert body["client_ip_header"] == ["203.0.113.9"]
    assert body["rate_limit_key"] == "203.0.113.9"
    # TestClient connects as "testclient", not an address: "unknown". Hops 3 is more entries
    # than the chain has, so it falls back to the connection too. The secret plays no part here.
    assert body["picked_by_hops"] == {
        "0": "unknown",
        "1": "198.51.100.7",
        "2": "6.6.6.6",
        "3": "unknown",
    }
    assert PROXY_SECRET_HEADER in body["header_names"] and "cookie" in body["header_names"]
    for text in (reply.text, str(reply.headers), caplog.text):
        assert SECRET not in text
        assert "cookie-value-not-to-show" not in text


def test_the_page_reports_a_wrong_secret(page):
    body = (
        page(debug_forwarded=True)
        .get(
            "/api/debug/forwarded",
            headers={CLIENT_IP_HEADER: "203.0.113.9", PROXY_SECRET_HEADER: "guess-" + "x" * 40},
        )
        .json()
    )
    assert body["proxy_secret_matches"] is False
    assert body["rate_limit_key"] != "203.0.113.9"


# --- review fixes -----------------------------------------------------------------------------


def test_a_weak_proxy_secret_is_refused_in_every_mode(monkeypatch):
    from gradpath.api.main import check_live_settings

    for mode in ("local", "demo"):
        weak = Settings(_env_file=None, app_mode=mode, proxy_shared_secret=SecretStr("abc"))
        with pytest.raises(RuntimeError, match="PROXY_SHARED_SECRET") as err:
            check_live_settings(weak)
        assert "abc" not in str(err.value)
        check_live_settings(settings(app_mode=mode))  # a strong one starts


def test_an_unusable_vouched_address_is_logged_once_without_values(monkeypatch, caplog):
    from gradpath.api import ratelimit

    monkeypatch.setattr(ratelimit, "_warned_site_address", False)
    caplog.set_level(logging.WARNING, logger="gradpath.api.ratelimit")
    for _ in range(3):
        client_ip(request(site("not-an-ip")), settings())
    lines = [r for r in caplog.records if "address was unusable" in r.getMessage()]
    assert len(lines) == 1
    assert SECRET not in caplog.text and "not-an-ip" not in caplog.text


# --- direct calls are refused (SiteOnly, owner decision: option C) ---------------------------


@pytest.fixture
def guarded(monkeypatch):
    """The whole app with PROXY_SHARED_SECRET set, as on the deployed site."""
    from gradpath.api import main

    s = settings(debug_forwarded=True)
    for module in (main, debug):
        monkeypatch.setattr(module, "get_settings", lambda: s)
    return TestClient(create_app(use_lifespan=False))


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/demo"),
        ("GET", "/api/auth/me"),
        ("GET", "/api/debug/forwarded"),
        ("GET", "/docs"),
        ("GET", "/openapi.json"),
        ("POST", "/api/chat"),
        ("POST", "/api/health"),  # only GET and HEAD are open
        ("GET", "/api/health/"),
        ("GET", "/api/healthz"),
        ("GET", "/nothing-here"),
    ],
)
def test_a_direct_call_is_refused_before_anything_runs(guarded, method, path):
    reply = guarded.request(method, path, json={"message": "x"} if method == "POST" else None)
    assert reply.status_code == 403
    assert reply.json() == {"detail": "Use GradPath through its website.", "code": "site_only"}
    assert reply.headers["cache-control"] == "no-store"


def test_forged_or_guessed_secrets_are_refused(guarded):
    for secret in ("", "guess-" + "x" * 40, SECRET[:-1], SECRET + "x"):
        reply = guarded.get("/api/demo", headers={PROXY_SECRET_HEADER: secret})
        assert reply.status_code == 403
    both = [(PROXY_SECRET_HEADER, SECRET), (PROXY_SECRET_HEADER, "other")]
    assert guarded.get("/api/demo", headers=both).status_code == 403


def test_the_health_check_stays_open(guarded):
    assert guarded.get("/api/health").status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [("HEAD", "/api/demo"), ("HEAD", "/api/health"), ("OPTIONS", "/api/chat"),
     ("GET", "//api/health"), ("GET", "/api//health"), ("GET", "/API/health")],
)  # fmt: skip
def test_method_and_path_tricks_are_refused(guarded, method, path):
    assert guarded.request(method, path).status_code == 403


def test_a_wrong_secret_is_logged_once_and_never_echoed(guarded, monkeypatch, caplog):
    from gradpath.api.main import SiteOnly

    monkeypatch.setattr(SiteOnly, "warned_mismatch", False)
    caplog.set_level(logging.WARNING)
    guarded.get("/api/demo")  # no secret header at all: a plain direct call, not logged
    assert "wrong site secret" not in caplog.text
    guess = "guess-" + "x" * 40
    for _ in range(3):
        reply = guarded.get("/api/demo", headers={PROXY_SECRET_HEADER: guess})
        assert guess not in reply.text and SECRET not in reply.text
    assert caplog.text.count("wrong site secret") == 1
    assert guess not in caplog.text and SECRET not in caplog.text


def test_the_secret_without_an_address_passes_the_guard(guarded):
    """What proxy.ts sends when it couldn't measure the visitor: allowed, keyed by the hops rule."""
    reply = guarded.get("/api/debug/forwarded", headers={PROXY_SECRET_HEADER: SECRET})
    assert reply.status_code == 200 and reply.json()["proxy_secret_matches"] is True


def test_calls_through_the_site_pass(guarded):
    through = {PROXY_SECRET_HEADER: SECRET, CLIENT_IP_HEADER: "198.51.100.7"}
    assert guarded.get("/api/health", headers=through).status_code == 200
    reply = guarded.get("/api/debug/forwarded", headers=through)
    assert reply.status_code == 200 and reply.json()["rate_limit_key"] == "198.51.100.7"
    assert SECRET not in reply.text


def test_without_a_secret_nothing_is_blocked(monkeypatch):
    """Local, CI and the Docker smoke test run with no secret: the guard is off."""
    from gradpath.api import main

    s = settings(proxy_shared_secret=None)
    monkeypatch.setattr(main, "get_settings", lambda: s)
    client = TestClient(create_app(use_lifespan=False))
    assert client.get("/api/health").status_code == 200
    assert client.get("/openapi.json").status_code == 200

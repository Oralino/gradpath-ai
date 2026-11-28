"""Per-IP and per-GitHub-user limits and the live sign-in guard (T-018 step 7, T-026; always-hard
area): fake clock, no network."""

import logging

import pytest
from conftest import plain
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_visitor_key import (
    GITHUB_ID,
    KEY_A,
    LIVE,
    LOGIN,
    PASS,
    SESSION_SECRET,
    session_for,
    spy_answer,
)

from gradpath.api import deps, ratelimit
from gradpath.api.auth import SESSION_COOKIE
from gradpath.api.deps import KEY_HEADER
from gradpath.api.main import check_live_settings, create_app
from gradpath.api.ratelimit import LIMITED, Limiter, Window, client_ip
from gradpath.config import Settings
from gradpath.providers import factory


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    """The shared limiter on a fake clock."""
    c = Clock()
    monkeypatch.setattr(ratelimit, "LIMITER", Limiter(clock=c))
    return c


def settings_for(mode: str, **extra) -> Settings:
    base = LIVE.model_dump() if mode == "live" else {"app_mode": mode}
    return Settings(_env_file=None, **{**base, "trusted_proxy_hops": 1, **extra})


def use(monkeypatch, s: Settings) -> None:
    for module in (deps, ratelimit, factory):
        monkeypatch.setattr(module, "get_settings", lambda: s)


def ip(n: int) -> dict[str, str]:
    """Headers that make the request come from client n (behind one trusted proxy)."""
    return {"X-Forwarded-For": f"203.0.113.{n}"}


# --- the limiter ------------------------------------------------------------------------------


def test_windows_allow_then_refuse_then_recover():
    c = Clock()
    lim = Limiter(clock=c)
    win = (Window(2, 60),)
    assert lim.hit(("b", "x"), win) == 0 and lim.hit(("b", "x"), win) == 0
    assert lim.hit(("b", "x"), win) == pytest.approx(60)
    c.now += 30
    assert lim.hit(("b", "x"), win) == pytest.approx(30)  # refused hits are not recorded
    c.now += 30.001
    assert lim.hit(("b", "x"), win) == 0
    assert lim.hit(("b", "y"), win) == 0  # another client has its own window


def test_the_longest_wait_of_several_windows_wins():
    c = Clock()
    lim = Limiter(clock=c)
    wins = (Window(5, 60), Window(2, 3600))
    lim.hit(("b", "x"), wins)
    c.now += 10
    lim.hit(("b", "x"), wins)
    assert lim.hit(("b", "x"), wins) == pytest.approx(3590)


def test_memory_is_bounded_and_global_counters_survive_a_flood(monkeypatch):
    monkeypatch.setattr(ratelimit, "MAX_TRACKED", 3)
    lim = Limiter(clock=Clock())
    cap = (Window(1, 60),)
    lim.hit(("search", "*"), cap)
    for n in range(10):
        lim.hit(("b", str(n)), cap)
    assert len(lim._events) == 3  # the least recent clients were dropped
    assert lim.hit(("search", "*"), cap) > 0  # the global count was not evicted


def test_checking_an_address_creates_nothing():
    lim = Limiter(clock=Clock())
    assert lim.wait_time(("b", "x"), (Window(1, 60),)) == 0
    assert len(lim._events) == 0


# --- which address is the client --------------------------------------------------------------


def request(headers: dict[str, str], host: str = "10.0.0.1") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": (host, 1234)})


def test_without_trusted_proxies_the_connection_address_is_used():
    s = Settings(_env_file=None, trusted_proxy_hops=0)
    assert client_ip(request({"X-Forwarded-For": "1.2.3.4"}), s) == "10.0.0.1"


def test_behind_proxies_the_forged_left_end_is_ignored():
    one, two = (Settings(_env_file=None, trusted_proxy_hops=n) for n in (1, 2))
    forged = {"X-Forwarded-For": "6.6.6.6, 198.51.100.7"}
    assert client_ip(request(forged), one) == "198.51.100.7"
    assert client_ip(request({"X-Forwarded-For": "6.6.6.6, 198.51.100.7, 10.1.1.1"}), two) == (
        "198.51.100.7"
    )
    assert client_ip(request({}), one) == "10.0.0.1"  # header missing: the connection address
    # Not an address: the connection address, never the client's text.
    assert client_ip(request({"X-Forwarded-For": "x" * 500}), one) == "10.0.0.1"


@pytest.mark.parametrize(
    ("address", "key"),
    [
        ("198.51.100.7", "198.51.100.7"),
        ("198.51.100.7:4433", "198.51.100.7"),
        ("::ffff:198.51.100.7", "198.51.100.7"),
        ("2001:db8:1:2:aaaa::1", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:ffff:ffff:ffff:ffff", "2001:db8:1:2::/64"),  # same /64, same client
        ("[2001:db8:1:2::9]:443", "2001:db8:1:2::/64"),
        ("not-an-ip", None),
    ],
)
def test_addresses_are_normalised(address, key):
    assert ratelimit.client_key(address) == key


def test_several_forwarded_for_lines_are_read_together():
    one = Settings(_env_file=None, trusted_proxy_hops=1)
    raw = [(b"x-forwarded-for", b"6.6.6.6"), (b"x-forwarded-for", b"198.51.100.7")]
    req = Request({"type": "http", "headers": raw, "client": ("10.0.0.1", 1)})
    assert client_ip(req, one) == "198.51.100.7"


# --- limits on the routes ---------------------------------------------------------------------


def search_client(kb_service) -> TestClient:
    app = create_app(use_lifespan=False)
    app.state.retrieval = kb_service
    return TestClient(app)


def test_search_is_limited_per_ip_in_demo_mode(kb_service, monkeypatch, clock):
    use(monkeypatch, settings_for("demo"))
    c = search_client(kb_service)
    codes = [c.post("/api/search", json={"query": "sql index"}, headers=ip(1)).status_code
             for _ in range(3)]  # fmt: skip
    assert codes == [200, 200, 429]
    refused = c.post("/api/search", json={"query": "sql index"}, headers=ip(1))
    assert plain(refused.json()) == {"detail": LIMITED} and int(refused.headers["Retry-After"]) >= 1
    assert c.post("/api/search", json={"query": "sql index"}, headers=ip(2)).status_code == 200
    clock.now += 61
    assert c.post("/api/search", json={"query": "sql index"}, headers=ip(1)).status_code == 200


def test_search_has_a_global_daily_cap(kb_service, monkeypatch, clock):
    use(monkeypatch, settings_for("demo"))
    monkeypatch.setitem(ratelimit.GLOBAL, "search", (Window(3, ratelimit.DAY),))
    c = search_client(kb_service)
    codes = [c.post("/api/search", json={"query": "sql index"}, headers=ip(n)).status_code
             for n in range(5)]  # fmt: skip
    assert codes == [200, 200, 200, 429, 429]


def test_local_mode_has_no_limits(kb_service, monkeypatch, clock):
    use(monkeypatch, settings_for("local"))
    c = search_client(kb_service)
    assert all(
        c.post("/api/search", json={"query": "sql index"}).status_code == 200 for _ in range(10)
    )


def live_client(monkeypatch, kb_service, **extra) -> TestClient:
    use(monkeypatch, settings_for("live", **extra))
    spy_answer(monkeypatch)
    app = create_app(use_lifespan=False)
    app.dependency_overrides[deps.get_retrieval] = lambda: kb_service
    return TestClient(app)


def chat(c: TestClient, n: int = 1, cookie: str | None = PASS["Cookie"]):
    headers = {KEY_HEADER: KEY_A, **ip(n)}
    if cookie is not None:
        headers["Cookie"] = cookie
    return c.post("/api/chat", json={"question": "What is an index?"}, headers=headers)


def test_model_routes_are_limited_per_ip_in_live_mode(kb_service, monkeypatch, clock):
    c = live_client(monkeypatch, kb_service)
    other_user = f"{SESSION_COOKIE}={session_for(GITHUB_ID + 1, 'other-user')}"
    assert [chat(c).status_code for _ in range(6)] == [200] * 6
    assert chat(c, cookie=other_user).status_code == 429  # same network, another user: shared
    assert chat(c, n=2, cookie=other_user).status_code == 200


def test_model_routes_are_also_limited_per_github_user(kb_service, monkeypatch, clock):
    """T-026: one person can't get more by switching networks."""
    c = live_client(monkeypatch, kb_service)
    assert [chat(c, n=k).status_code for k in range(1, 7)] == [200] * 6
    resp = chat(c, n=7)
    assert resp.status_code == 429 and int(resp.headers["Retry-After"]) >= 1
    assert (
        chat(c, n=7, cookie=f"{SESSION_COOKIE}={session_for(GITHUB_ID + 1, 'b')}").status_code
        == 200
    )
    clock.now += 61
    assert chat(c, n=7).status_code == 200


# --- the GitHub sign-in (T-026; replaced the passcode and its lock) --------------------------


def _forged() -> str:
    body, _ = session_for().split(".")
    return f"{SESSION_COOKIE}={body}.{'0' * 64}"


@pytest.mark.parametrize(
    "cookie",
    [None, f"{SESSION_COOKIE}=", f"{SESSION_COOKIE}=garbage", "other=1", "FORGED", "OTHER_SECRET"],
)
def test_live_needs_a_github_sign_in_before_the_key(kb_service, monkeypatch, clock, cookie):
    from gradpath.api.auth import SIGNIN_NEEDED

    if cookie == "FORGED":
        cookie = _forged()
    elif cookie == "OTHER_SECRET":
        other = LIVE.model_copy(update={"session_secret": SecretStr("another-secret-" + "o" * 30)})
        cookie = f"{SESSION_COOKIE}={session_for(settings=other)}"
    c = live_client(monkeypatch, kb_service)
    resp = chat(c, cookie=cookie)
    assert (resp.status_code, plain(resp.json())) == (401, {"detail": SIGNIN_NEEDED})
    assert resp.json()["code"] == "signin_required"


def test_wrong_sign_ins_lock_nobody_out(kb_service, monkeypatch, clock):
    """No passcode lock any more: forged cookies cost nothing and block no one on the network."""
    c = live_client(monkeypatch, kb_service)
    assert [chat(c, cookie=_forged()).status_code for _ in range(20)] == [401] * 20
    assert chat(c).status_code == 200


def test_an_expired_session_is_refused(kb_service, monkeypatch, clock):
    from gradpath.api import auth

    c = live_client(monkeypatch, kb_service)
    cookie = PASS["Cookie"]
    monkeypatch.setattr(auth, "now", lambda: __import__("time").time() + LIVE.session_ttl_s + 1)
    assert chat(c, cookie=cookie).status_code == 401


def test_a_blocked_user_is_refused_even_with_a_valid_session(kb_service, monkeypatch, clock):
    c = live_client(monkeypatch, kb_service, github_blocked_users=f"someone, {LOGIN.upper()}")
    assert chat(c).status_code == 401
    c = live_client(monkeypatch, kb_service, github_blocked_users=str(GITHUB_ID))
    assert chat(c).status_code == 401


def test_the_session_is_never_logged_or_echoed(kb_service, monkeypatch, clock, caplog):
    c = live_client(monkeypatch, kb_service)
    value = PASS["Cookie"].split("=", 1)[1]
    with caplog.at_level(logging.DEBUG):
        good = chat(c)
        bad = chat(c, cookie=_forged())
    for secret in (value, LOGIN, str(GITHUB_ID), SESSION_SECRET):
        assert secret not in caplog.text and secret not in good.text + bad.text


def _with(**update):
    return LIVE.model_copy(update=update)


@pytest.mark.parametrize(
    ("settings", "names"),
    [
        (_with(github_client_id=None), "GITHUB_CLIENT_ID"),
        (_with(github_client_id="x y"), "GITHUB_CLIENT_ID"),
        (_with(github_client_secret=None), "GITHUB_CLIENT_SECRET"),
        (_with(github_client_secret=SecretStr("   ")), "GITHUB_CLIENT_SECRET"),
        (_with(session_secret=None), "SESSION_SECRET"),
        (_with(session_secret=SecretStr("short-secret")), "SESSION_SECRET"),
        (_with(session_secret=SecretStr("sëcret-" + "s" * 40)), "SESSION_SECRET"),
        (_with(session_secret=SecretStr("secret with spaces " + "s" * 30)), "SESSION_SECRET"),
        (_with(public_site_url=None), "PUBLIC_SITE_URL"),
        (_with(public_site_url="http://site.example"), "PUBLIC_SITE_URL"),
        (_with(public_site_url="https://site.example/"), "PUBLIC_SITE_URL"),
        (_with(public_site_url="https://site.example/path"), "PUBLIC_SITE_URL"),
    ],
)
def test_live_refuses_to_start_without_github_sign_in_settings(monkeypatch, settings, names):
    for var in ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_URL"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match=names) as err:
        check_live_settings(settings)
    for value in ("short-secret", "spaces", "sëcret", "site.example"):
        assert value not in str(err.value)


def test_live_starts_with_a_localhost_site_for_local_testing(monkeypatch):
    for var in ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_URL"):
        monkeypatch.delenv(var, raising=False)
    check_live_settings(LIVE)
    check_live_settings(_with(public_site_url="http://127.0.0.1:3000"))
    check_live_settings(_with(public_site_url="http://localhost:3000"))


def test_workflow_runs_started_through_assist_count(kb_service, monkeypatch, clock):
    """A run started by /api/assist counts against the workflow bucket like /api/career/runs."""
    from test_visitor_key import data

    from gradpath.api import assist as assist_module
    from gradpath.router.schemas import RouteDecision

    decision = RouteDecision(
        route="agentic_workflow", action="run", kind="job_preparation", missing=[],
        reason="Plan request.", requires_user_profile=True, requires_multi_step_workflow=True,
        decided_by="rules",
    )  # fmt: skip
    monkeypatch.setattr(assist_module, "decide", lambda body, fast: decision)
    monkeypatch.setitem(ratelimit.PER_IP, "workflow", (Window(1, ratelimit.HOUR),))
    started = []
    monkeypatch.setattr(
        assist_module.RunStore, "start", lambda self, *a, **k: started.append(1) or "run-id"
    )
    c = live_client(monkeypatch, kb_service)
    payload = {"message": "Make me a plan", **data().model_dump(exclude={"corrections"})}
    headers = {**PASS, KEY_HEADER: KEY_A, **ip(1)}
    first = c.post("/api/assist", json=payload, headers=headers)
    second = c.post("/api/assist", json=payload, headers=headers)
    assert first.status_code == 200 and second.status_code == 429 and started == [1]


def test_one_ipv6_network_counts_as_one_client(kb_service, monkeypatch, clock):
    use(monkeypatch, settings_for("demo"))
    c = search_client(kb_service)
    codes = [
        c.post("/api/search", json={"query": "sql index"},
               headers={"X-Forwarded-For": f"2001:db8:1:2::{n}"}).status_code
        for n in range(1, 4)
    ]  # fmt: skip
    assert codes == [200, 200, 429]


def test_without_trusted_proxies_a_forged_header_changes_nothing(kb_service, monkeypatch, clock):
    use(monkeypatch, settings_for("demo", trusted_proxy_hops=0))
    c = search_client(kb_service)
    codes = [c.post("/api/search", json={"query": "sql index"}, headers=ip(n)).status_code
             for n in range(3)]  # fmt: skip
    assert codes == [200, 200, 429]  # all one client: the connection address


def test_demo_model_routes_are_refused_without_counting(monkeypatch, clock):
    use(monkeypatch, settings_for("demo"))
    c = TestClient(create_app(use_lifespan=False))
    for _ in range(10):
        assert c.post("/api/chat", json={"question": "What?"}, headers=ip(1)).status_code == 403
    assert len(ratelimit.LIMITER._events) == 0


def test_assist_refuses_a_spent_run_quota_before_routing(kb_service, monkeypatch, clock):
    from test_visitor_key import data

    from gradpath.api import assist as assist_module

    routed = []
    monkeypatch.setattr(assist_module, "decide", lambda body, fast: routed.append(1))
    c = live_client(monkeypatch, kb_service)
    for _ in range(3):  # spend the hourly workflow quota for ip(1)
        ratelimit.LIMITER.hit(("workflow", "203.0.113.1"), ratelimit.PER_IP["workflow"])
    payload = {"message": "Make me a plan", **data().model_dump(exclude={"corrections"})}
    resp = c.post("/api/assist", json=payload, headers={**PASS, KEY_HEADER: KEY_A, **ip(1)})
    assert resp.status_code == 429 and routed == []


# --- request size ---------------------------------------------------------------------------


@pytest.mark.parametrize("chunked", [False, True])
def test_a_huge_body_is_refused_before_anything_reads_it(monkeypatch, clock, chunked):
    from gradpath.api.main import MAX_BODY_BYTES

    use(monkeypatch, settings_for("demo"))
    c = TestClient(create_app(use_lifespan=False))
    big = b'{"question": "' + b"x" * (MAX_BODY_BYTES + 10) + b'"}'
    content = iter([big[:1000], big[1000:]]) if chunked else big
    resp = c.post("/api/chat", content=content, headers={"Content-Type": "application/json"})
    assert resp.status_code == 413 and plain(resp.json()) == {"detail": "The request is too large."}


def test_a_normal_body_still_works(kb_service, monkeypatch, clock):
    use(monkeypatch, settings_for("demo"))
    c = search_client(kb_service)
    assert c.post("/api/search", json={"query": "sql index " * 40}).status_code == 200

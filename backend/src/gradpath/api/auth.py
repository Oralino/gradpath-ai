"""Sign in with GitHub for live mode (T-026, always-hard area; replaced the shared passcode).

Flow (GitHub OAuth App web flow with PKCE, no scopes):
1. `GET /api/auth/github/login`: a fresh `state` and PKCE verifier go into a short-lived signed
   cookie; the browser is sent to GitHub.
2. GitHub sends the browser back to `GET /api/auth/github/callback?code&state`: the state must
   match the cookie; the code is exchanged (with the verifier and the client secret) for a token,
   which reads the visitor's public profile once and is then dropped. Accounts younger than
   GITHUB_MIN_ACCOUNT_AGE_DAYS or listed in GITHUB_BLOCKED_USERS are refused.
3. The server sets `gp_session`: "<payload>.<HMAC>" holding only the GitHub id, login and expiry.
   No database: the signature is the proof. `deps.require_session` checks it on live routes.

Every redirect goes to a fixed address built from PUBLIC_SITE_URL, never one the caller chose.
Nothing here logs a GitHub id, login, code, token, state or cookie: only the outcome.
"""

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from gradpath.api import ratelimit
from gradpath.config import Settings, get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_COOKIE = "gp_session"
OAUTH_COOKIE = "gp_oauth"
OAUTH_PATH = "/api/auth/github"
OAUTH_TTL_S = 600  # GitHub's codes expire after 10 minutes too
AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
SIGNIN_NEEDED = "Sign in with GitHub to use your own key here."
AUTH_OFF = "Sign-in is off on this server."
# Where a finished sign-in lands: the site's home page with one of these outcome codes.
OUTCOMES = ("ok", "too_new", "blocked", "denied", "failed")

# Bounds before any parsing: cookies and query values are client text.
SIGNED_SHAPE = re.compile(r"([A-Za-z0-9_-]{1,700})\.([0-9a-f]{64})")
CODE_SHAPE = re.compile(r"[A-Za-z0-9_-]{1,100}")
STATE_SHAPE = re.compile(r"[A-Za-z0-9_-]{20,100}")
LOGIN_SHAPE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")

# Injected by tests: the clock and the HTTP client that talks to GitHub.
now: Callable[[], float] = time.time


def github_client() -> httpx.Client:
    """The client for the two GitHub calls: short timeout, no retries, no redirects followed, and
    no proxy or certificate settings taken from the environment (`trust_env=False`), so nothing
    outside the code can route the client secret elsewhere. No API version header: GitHub's
    default version serves `/user` (T-026 review: an unknown version would fail every sign-in)."""
    return httpx.Client(timeout=10.0, follow_redirects=False, trust_env=False)


@dataclass(frozen=True)
class Session:
    """A signed-in visitor, as read back from `gp_session`."""

    github_id: int
    login: str
    expires: int


# --- signing -------------------------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(secret: str, purpose: str, body: str) -> str:
    """HMAC-SHA256 over purpose|body: the purpose keeps a sign-in cookie from passing as a
    session cookie (and the other way round), though both use SESSION_SECRET."""
    return hmac.new(secret.encode(), f"{purpose}|{body}".encode(), hashlib.sha256).hexdigest()


def sign(secret: str, purpose: str, payload: dict) -> str:
    """ "<base64url JSON>.<hex HMAC>". Called for both cookies; read back with `unsign`."""
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    return f"{body}.{_mac(secret, purpose, body)}"


def unsign(secret: str, purpose: str, value: str, max_ttl: int) -> dict | None:
    """The payload of a value `sign` made for this purpose, or None: wrong shape, bad signature
    (constant-time compare), not JSON, no integer `exp`, expired, or claiming more than
    `max_ttl` (+60 s of clock skew) of remaining life."""
    match = SIGNED_SHAPE.fullmatch(value.strip()) if value else None
    if match is None:
        return None
    body, mac = match.groups()
    if not hmac.compare_digest(mac, _mac(secret, purpose, body)):
        return None
    try:
        payload = json.loads(_unb64(body))
    except ValueError:
        return None
    exp = payload.get("exp") if isinstance(payload, dict) else None
    if not isinstance(exp, int) or isinstance(exp, bool):
        return None
    t = now()
    if exp <= t or exp > t + max_ttl + 60:
        return None
    return payload


def _secret(settings: Settings) -> str:
    """SESSION_SECRET; `check_live_settings` guarantees one in live mode."""
    if settings.session_secret is None:
        raise HTTPException(status_code=404, detail=AUTH_OFF)
    return settings.session_secret.get_secret_value()


def session_cookie(settings: Settings, github_id: int, login: str) -> tuple[str, int]:
    """A new session value for this GitHub user, and its expiry (epoch seconds)."""
    expires = int(now()) + settings.session_ttl_s
    payload = {"exp": expires, "id": github_id, "login": login}
    return sign(_secret(settings), "session", payload), expires


def read_session(request: Request, settings: Settings) -> Session | None:
    """The visitor's session from `gp_session`, or None (missing, forged, expired, malformed, or
    the user is blocked now). Used by `deps.require_session` and `GET /api/auth/me`."""
    if settings.session_secret is None:
        return None
    raw = request.cookies.get(SESSION_COOKIE, "")
    payload = unsign(_secret(settings), "session", raw, settings.session_ttl_s)
    if payload is None:
        return None
    github_id, login = payload.get("id"), payload.get("login")
    if not isinstance(github_id, int) or isinstance(github_id, bool) or github_id <= 0:
        return None
    if not isinstance(login, str) or not LOGIN_SHAPE.fullmatch(login):
        return None
    if is_blocked(settings, github_id, login):
        return None
    return Session(github_id=github_id, login=login, expires=payload["exp"])


def is_blocked(settings: Settings, github_id: int, login: str) -> bool:
    """GITHUB_BLOCKED_USERS names this user (by login, case-insensitive, or numeric id)."""
    blocked = {b.strip().lower() for b in settings.github_blocked_users.split(",") if b.strip()}
    return login.lower() in blocked or str(github_id) in blocked


# --- routes --------------------------------------------------------------------------------


def _live_only(settings: Settings) -> None:
    if settings.app_mode != "live":
        raise HTTPException(status_code=404, detail=AUTH_OFF)


def _site(settings: Settings) -> str:
    return (settings.public_site_url or "").rstrip("/")


def _callback_url(settings: Settings) -> str:
    return f"{_site(settings)}{OAUTH_PATH}/callback"


def _secure(settings: Settings) -> bool:
    """Secure cookies whenever the site is https (always when deployed; `check_live_settings`
    allows http only for a localhost site)."""
    return _site(settings).startswith("https://")


def _pkce_challenge(verifier: str) -> str:
    return _b64(hashlib.sha256(verifier.encode()).digest())


@router.get("/github/login", include_in_schema=False)
def login(request: Request) -> Response:
    """Start a sign-in: new state + PKCE verifier in a signed cookie, then off to GitHub."""
    settings = get_settings()
    _live_only(settings)
    ratelimit.charge("auth", request)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)  # 86 characters (PKCE allows 43-128)
    params = {
        "client_id": settings.github_client_id or "",
        "redirect_uri": _callback_url(settings),
        "state": state,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
        "allow_signup": "false",  # a brand-new account would be refused anyway (account age)
    }
    response = RedirectResponse(f"{AUTHORIZE_URL}?{urlencode(params)}", status_code=302)
    value = sign(
        _secret(settings), "oauth", {"exp": int(now()) + OAUTH_TTL_S, "s": state, "v": verifier}
    )
    response.set_cookie(
        OAUTH_COOKIE, value, max_age=OAUTH_TTL_S, path=OAUTH_PATH,
        secure=_secure(settings), httponly=True, samesite="lax",
    )  # fmt: skip
    response.headers["Cache-Control"] = "no-store"
    return response


def _finish(settings: Settings, outcome: str) -> RedirectResponse:
    """Back to the site's home page with an outcome code; the sign-in cookie is always cleared."""
    response = RedirectResponse(f"{_site(settings)}/?signin={outcome}", status_code=303)
    response.delete_cookie(
        OAUTH_COOKIE, path=OAUTH_PATH, secure=_secure(settings), httponly=True, samesite="lax"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _parse_created(value: object) -> datetime | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        created = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return created if created.tzinfo is not None else None


def _github_user(settings: Settings, code: str, verifier: str) -> dict | None:
    """Exchange the code (with the PKCE verifier and client secret) and read the public profile.
    The GitHub token lives only inside this function. None on any failure; logs the step only."""
    client_secret = settings.github_client_secret
    secret = client_secret.get_secret_value() if client_secret is not None else ""
    with github_client() as client:
        reply = client.post(
            TOKEN_URL,
            data={
                "client_id": settings.github_client_id or "",
                "client_secret": secret,
                "code": code,
                "redirect_uri": _callback_url(settings),
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json", "User-Agent": "GradPath"},
        )
        body = reply.json() if reply.status_code == 200 else {}
        token = body.get("access_token") if isinstance(body, dict) else None
        if not isinstance(token, str) or not token:
            log.warning("github sign-in: code exchange refused (HTTP %d)", reply.status_code)
            return None
        user = client.get(
            USER_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "GradPath",
            },
        )
        if user.status_code != 200:
            log.warning("github sign-in: profile read failed (HTTP %d)", user.status_code)
            return None
        profile = user.json()
    return profile if isinstance(profile, dict) else None


@router.get("/github/callback", include_in_schema=False)
def callback(request: Request) -> Response:
    """GitHub's redirect back: check state, exchange the code, check age and block list, then
    set the session cookie. Every outcome ends on the site's home page (`_finish`)."""
    settings = get_settings()
    _live_only(settings)
    ratelimit.charge("auth", request)
    query = request.query_params
    pending = unsign(_secret(settings), "oauth", request.cookies.get(OAUTH_COOKIE, ""), OAUTH_TTL_S)
    if query.get("error"):  # e.g. access_denied: the visitor pressed Cancel on GitHub
        log.info("github sign-in: denied on GitHub")
        return _finish(settings, "denied")
    state, code = query.get("state", ""), query.get("code", "")
    if (
        pending is None
        or not isinstance(pending.get("s"), str)
        or not isinstance(pending.get("v"), str)
        or not STATE_SHAPE.fullmatch(state)
        or not CODE_SHAPE.fullmatch(code)
        or not hmac.compare_digest(state, pending["s"])
    ):
        log.info("github sign-in: missing or mismatched state")
        return _finish(settings, "failed")
    try:
        profile = _github_user(settings, code, pending["v"])
    except (httpx.HTTPError, ValueError) as exc:  # network, timeout, or a non-JSON reply
        log.warning("github sign-in: %s", type(exc).__name__)
        profile = None
    if profile is None:
        return _finish(settings, "failed")
    github_id, login = profile.get("id"), profile.get("login")
    created = _parse_created(profile.get("created_at"))
    if (
        not isinstance(github_id, int)
        or isinstance(github_id, bool)
        or github_id <= 0
        or not isinstance(login, str)
        or not LOGIN_SHAPE.fullmatch(login)
        or created is None
    ):
        log.warning("github sign-in: unexpected profile shape")
        return _finish(settings, "failed")
    age_days = (datetime.fromtimestamp(now(), UTC) - created).total_seconds() / 86_400
    if age_days < settings.github_min_account_age_days:
        log.info("github sign-in: refused, account too new")
        return _finish(settings, "too_new")
    if is_blocked(settings, github_id, login):
        log.info("github sign-in: refused, blocked user")
        return _finish(settings, "blocked")
    value, _ = session_cookie(settings, github_id, login)
    response = _finish(settings, "ok")
    response.set_cookie(
        SESSION_COOKIE, value, max_age=settings.session_ttl_s, path="/",
        secure=_secure(settings), httponly=True, samesite="lax",
    )  # fmt: skip
    log.info("github sign-in: ok")
    return response


@router.get("/me", include_in_schema=False)
def me(request: Request, response: Response) -> dict:
    """Whether this browser is signed in, for the live panel: {signed_in, login, expires_at}."""
    settings = get_settings()
    _live_only(settings)
    response.headers["Cache-Control"] = "no-store"
    session = read_session(request, settings)
    if session is None:
        return {"signed_in": False, "login": None, "expires_at": None}
    expires = datetime.fromtimestamp(session.expires, UTC).isoformat()
    return {"signed_in": True, "login": session.login, "expires_at": expires}


@router.post("/logout", status_code=204, include_in_schema=False)
def logout() -> Response:
    """Clear the session cookie (OriginCheck refuses a cross-site POST before this runs)."""
    settings = get_settings()
    _live_only(settings)
    response = Response(status_code=204)
    response.delete_cookie(
        SESSION_COOKIE, path="/", secure=_secure(settings), httponly=True, samesite="lax"
    )
    return response

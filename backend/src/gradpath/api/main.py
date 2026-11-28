"""FastAPI application. Run from `backend/`: uv run uvicorn gradpath.api.main:app --reload"""

import functools
import json
import logging
import os
import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

import anthropic
import pydantic
import voyageai.error
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from gradpath.api.assist import router as assist_router
from gradpath.api.auth import router as auth_router
from gradpath.api.career import router as career_router
from gradpath.api.chat import router as chat_router
from gradpath.api.debug import router as debug_router
from gradpath.api.demo import router as demo_router
from gradpath.api.jobs import router as jobs_router
from gradpath.api.live import router as live_router
from gradpath.api.profile import router as profile_router
from gradpath.api.ratelimit import PROXY_SECRET_HEADER, from_site
from gradpath.api.runs import router as runs_router
from gradpath.api.search import router as search_router
from gradpath.config import REPO_ROOT, Settings, get_settings
from gradpath.demo import load_library
from gradpath.ingestion.embed import WindowFull
from gradpath.ingestion.index_info import read_index_info
from gradpath.providers import ClaudeCodeError
from gradpath.retrieval import RetrievalService, get_retrieval_service
from gradpath.retrieval.budget import DailyBudgetSpent, TotalBudgetSpent
from gradpath.tracing import configure_tracing, flush

log = logging.getLogger(__name__)

LLM_DOWN = "The language model is unavailable. Try again later."
LLM_INVALID = "The language model returned an invalid response. Try again."
SEARCH_LIMITED = "Search is rate limited on the free tier. Try again in a minute."
SEARCH_DOWN = "Search is unavailable. Try again later."
BUDGET_DAILY = "Search has reached today's limit on this free demo. Try again tomorrow."
BUDGET_TOTAL = "Search is paused on this server. Browse the recorded examples instead."
WORKFLOW_LIMIT = "The preparation workflow stopped at its step limit. Try again."
KEY_REFUSED = "Anthropic refused this API key. Check the key, then try again."
KEY_LIMITED = "Your Anthropic key is at its rate limit. Wait a minute, then try again."
# Loggers that could print request details at DEBUG; capped in live mode (visitor keys).
QUIET_IN_LIVE = ("anthropic", "httpx", "httpcore")
REDIRECT_VARS = ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_URL")
MIN_SESSION_SECRET_CHARS = 32
GITHUB_CLIENT_ID_SHAPE = re.compile(r"[A-Za-z0-9._-]{8,64}")
# PUBLIC_SITE_URL: an https origin (no path, query or trailing slash), or a localhost origin over
# http for testing live mode on the owner's PC.
SITE_SHAPE = re.compile(
    r"https://[A-Za-z0-9.-]{1,253}(:[0-9]{1,5})?|http://(localhost|127\.0\.0\.1)(:[0-9]{1,5})?"
)


def _strong_secret(value: str) -> bool:
    """32+ printable ASCII characters, no spaces: the shape `check_live_settings` asks of
    SESSION_SECRET and PROXY_SHARED_SECRET (Render's Generate button makes such a value)."""
    return len(value) >= MIN_SESSION_SECRET_CHARS and all(33 <= ord(c) <= 126 for c in value)


def check_live_settings(settings: Settings) -> None:
    """Refuse to start live mode unless every model call must use the visitor's key (the
    provider is the Anthropic API, no server key is set: owner rule, no key the owner pays for)
    and GitHub sign-in guards it (T-026: client id and secret, a 32+ character session secret, an
    https site URL). A set PROXY_SHARED_SECRET must be strong in every mode (T-020 step 4: a weak
    one would let callers pick their rate-limit bucket). Called by `lifespan`; the message names
    settings, never values."""
    proxy = settings.proxy_shared_secret
    if proxy is not None and not _strong_secret(proxy.get_secret_value()):
        raise RuntimeError(
            f"PROXY_SHARED_SECRET, when set, needs {MIN_SESSION_SECRET_CHARS}+ printable ASCII "
            "characters"
        )
    if settings.app_mode != "live":
        return
    if settings.llm_provider != "anthropic_api":
        raise RuntimeError("APP_MODE=live needs LLM_PROVIDER=anthropic_api (visitor keys)")
    if settings.anthropic_api_key is not None:
        raise RuntimeError("APP_MODE=live must not have ANTHROPIC_API_KEY set on the server")
    if not GITHUB_CLIENT_ID_SHAPE.fullmatch((settings.github_client_id or "").strip()):
        raise RuntimeError("APP_MODE=live needs GITHUB_CLIENT_ID (the GitHub OAuth App's id)")
    client_secret = settings.github_client_secret
    if client_secret is None or not client_secret.get_secret_value().strip():
        raise RuntimeError("APP_MODE=live needs GITHUB_CLIENT_SECRET (the OAuth App's secret)")
    secret = "" if settings.session_secret is None else settings.session_secret.get_secret_value()
    if not _strong_secret(secret):
        raise RuntimeError(
            f"APP_MODE=live needs SESSION_SECRET of {MIN_SESSION_SECRET_CHARS}+ printable ASCII "
            "characters"
        )
    if not SITE_SHAPE.fullmatch(settings.public_site_url or ""):
        raise RuntimeError(
            "APP_MODE=live needs PUBLIC_SITE_URL: the site's https origin, no trailing slash"
        )
    # The Anthropic SDK and langchain_anthropic read these from the process environment: set on
    # the server, they would send every visitor's key to another host.
    for name in REDIRECT_VARS:
        if os.environ.get(name, "").strip():
            raise RuntimeError(
                f"APP_MODE=live must not have {name} set (it redirects visitor keys)"
            )
    for name in QUIET_IN_LIVE:
        logging.getLogger(name).setLevel(logging.WARNING)


class Health(BaseModel):
    status: str
    llm_provider: str
    app_mode: str
    sources_as_of: date | None = None
    sources_newest: date | None = None
    search_enabled: bool = False  # source search works on this server (T-018 step 9)


# A loc part we echo back as is: a plain field name (or an index). Anything else could be text the
# client chose, such as an unknown field named after a secret. Note: no request model has a
# dict field today; if one is added, its keys are client text that this pattern would echo when
# they look like identifiers (mask loc parts that aren't model field names then).
SAFE_LOC = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
UNKNOWN_FIELD = "(unknown field)"


def safe_validation_errors(errors: Sequence[Any]) -> list[dict[str, Any]]:
    """FastAPI's 422 errors without what the client sent (T-018 step 6, found in T-017): only
    `loc`, `msg` and `type` stay, `input` and `ctx` (which can quote the rejected value, e.g. a key
    pasted into the wrong field) are dropped, and `loc` keeps only field names and indexes. The
    frontend reads `loc` alone (`lib/api.ts` fieldPaths). Called by `_validation_handler`."""
    cleaned = []
    for error in errors:
        loc = list(error.get("loc", ()))
        if error.get("type") == "extra_forbidden" and loc:
            loc[-1] = UNKNOWN_FIELD  # the name of an unknown field is client text
        safe = [
            part if isinstance(part, int) or part == UNKNOWN_FIELD
            or (isinstance(part, str) and SAFE_LOC.fullmatch(part)) else "?"
            for part in loc
        ]  # fmt: skip
        cleaned.append(
            {
                "loc": safe,
                "msg": str(error.get("msg", ""))[:200],
                "type": str(error.get("type", "")),
            }
        )
    return cleaned


async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 for a request that failed validation, with `safe_validation_errors` as its detail.
    Logged by count only (the errors themselves can carry the client's text)."""
    errors = exc.errors()
    log.info("validation failed on %s (%d errors)", request.url.path, len(errors))
    return JSONResponse(
        {"detail": safe_validation_errors(errors), "code": "validation"}, status_code=422
    )


@functools.cache
def error_codes() -> dict[str, str]:
    """Every fixed error message the API sends, mapped to a stable machine-readable code, so the
    frontend can tell signed-out from bad-key from rate-limited without matching text (T-018
    step 9). Used by the error handlers; a test checks every raised detail has a code."""
    from gradpath.api import auth, career, demo, deps, limits, live, ratelimit, runs, search

    return {
        deps.MODEL_ROUTES_OFF: "demo_mode",
        auth.SIGNIN_NEEDED: "signin_required",
        auth.AUTH_OFF: "auth_off",
        deps.KEY_NEEDED: "key_required",
        ratelimit.LIMITED: "rate_limited",
        KEY_REFUSED: "key_refused",
        KEY_LIMITED: "key_rate_limited",
        search.SEARCH_OFF: "search_off",
        SEARCH_LIMITED: "search_rate_limited",
        SEARCH_DOWN: "search_unavailable",
        BUDGET_DAILY: "search_budget_daily",
        BUDGET_TOTAL: "search_budget_spent",
        LLM_DOWN: "llm_unavailable",
        LLM_INVALID: "llm_invalid",
        WORKFLOW_LIMIT: "workflow_limit",
        limits.BUSY: "busy",
        career.BUSY: "busy",
        runs.NOT_FOUND: "run_not_found",
        demo.NOT_FOUND: "recording_not_found",
        live.LIVE_OFF: "live_off",
        "Not Found": "not_found",
        "Method Not Allowed": "method_not_allowed",
        "Internal Server Error": "server_error",
    }


async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Every HTTPException as {"detail", "code"}; details are fixed text (no client input)."""
    detail = exc.detail if isinstance(exc.detail, str) else "Error"
    body = {"detail": detail, "code": error_codes().get(detail, "error")}
    return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)


def _error_handler(status: int, detail: str):
    """Handler that logs the exception server-side and returns a fixed message.

    Used by `create_app`; the response never carries exception text, keys or prompts.
    """

    async def handler(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, pydantic.ValidationError):
            # Its message quotes the model's reply, which can echo posting or profile text.
            log.error(
                "%s on %s (%d errors)", type(exc).__name__, request.url.path, exc.error_count()
            )
        elif isinstance(exc, (ClaudeCodeError, anthropic.APIError, voyageai.error.VoyageError)):
            # Their messages can carry model or SDK text, which can quote a resume, a profile
            # (T-014) or a search query (T-018): log the type only, no message or traceback.
            log.error("%s on %s", type(exc).__name__, request.url.path)
        else:
            log.error("%s on %s", type(exc).__name__, request.url.path, exc_info=exc)
        return JSONResponse(
            {"detail": detail, "code": error_codes().get(detail, "error")}, status_code=status
        )

    return handler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load the demo recordings and the index info, and open the retrieval service once per process.

    Demo mode opens retrieval only for source search, and only with a Voyage key, so the API still
    starts with no keys at all (T-018); its model routes are refused by `deps.require_model_routes`.
    Qdrant's local (file) mode allows one open client per folder, so routes share this one
    instead of creating their own.
    Tests set `app.state` themselves and skip this. Tracing is decided here, once per process.
    """
    settings = get_settings()
    check_live_settings(settings)
    configure_tracing(settings)
    if getattr(app.state, "demo", None) is None:
        app.state.demo = load_library(REPO_ROOT / settings.demo_runs_path)
    if getattr(app.state, "index_info", None) is None:
        app.state.index_info = read_index_info(REPO_ROOT / settings.index_info_path)
    if getattr(app.state, "retrieval", None) is None:
        app.state.retrieval = open_retrieval(settings)
    try:
        yield
    finally:
        try:
            retrieval = getattr(app.state, "retrieval", None)
            if retrieval is not None:
                retrieval.store.client.close()
        finally:
            flush()


def open_retrieval(settings: Settings) -> RetrievalService | None:
    """The retrieval service for this mode (called by `lifespan`). Local and live need it, so a
    failure stops startup. Demo needs it only for source search (T-018 step 4): without a Voyage
    key it stays closed, and a failure to open it turns search off instead of stopping demo mode."""
    if settings.app_mode != "demo":
        return get_retrieval_service(settings)
    if not settings.search_enabled:
        log.info("SEARCH_ENABLED=false: source search is off")
        return None
    key = settings.voyage_api_key
    if key is None or not key.get_secret_value().strip():
        log.info("demo mode without VOYAGE_API_KEY: source search is off")
        return None
    try:
        return get_retrieval_service(settings)
    except Exception as exc:  # type only: messages can carry connection details
        log.error("source search is off: retrieval failed to open (%s)", type(exc).__name__)
        return None


MAX_BODY_BYTES = 256 * 1024  # largest real body: ~12k profile + 20k posting, JSON-escaped
TOO_LARGE = b'{"detail":"The request is too large.","code":"too_large"}'


class BodySizeLimit:
    """Refuse request bodies over MAX_BODY_BYTES with 413 before the app reads them (T-018 step
    7: FastAPI parses the body before any guard runs). Checks Content-Length first, then counts
    streamed bytes, buffering at most the limit. Added by `create_app`."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = dict(scope.get("headers") or []).get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > MAX_BODY_BYTES):
            await self._refuse(send)
            return
        body, more = b"", True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                break
            body += message.get("body", b"")
            more = message.get("more_body", False)
            if len(body) > MAX_BODY_BYTES:
                await self._refuse(send)
                return
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def _refuse(send) -> None:
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json")]})  # fmt: skip
        await send({"type": "http.response.body", "body": TOO_LARGE})


CROSS_SITE = b'{"detail":"Cross-site requests are not accepted.","code":"cross_site"}'
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SITE_ONLY = b'{"detail":"Use GradPath through its website.","code":"site_only"}'
# The one route a caller may reach without the site's secret: the host's health check calls the
# API directly (Render: /api/health), and it reveals nothing beyond the footer's facts.
OPEN_ROUTES = {("GET", "/api/health")}


# Browser protections on every API reply (T-020 step 5, SECURITY.md); the site sets the same three
# on its pages (frontend/next.config.ts). Its headers() can't reach replies the site forwards from
# here, so the API adds them itself; Vercel passes them through.
SECURITY_HEADERS = [
    (b"x-frame-options", b"DENY"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
]


class SecurityHeaders:
    """Add SECURITY_HEADERS to every HTTP response that doesn't already set them, including the
    guards' own 403/413 replies (added by `create_app` outermost). Raw ASGI, like the guards."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                present = {k.lower() for k, _ in message.get("headers") or []}
                extra = [(k, v) for k, v in SECURITY_HEADERS if k not in present]
                message = {**message, "headers": [*(message.get("headers") or []), *extra]}
            await send(message)

        await self.app(scope, receive, send_with_headers)


class SiteOnly:
    """Once PROXY_SHARED_SECRET is set (the deployed site), refuse every request that did not come
    through the site's own server (403), except the health check: "origin cloaking", owner
    decision T-020 step 4. Callers who skip the site can't use the API, its docs or its debug
    page at all. Unset (local, CI, the Docker smoke test): no effect. Uses `ratelimit.from_site`
    (constant-time compare); added by `create_app` right inside `SecurityHeaders`, before
    anything reads the body.
    Only "http" scopes are checked: the app has no websocket routes, and lifespan must pass."""

    warned_mismatch = False

    def __init__(self, app) -> None:
        self.app = app

    @classmethod
    def _warn_mismatch(cls, scope) -> None:
        """A wrong secret header (not a missing one) usually means Render's and Vercel's values
        differ: the whole site is then refused. Logged once per process, never with a value."""
        if cls.warned_mismatch:
            return
        if any(k == PROXY_SECRET_HEADER.encode() for k, _ in scope.get("headers") or []):
            cls.warned_mismatch = True
            log.warning(
                "site only: a request carried a wrong site secret (Render and Vercel values "
                "differ, or a guess); refusing"
            )

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            settings = get_settings()
            secret = settings.proxy_shared_secret
            if (
                secret is not None
                and secret.get_secret_value()
                and (scope.get("method", ""), scope.get("path", "")) not in OPEN_ROUTES
                and not from_site(Request(scope), settings)
            ):
                self._warn_mismatch(scope)
                await send({"type": "http.response.start", "status": 403,
                            "headers": [(b"content-type", b"application/json"),
                                        (b"cache-control", b"no-store")]})  # fmt: skip
                await send({"type": "http.response.body", "body": SITE_ONLY})
                return
        await self.app(scope, receive, send)


def allowed_origins(settings: Settings) -> frozenset[str]:
    """The ALLOWED_ORIGINS setting as a set (trailing slashes and case don't matter)."""
    return frozenset(
        o.strip().rstrip("/").lower() for o in settings.allowed_origins.split(",") if o.strip()
    )


class RedactAuthQuery(logging.Filter):
    """Hides the query string of `/api/auth/` requests in uvicorn's access log (T-026): GitHub's
    callback carries the one-time `code` and `state` there, and the access log is what Render
    keeps. Installed on the "uvicorn.access" logger by `create_app`."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        # uvicorn's access record: (client_addr, method, full_path, http_version, status_code)
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            path = args[2]
            if path.startswith("/api/auth/") and "?" in path:
                record.args = (*args[:2], path.split("?", 1)[0] + "?[redacted]", *args[3:])
        return True


def _redact_auth_queries() -> None:
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactAuthQuery) for f in access.filters):
        access.addFilter(RedactAuthQuery())


class OriginCheck:
    """Refuse a state-changing request whose Origin header names a site not in ALLOWED_ORIGINS
    (403), before anything reads it (T-018 step 8, guide 01: CORS is not CSRF protection, check
    Origin too). Browsers send Origin on every cross-site POST, including form posts; requests
    with no Origin (curl, server-to-server) pass. `null` (sandboxed or privacy-redirected pages) is
    refused. Added by `create_app`, right inside `SiteOnly`."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope.get("method", "") in UNSAFE_METHODS:
            origins = [v for k, v in scope.get("headers") or [] if k == b"origin"]
            if origins:
                # Browsers send exactly one; more than one is refused rather than guessed at.
                value = origins[0].decode("latin-1").strip().rstrip("/").lower()
                if len(origins) > 1 or value not in allowed_origins(get_settings()):
                    await send({"type": "http.response.start", "status": 403,
                                "headers": [(b"content-type", b"application/json")]})  # fmt: skip
                    await send({"type": "http.response.body", "body": CROSS_SITE})
                    return
        await self.app(scope, receive, send)


def create_app(*, use_lifespan: bool = True) -> FastAPI:
    """Build the app; tests pass `use_lifespan=False` and provide their own dependencies."""
    app = FastAPI(
        title="GradPath AI",
        version="0.1.0",
        summary="Adaptive RAG + agentic career preparation for new-grad engineers.",
        lifespan=lifespan if use_lifespan else None,
    )
    _redact_auth_queries()
    app.add_middleware(BodySizeLimit)
    app.add_middleware(OriginCheck)
    app.add_middleware(SiteOnly)
    app.add_middleware(SecurityHeaders)  # added last = runs first
    # Deliberately no CORSMiddleware: cross-origin browser reads stay blocked (T-018 step 8).
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    # Subclasses are matched first (voyageai.error.RateLimitError before VoyageError).
    for exc_type, status, detail in [
        (ClaudeCodeError, 502, LLM_DOWN),
        (anthropic.APIError, 502, LLM_DOWN),
        # A visitor's key (live mode): refused or at its own limit. Matched before APIError by
        # class (Starlette picks the most specific handler).
        (anthropic.AuthenticationError, 401, KEY_REFUSED),
        (anthropic.PermissionDeniedError, 401, KEY_REFUSED),
        (anthropic.RateLimitError, 429, KEY_LIMITED),
        (voyageai.error.RateLimitError, 429, SEARCH_LIMITED),
        (WindowFull, 429, SEARCH_LIMITED),
        (voyageai.error.VoyageError, 503, SEARCH_DOWN),
        (DailyBudgetSpent, 503, BUDGET_DAILY),
        (TotalBudgetSpent, 503, BUDGET_TOTAL),
        (pydantic.ValidationError, 502, LLM_INVALID),
        (json.JSONDecodeError, 502, LLM_INVALID),
        # Anything not listed (a guard error, a missing service) gets FastAPI's default 500,
        # "Internal Server Error", which carries no exception text either.
        (GraphRecursionError, 500, WORKFLOW_LIMIT),
    ]:
        app.add_exception_handler(exc_type, _error_handler(status, detail))
    app.include_router(chat_router)
    app.include_router(jobs_router)
    app.include_router(career_router)
    app.include_router(assist_router)
    app.include_router(profile_router)
    app.include_router(runs_router)
    app.include_router(demo_router)
    app.include_router(search_router)
    app.include_router(live_router)
    app.include_router(auth_router)
    app.include_router(debug_router)

    @app.get("/api/health", tags=["meta"], response_model=Health)
    def health(request: Request) -> Health:
        """Liveness plus what the footer shows: the sources date (null when unknown)."""
        s = get_settings()
        info = getattr(request.app.state, "index_info", None)
        return Health(
            status="ok",
            llm_provider=s.llm_provider,
            app_mode=s.app_mode,
            sources_as_of=info.sources_as_of if info else None,
            sources_newest=info.sources_newest if info else None,
            search_enabled=getattr(request.app.state, "retrieval", None) is not None
            and s.search_enabled,
        )

    return app


app = create_app()

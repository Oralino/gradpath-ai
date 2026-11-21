"""FastAPI application. Run from `backend/`: uv run uvicorn gradpath.api.main:app --reload"""

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

from gradpath.api.assist import router as assist_router
from gradpath.api.career import router as career_router
from gradpath.api.chat import router as chat_router
from gradpath.api.demo import router as demo_router
from gradpath.api.jobs import router as jobs_router
from gradpath.api.profile import router as profile_router
from gradpath.api.runs import router as runs_router
from gradpath.api.search import router as search_router
from gradpath.config import REPO_ROOT, Settings, get_settings
from gradpath.demo import load_library
from gradpath.ingestion.embed import WindowFull
from gradpath.ingestion.index_info import read_index_info
from gradpath.providers import ClaudeCodeError
from gradpath.retrieval import RetrievalService, get_retrieval_service
from gradpath.tracing import configure_tracing, flush

log = logging.getLogger(__name__)

LLM_DOWN = "The language model is unavailable. Try again later."
LLM_INVALID = "The language model returned an invalid response. Try again."
SEARCH_LIMITED = "Search is rate limited on the free tier. Try again in a minute."
SEARCH_DOWN = "Search is unavailable. Try again later."
WORKFLOW_LIMIT = "The preparation workflow stopped at its step limit. Try again."
KEY_REFUSED = "Anthropic refused this API key. Check the key, then try again."
KEY_LIMITED = "Your Anthropic key is at its rate limit. Wait a minute, then try again."
# Loggers that could print request details at DEBUG; capped in live mode (visitor keys).
QUIET_IN_LIVE = ("anthropic", "httpx", "httpcore")
REDIRECT_VARS = ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_URL")
MIN_PASSCODE_CHARS = 16


def check_live_settings(settings: Settings) -> None:
    """Refuse to start live mode unless every model call must use the visitor's key (the
    provider is the Anthropic API, no server key is set: owner rule, no key the owner pays for)
    and a passcode of 16+ characters guards it (T-018 step 7). Called by `lifespan`; the message
    names settings, never values."""
    if settings.app_mode != "live":
        return
    if settings.llm_provider != "anthropic_api":
        raise RuntimeError("APP_MODE=live needs LLM_PROVIDER=anthropic_api (visitor keys)")
    if settings.anthropic_api_key is not None:
        raise RuntimeError("APP_MODE=live must not have ANTHROPIC_API_KEY set on the server")
    passcode = "" if settings.live_passcode is None else settings.live_passcode.get_secret_value()
    passcode = passcode.strip()
    if len(passcode) < MIN_PASSCODE_CHARS or not all(33 <= ord(c) <= 126 for c in passcode):
        raise RuntimeError(
            f"APP_MODE=live needs LIVE_PASSCODE of {MIN_PASSCODE_CHARS}+ printable ASCII characters"
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
    return JSONResponse({"detail": safe_validation_errors(errors)}, status_code=422)


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
        return JSONResponse({"detail": detail}, status_code=status)

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
TOO_LARGE = b'{"detail":"The request is too large."}'


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


CROSS_SITE = b'{"detail":"Cross-site requests are not accepted."}'
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def allowed_origins(settings: Settings) -> frozenset[str]:
    """The ALLOWED_ORIGINS setting as a set (trailing slashes and case don't matter)."""
    return frozenset(
        o.strip().rstrip("/").lower() for o in settings.allowed_origins.split(",") if o.strip()
    )


class OriginCheck:
    """Refuse a state-changing request whose Origin header names a site not in ALLOWED_ORIGINS
    (403), before anything reads it (T-018 step 8, guide 01: CORS is not CSRF protection, check
    Origin too). Browsers send Origin on every cross-site POST, including form posts; requests
    with no Origin (curl, server-to-server) pass. `null` (sandboxed or privacy-redirected pages) is
    refused. Added by `create_app`, outermost."""

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
    app.add_middleware(BodySizeLimit)
    app.add_middleware(OriginCheck)  # added last = runs first
    # Deliberately no CORSMiddleware: cross-origin browser reads stay blocked (T-018 step 8).
    app.add_exception_handler(RequestValidationError, _validation_handler)
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
        )

    return app


app = create_app()

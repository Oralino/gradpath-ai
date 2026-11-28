"""FastAPI dependencies: the shared retrieval service, the chat models, the demo recordings, the
visitor's key in live mode, and the mode guard on routes that call models.

Routes depend on these functions (not on globals), so tests swap in fakes with
`app.dependency_overrides`.

Visitor keys (T-018 step 5, always-hard area): in live mode the key arrives in the
`X-Anthropic-Key` header on each request, is checked for shape only, and is passed straight into
the model clients. It is never stored, logged, traced or returned. A header is used rather than a
body field because FastAPI echoes rejected body values back in 422 responses.
"""

import hashlib
import hmac
import re
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import SecretStr

from gradpath.api.auth import SIGNIN_NEEDED, Session, read_session
from gradpath.config import Settings, get_settings
from gradpath.demo import DemoLibrary
from gradpath.providers import get_chat_model
from gradpath.retrieval import RetrievalService

KEY_HEADER = "X-Anthropic-Key"
MODEL_ROUTES_OFF = "This site runs in demo mode: browse the recorded examples instead."
KEY_NEEDED = "Add your Anthropic API key to use live mode. It is sent with each request only."
# Shape only (no network call): Anthropic keys start with sk-ant-. Bounded so a huge header can't
# reach the model client; the character set keeps it a plain token.
KEY_SHAPE = re.compile(r"sk-ant-[A-Za-z0-9_-]{20,200}")
# Per-process secret for run ownership tags: a run is tied to its starter's key without keeping
# the key, and a restart (which forgets all runs anyway) changes the secret.
_RUN_SECRET = secrets.token_bytes(32)


def visitor_key(request: Request) -> SecretStr | None:
    """The request's key in live mode, else None. Demo is refused here (403). Live needs a GitHub
    sign-in first (T-026: 401 `signin_required` without a valid session cookie) and then a
    well-formed key header (401), all before any model or retrieval is built. Local mode ignores
    both: the owner's machine uses the server's own provider."""
    settings = get_settings()
    mode = settings.app_mode
    if mode == "local":
        return None
    if mode != "live":  # demo, or anything unexpected: deny by default
        raise HTTPException(status_code=403, detail=MODEL_ROUTES_OFF)
    require_session(request, settings)
    raw = request.headers.get(KEY_HEADER, "").strip()
    if not KEY_SHAPE.fullmatch(raw):
        raise HTTPException(status_code=401, detail=KEY_NEEDED)
    return SecretStr(raw)


def require_session(request: Request, settings: Settings) -> Session:
    """The signed-in GitHub user (T-026), or 401 `signin_required`. Stores the user's id on
    `request.state.github_id`, where `ratelimit.charge` adds per-user limits and `run_owner`
    binds runs. Called by `visitor_key` and `POST /api/live/check`."""
    session = read_session(request, settings)
    if session is None:
        raise HTTPException(status_code=401, detail=SIGNIN_NEEDED)
    request.state.github_id = session.github_id
    return session


VisitorKey = Annotated[SecretStr | None, Depends(visitor_key)]


def require_model_routes(key: VisitorKey) -> None:
    """Router-level guard on every route that calls a model (chat, jobs, career, runs, assist,
    profile): local passes, live needs a well-formed key, demo is refused (`visitor_key`).
    FastAPI resolves it before the route's other dependencies, so a refused request builds no
    model and touches no retrieval; `visitor_key` is cached per request, so it runs once."""


def run_owner(request: Request, key: VisitorKey) -> str | None:
    """A tag tying a background run to the GitHub user and key that started it (HMAC-SHA256 with
    a per-process secret; the key itself is not kept). None in local mode, where runs are not
    bound. Used by `api/runs.py` and `api/assist.py` (guide 02: an unguessable id alone isn't
    access control). `visitor_key` has already set `request.state.github_id` in live mode."""
    if key is None:
        return None
    github_id = getattr(request.state, "github_id", None)
    message = f"{github_id}|{key.get_secret_value()}".encode()
    return hmac.new(_RUN_SECRET, message, hashlib.sha256).hexdigest()


def get_retrieval(request: Request) -> RetrievalService:
    """The retrieval service opened once at startup (see `main.lifespan`)."""
    return request.app.state.retrieval


def get_demo_library(request: Request) -> DemoLibrary:
    """The recordings loaded once at startup (see `main.lifespan`)."""
    return request.app.state.demo


def get_answer_model(key: VisitorKey) -> BaseChatModel:
    """The "smart" tier model (Sonnet by default), on the visitor's key in live mode."""
    return get_chat_model("smart", api_key=key)


def get_extraction_model(key: VisitorKey) -> BaseChatModel:
    """The "fast" tier model (Haiku by default), on the visitor's key in live mode."""
    return get_chat_model("fast", api_key=key)

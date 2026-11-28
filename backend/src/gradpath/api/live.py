"""`POST /api/live/check`: try the visitor's key once before live mode is switched on (T-018 step
9; behind GitHub sign-in since T-026, always-hard area).

The visitor must be signed in with GitHub (`deps.require_session`), the key's shape is checked,
and the key is tried once against Anthropic's model list, a call that costs nothing. Nothing is
issued: the session cookie already proves the sign-in, and the key itself is not kept anywhere
(the browser holds it in memory and sends it with each request).
"""

import logging

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, SecretStr

from gradpath.api import deps
from gradpath.api.ratelimit import limit
from gradpath.config import Settings, get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/live", tags=["live"])

LIVE_OFF = "Live mode is off on this server."


class LiveCheck(BaseModel):
    """A successful check: the key works and live mode can be switched on."""

    ok: bool = True


def verify_key(key: SecretStr) -> None:
    """One free Anthropic call (list one model) with the visitor's key: raises the SDK's errors
    for a refused key or a limit. No retries; short timeout. Tests replace this function."""
    client = anthropic.Anthropic(api_key=key.get_secret_value(), max_retries=0, timeout=10.0)
    try:
        client.models.list(limit=1)
    finally:
        client.close()


def live_mode(settings: Settings) -> None:
    """Only live mode has a check: demo answers as the model routes do (403), local 404."""
    if settings.app_mode == "demo":
        raise HTTPException(status_code=403, detail=deps.MODEL_ROUTES_OFF)
    if settings.app_mode != "live":
        raise HTTPException(status_code=404, detail=LIVE_OFF)


def signed_in(request: Request) -> None:
    """Live mode and a GitHub session, before `limit("model")` counts anything: an anonymous
    caller must not spend a shared network's model limit (T-026 review), and the session's user
    gets the per-user limit too. FastAPI runs a route's dependencies in list order."""
    settings = get_settings()
    live_mode(settings)
    deps.require_session(request, settings)


@router.post(
    "/check",
    response_model=LiveCheck,
    dependencies=[Depends(signed_in), Depends(limit("model"))],
)
def check(request: Request) -> LiveCheck:
    """Key shape, then one free Anthropic call (`signed_in` already checked mode and session).
    Anthropic's refusals map to the same fixed answers as on the model routes (api/main.py)."""
    raw = request.headers.get(deps.KEY_HEADER, "").strip()
    if not deps.KEY_SHAPE.fullmatch(raw):
        raise HTTPException(status_code=401, detail=deps.KEY_NEEDED)
    verify_key(SecretStr(raw))  # AuthenticationError etc. -> 401/429/502 in api/main.py
    log.info("live check passed")  # no key, login or id
    return LiveCheck()

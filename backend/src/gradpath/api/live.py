"""`POST /api/live/check`: check the passcode and the visitor's key once, get a session token (T-018
step 9, owner decisions 11 and 12; always-hard area).

The passcode is checked (wrong guesses count towards the per-IP lock), the key's shape is checked,
and the key is tried once against Anthropic's model list, a call that costs nothing. On success the
response carries a signed token that stands in for the passcode for TOKEN_TTL_S; the browser keeps
only the token (sessionStorage), never the passcode. The key itself is not kept anywhere: the
browser holds it in memory and sends it with each request.
"""

import hashlib
import hmac
import logging
import re
import secrets
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, SecretStr

from gradpath.api import deps
from gradpath.api.ratelimit import limit
from gradpath.config import Settings, get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/live", tags=["live"])

TOKEN_HEADER = "X-GradPath-Token"
TOKEN_TTL_S = 12 * 3600
LIVE_OFF = "Live mode is off on this server."
# Per-process secret: a restart invalidates every token (as it forgets every run).
_TOKEN_SECRET = secrets.token_bytes(32)


class LiveCheck(BaseModel):
    """What a successful check returns: the session token and when it expires (UTC)."""

    token: str
    expires_at: datetime


TOKEN_SHAPE = re.compile(r"([0-9]{1,12})\.([0-9a-f]{64})")  # ASCII only, checked first


def _signature(expires: int, passcode: str, key: str) -> str:
    """HMAC over the expiry, the current passcode and a hash of the visitor's key: changing
    LIVE_PASSCODE invalidates every token, a token can't be stretched past its expiry, and a
    stolen token is useless without the same key (which only lives in the visitor's tab)."""
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    message = f"{expires}|{passcode}|{key_hash}".encode()
    return hmac.new(_TOKEN_SECRET, message, hashlib.sha256).hexdigest()


def issue_token(passcode: str, key: str, now: Callable[[], float] = time.time) -> tuple[str, int]:
    """A new token for a correct passcode and a key Anthropic accepted: "<expiry>.<signature>"."""
    expires = int(now()) + TOKEN_TTL_S
    return f"{expires}.{_signature(expires, passcode, key)}", expires


TokenStatus = Literal["valid", "expired", "invalid"]


def token_status(
    token: str, passcode: str, key: str, now: Callable[[], float] = time.time
) -> TokenStatus:
    """ "valid", "expired" (genuinely signed but past its time: not counted as a guess), or
    "invalid" (malformed, forged, for another passcode or key, or claiming too long a life).
    Called by `deps.check_passcode`; the shape check rejects non-ASCII before any parsing, and
    the signature compare is constant-time."""
    match = TOKEN_SHAPE.fullmatch(token.strip())
    if match is None:
        return "invalid"
    expires = int(match.group(1))
    if expires > now() + TOKEN_TTL_S + 60:
        return "invalid"
    if not hmac.compare_digest(match.group(2), _signature(expires, passcode, key)):
        return "invalid"
    return "valid" if expires > now() else "expired"


def token_valid(token: str, passcode: str, key: str, now: Callable[[], float] = time.time) -> bool:
    """Shorthand for `token_status(...) == "valid"`."""
    return token_status(token, passcode, key, now) == "valid"


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


@router.post("/check", response_model=LiveCheck, dependencies=[Depends(limit("model"))])
def check(request: Request) -> LiveCheck:
    """Passcode (header, counted towards the lock), then key shape, then one free Anthropic call.
    Anthropic's refusals map to the same fixed answers as on the model routes (api/main.py)."""
    settings = get_settings()
    live_mode(settings)
    deps.check_passcode(request, settings, allow_token=False)
    raw = request.headers.get(deps.KEY_HEADER, "").strip()
    if not deps.KEY_SHAPE.fullmatch(raw):
        raise HTTPException(status_code=401, detail=deps.KEY_NEEDED)
    verify_key(SecretStr(raw))  # AuthenticationError etc. -> 401/429/502 in api/main.py
    if settings.live_passcode is None:  # check_live_settings guarantees one in live mode
        raise HTTPException(status_code=404, detail=LIVE_OFF)
    token, expires = issue_token(settings.live_passcode.get_secret_value().strip(), raw)
    log.info("live check passed")  # no key, passcode or token
    return LiveCheck(token=token, expires_at=datetime.fromtimestamp(expires, UTC))

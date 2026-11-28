"""Temporary measuring page for the proxy chain (T-020 step 4; always-hard: proxy trust).

`GET /api/debug/forwarded` shows the caller how their own request reached the API: the
X-Forwarded-For entries, the connection address, the request header *names*, whether the site's
shared secret matched, and which address each TRUSTED_PROXY_HOPS value would pick. The owner
switches it on with DEBUG_FORWARDED=true for a few minutes to measure the deployed chain; off, it
is a plain 404. It never returns a header value other than the caller's own addresses, so the
shared secret and cookies never appear in it.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from gradpath.api.ratelimit import CLIENT_IP_HEADER, client_ip, client_key, from_site
from gradpath.config import get_settings

router = APIRouter()

MAX_ENTRIES = 10
MAX_CHARS = 64


def _short(value: str) -> str:
    return value.strip()[:MAX_CHARS]


@router.get("/api/debug/forwarded", include_in_schema=False)
def forwarded(request: Request) -> JSONResponse:
    """The caller's own forwarding chain, for measuring the deployed proxies. 404 unless
    DEBUG_FORWARDED; never cached. Reuses `client_ip` and `from_site` so it shows exactly what the
    rate limits would use."""
    settings = get_settings()
    if not settings.debug_forwarded:
        raise HTTPException(status_code=404, detail="Not Found")
    lines = request.headers.getlist("x-forwarded-for")
    chain = [p.strip() for p in ",".join(lines).split(",") if p.strip()]
    plain = settings.model_copy(update={"proxy_shared_secret": None})
    picks = {
        str(n): client_ip(request, plain.model_copy(update={"trusted_proxy_hops": n}))
        for n in range(4)
    }
    site_ip = request.headers.getlist(CLIENT_IP_HEADER)
    body = {
        "connection_host": _short(request.client.host) if request.client else None,
        "x_forwarded_for": [_short(p) for p in chain[-MAX_ENTRIES:]],
        "header_names": sorted({name.lower()[:MAX_CHARS] for name in request.headers})[:50],
        "proxy_secret_matches": from_site(request, settings),
        "client_ip_header": [client_key(v) or "not an address" for v in site_ip[:2]],
        "picked_by_hops": picks,
        "trusted_proxy_hops": settings.trusted_proxy_hops,
        "rate_limit_key": client_ip(request, settings),
    }
    return JSONResponse(body, headers={"Cache-Control": "no-store"})

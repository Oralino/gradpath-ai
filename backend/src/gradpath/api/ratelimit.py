"""Per-IP rate limits and the live-mode passcode's brute-force lock (T-018 step 7, always-hard).

Each limited route names a bucket (search, model, workflow, poll); a bucket has per-IP sliding
windows and may have a site-wide cap (`GLOBAL`). The owner's Voyage tokens are protected across
IPs by the persistent embedding budget instead (`retrieval/budget.py`, T-020 step 2), which
survives restarts. Limits are off in local mode (the owner's machine). Everything is in memory,
per process (deploy with one worker), and bounded: at most MAX_TRACKED clients, oldest dropped.
Own code, no dependency: a few dozen lines with a fake clock for tests (CLAUDE.md: own code for
limits). Over a limit the route answers 429 with a fixed message and `Retry-After`.
"""

import ipaddress
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request

from gradpath.config import Settings, get_settings

# "Your network": limits are per IP, and one IP can be a whole household, office or campus.
LIMITED = (
    "Too many requests from your network (this can include other people on the same Wi-Fi). "
    "Try again later."
)
LOCKED = (
    "Too many wrong passcodes from your network (this can include other people on the same "
    "Wi-Fi). Try again in 15 minutes."
)
MAX_TRACKED = 10_000
MINUTE, HOUR, DAY = 60.0, 3600.0, 86_400.0


@dataclass(frozen=True)
class Window:
    """At most `count` events per `seconds`."""

    count: int
    seconds: float


# Owner can tune these; T-018 step 7 proposal (2026-11-20).
PER_IP: dict[str, tuple[Window, ...]] = {
    # Voyage allows 3 requests a minute in total; 2 per IP leaves room for someone else.
    "search": (Window(2, MINUTE), Window(60, DAY)),
    "model": (Window(6, MINUTE), Window(60, DAY)),
    "workflow": (Window(3, HOUR), Window(10, DAY)),
    "poll": (Window(60, MINUTE),),
}
# Site-wide caps kept in memory. Search's daily cap moved to `retrieval/budget.py` (T-020 step 2):
# stored in Qdrant, so a restart doesn't reset it, and it counts every server-paid embedding.
GLOBAL: dict[str, tuple[Window, ...]] = {}
PASSCODE_FAILURES = Window(5, 15 * MINUTE)


class Limiter:
    """Sliding-window counters keyed by (bucket, client). Thread-safe; `clock` is injectable."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        # Per-client windows, least recently used first (evicted past MAX_TRACKED); global
        # counters (client "*") live apart so a flood of clients can never evict them.
        self._events: OrderedDict[tuple[str, str], deque[float]] = OrderedDict()
        self._global: dict[tuple[str, str], deque[float]] = {}

    def _trimmed(
        self, key: tuple[str, str], horizon: float, now: float, *, create: bool
    ) -> deque[float]:
        """The key's events inside `horizon`. Only `hit` creates an entry, so merely checking an
        address (`wait_time`) can't grow or churn the table."""
        store = self._global if key[1] == "*" else self._events
        events = store.get(key)
        if events is None:
            events = deque()
            if not create:
                return events
            store[key] = events
            if store is self._events:
                while len(self._events) > MAX_TRACKED:  # bounded: drop the least recent client
                    self._events.popitem(last=False)
        elif store is self._events:
            self._events.move_to_end(key)
        while events and events[0] <= now - horizon:
            events.popleft()
        return events

    def wait_time(self, key: tuple[str, str], windows: tuple[Window, ...]) -> float:
        """Seconds until one more event fits every window (0 if it fits now). Records nothing."""
        with self._lock:
            now = self._clock()
            events = self._trimmed(key, max(w.seconds for w in windows), now, create=False)
            return self._wait(events, windows, now)

    def hit(self, key: tuple[str, str], windows: tuple[Window, ...]) -> float:
        """Record one event if it fits every window and return 0; else record nothing and return
        the seconds to wait. Check and record happen under one lock."""
        with self._lock:
            now = self._clock()
            events = self._trimmed(key, max(w.seconds for w in windows), now, create=True)
            wait = self._wait(events, windows, now)
            if wait == 0:
                events.append(now)
            return wait

    @staticmethod
    def _wait(events: deque[float], windows: tuple[Window, ...], now: float) -> float:
        wait = 0.0
        for w in windows:
            recent = [t for t in events if t > now - w.seconds]
            if len(recent) >= w.count:
                wait = max(wait, recent[len(recent) - w.count] + w.seconds - now)
        return wait

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._global.clear()


LIMITER = Limiter()


def client_ip(request: Request, settings: Settings) -> str:
    """The caller, as a rate-limit key. With TRUSTED_PROXY_HOPS = n > 0 (behind n proxies that
    each append to X-Forwarded-For), the n-th entry from the right: entries further left are
    client-written and could be forged. Falls back to the connection address. Normalised by
    `client_key`, so one IPv6 network can't pose as many clients."""
    hops = settings.trusted_proxy_hops
    if hops > 0:
        lines = request.headers.getlist("x-forwarded-for")
        parts = [p.strip() for p in ",".join(lines).split(",")]
        parts = [p for p in parts if p]
        if len(parts) >= hops:
            key = client_key(parts[-hops])
            if key is not None:
                return key
    host = request.client.host if request.client else ""
    return client_key(host) or "unknown"


def client_key(address: str) -> str | None:
    """An address as a rate-limit key: IPv4 as is (an IPv4-mapped IPv6 address as its IPv4), any
    other IPv6 address as its /64 network (one home or server usually owns a whole /64), a port
    suffix dropped. None if it isn't an IP address."""
    text = address.strip()[:64]
    if text.startswith("[") and "]" in text:  # [v6]:port
        text = text[1 : text.index("]")]
    elif text.count(":") == 1:  # v4:port
        text = text.split(":", 1)[0]
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


def _too_many(wait: float, detail: str = LIMITED) -> HTTPException:
    return HTTPException(
        status_code=429, detail=detail, headers={"Retry-After": str(max(1, int(wait + 0.999)))}
    )


def charge(bucket: str, request: Request) -> None:
    """Count this request against `bucket` for the caller's IP (and the bucket's global cap), or
    raise 429. Off in local mode. Used by `limit` and by `/api/assist` when it starts a run."""
    settings = get_settings()
    if settings.app_mode == "local":
        return
    if bucket in GLOBAL:
        wait = LIMITER.wait_time((bucket, "*"), GLOBAL[bucket])
        if wait:
            raise _too_many(wait)
    wait = LIMITER.hit((bucket, client_ip(request, settings)), PER_IP[bucket])
    if wait:
        raise _too_many(wait)
    if bucket in GLOBAL:
        LIMITER.hit((bucket, "*"), GLOBAL[bucket])


def ensure_room(bucket: str, request: Request) -> None:
    """429 if this caller has no room left in `bucket`, without counting anything: lets
    `/api/assist` refuse a run before spending its routing call."""
    settings = get_settings()
    if settings.app_mode == "local":
        return
    wait = LIMITER.wait_time((bucket, client_ip(request, settings)), PER_IP[bucket])
    if wait:
        raise _too_many(wait)


def limit(bucket: str) -> Callable[[Request], None]:
    """A route dependency for `charge(bucket)` (route-level, so it runs after the router's mode,
    passcode and key guard)."""

    def dependency(request: Request) -> None:
        charge(bucket, request)

    dependency.__name__ = f"limit_{bucket}"
    return dependency


def check_passcode_lock(request: Request, settings: Settings) -> None:
    """429 if this IP has failed the passcode too often lately (called before checking it)."""
    wait = LIMITER.wait_time(("passcode", client_ip(request, settings)), (PASSCODE_FAILURES,))
    if wait:
        raise _too_many(wait, LOCKED)


def record_passcode_failure(request: Request, settings: Settings) -> None:
    LIMITER.hit(("passcode", client_ip(request, settings)), (PASSCODE_FAILURES,))

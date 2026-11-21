"""Concurrency caps for the routes that call models (chat, jobs, career) and for source search
(Voyage only, T-018).

Each request to these routes can start a Claude Code process and spend plan quota (or a visitor's
key), and all of them share Voyage's 3-requests-a-minute free tier. A route that is at its cap
answers 503 at once instead of queueing. Per-IP limits and auth come before deploy (TASKS.md).
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

BUSY = "The server is busy with other requests. Try again in a minute."

CHAT = threading.BoundedSemaphore(2)  # one model call each, under a minute
JOBS = threading.BoundedSemaphore(1)  # two model calls, about a minute
CAREER = threading.BoundedSemaphore(1)  # about five model calls, a few minutes
SEARCH = threading.BoundedSemaphore(2)  # one Voyage request each, no model (T-018)


@contextmanager
def slot(limit: threading.BoundedSemaphore, detail: str = BUSY) -> Iterator[None]:
    """Hold one slot of `limit` for the request, or raise 503 if none is free. Used by the chat,
    jobs and career routes around their model calls."""
    if not limit.acquire(blocking=False):
        raise HTTPException(status_code=503, detail=detail)
    try:
        yield
    finally:
        limit.release()

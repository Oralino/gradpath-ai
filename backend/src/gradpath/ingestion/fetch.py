"""Polite page download with an on-disk cache. Fetched content is untrusted, only stored."""

import hashlib
import json
import logging
import time
import urllib.robotparser
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from gradpath.ingestion.manifest import SourceEntry

log = logging.getLogger(__name__)

USER_AGENT = "GradPathIngest/0.1 (educational project)"
TIMEOUT_S = 30.0
MAX_BYTES = 5 * 1024 * 1024
MIN_HOST_INTERVAL_S = 1.0
LOG_NAME = "fetch_log.json"
MANUAL_SUFFIXES = {".html", ".htm", ".md", ".mdx", ".txt"}


class FetchedPage(BaseModel):
    """A page on disk, ready for cleaning. `kind` is `html` or `md`."""

    index: int
    url: str
    path: Path
    kind: str
    retrieved_at: str


def make_client() -> httpx.Client:
    """Client with our User-Agent, redirects and timeout (ingest.py; tests inject their own)."""
    return httpx.Client(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=TIMEOUT_S
    )


class Politeness:
    """robots.txt cache per host plus a minimum gap between requests to one host.

    Shared across documents by ingest.py so the gap holds across them; `sleep`/`clock` are
    injectable so tests run instantly.
    """

    def __init__(
        self,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        min_interval: float = MIN_HOST_INTERVAL_S,
    ):
        self._sleep = sleep
        self._clock = clock
        self._min_interval = min_interval
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def wait(self, host: str) -> None:
        """Sleep until at least `min_interval` has passed since the last request to `host`."""
        last = self._last.get(host)
        if last is not None:
            gap = self._min_interval - (self._clock() - last)
            if gap > 0:
                self._sleep(gap)
        self._last[host] = self._clock()

    def allowed(self, url: str, client: httpx.Client) -> bool:
        """Check robots.txt for the URL's host (cached); a missing or unreadable one allows."""
        parts = urlparse(url)
        host = parts.netloc
        if host not in self._robots:
            parser: urllib.robotparser.RobotFileParser | None = None
            try:
                self.wait(host)
                resp = client.get(f"{parts.scheme}://{host}/robots.txt")
                if resp.status_code == 200:
                    parser = urllib.robotparser.RobotFileParser()
                    parser.parse(resp.text.splitlines())
            except httpx.HTTPError as exc:
                log.warning("robots.txt fetch failed for %s: %s", host, exc)
            self._robots[host] = parser
        parser = self._robots[host]
        return True if parser is None else parser.can_fetch(USER_AGENT, url)


def _kind_for(url: str) -> str:
    return "md" if urlparse(url).path.lower().endswith((".md", ".mdx")) else "html"


def _download(client: httpx.Client, url: str) -> tuple[int, bytes | None]:
    """GET with a size cap; returns (status, body) where body is None if not 200 or too large."""
    with client.stream("GET", url) as resp:
        if resp.status_code != 200:
            return resp.status_code, None
        body = bytearray()
        for chunk in resp.iter_bytes():
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                log.warning("skip %s: larger than %d bytes", url, MAX_BYTES)
                return resp.status_code, None
        return resp.status_code, bytes(body)


def fetch_source(
    entry: SourceEntry,
    raw_dir: Path,
    client: httpx.Client,
    refresh: bool = False,
    politeness: Politeness | None = None,
) -> list[FetchedPage]:
    """Download each of the entry's URLs into `raw_dir/<document_id>/<index>.<ext>` and log them.

    Called by ingest.py. Cached pages (present in fetch_log.json and on disk) are reused unless
    `refresh`. Disallowed (robots), non-200 and oversized pages are logged and skipped.
    """
    politeness = politeness or Politeness()
    doc_dir = raw_dir / entry.document_id
    log_path = doc_dir / LOG_NAME
    old: dict[str, dict] = {}
    if log_path.exists():
        old = {r["url"]: r for r in json.loads(log_path.read_text(encoding="utf-8"))}
    records: list[dict] = []
    pages: list[FetchedPage] = []
    for index, url in enumerate(entry.fetch_urls):
        kind = _kind_for(url)
        path = doc_dir / f"{index}.{kind}"
        cached = old.get(url)
        if cached and path.exists() and not refresh:
            records.append(cached)
            pages.append(
                FetchedPage(
                    index=index, url=url, path=path, kind=kind, retrieved_at=cached["retrieved_at"]
                )
            )
            continue
        if not politeness.allowed(url, client):
            log.warning("skip %s: disallowed by robots.txt", url)
            continue
        politeness.wait(urlparse(url).netloc)
        try:
            status, body = _download(client, url)
        except httpx.HTTPError as exc:
            log.warning("skip %s: %s", url, exc)
            continue
        if body is None:
            log.warning("skip %s: status %s", url, status)
            continue
        doc_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        retrieved_at = datetime.now(UTC).isoformat(timespec="seconds")
        records.append(
            {
                "url": url,
                "file": path.name,
                "retrieved_at": retrieved_at,
                "status": status,
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        )
        pages.append(
            FetchedPage(index=index, url=url, path=path, kind=kind, retrieved_at=retrieved_at)
        )
    if records:
        doc_dir.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return pages


def load_manual(entry: SourceEntry, manual_dir: Path) -> list[FetchedPage]:
    """Pages from the owner's saved files `manual_dir/<document_id>.*`.

    Empty list (with a warning) if none exist. Pages carry the manifest source_url.
    """
    files = sorted(
        p for p in manual_dir.glob(f"{entry.document_id}.*") if p.suffix.lower() in MANUAL_SUFFIXES
    )
    if not files:
        log.warning("%s: manual document but no file in %s", entry.document_id, manual_dir)
    pages = []
    for i, path in enumerate(files):
        kind = "md" if path.suffix.lower() in {".md", ".mdx", ".txt"} else "html"
        stamp = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(timespec="seconds")
        pages.append(
            FetchedPage(index=i, url=entry.source_url, path=path, kind=kind, retrieved_at=stamp)
        )
    return pages

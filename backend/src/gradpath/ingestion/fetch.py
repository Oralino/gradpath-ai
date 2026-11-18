"""Polite page download with an on-disk cache. Fetched content is untrusted, only stored."""

import hashlib
import ipaddress
import json
import logging
import re
import time
import urllib.robotparser
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

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
MAX_REDIRECTS = 5
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
TEXT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/markdown",
    "text/x-markdown",
    "text/plain",
}


def manifest_hosts(entries: Iterable[SourceEntry]) -> frozenset[str]:
    """Hostnames of the given manifest entries (source and fetch URLs): the only hosts ingestion
    may contact, redirects included (T-007). Built by ingest.run from the approved entries."""
    hosts = set()
    for e in entries:
        for url in [e.source_url, *e.fetch_urls]:
            host = (urlparse(url).hostname or "").lower().rstrip(".")
            if host:
                hosts.add(host)
    return frozenset(hosts)


# Hosts written as numbers (2130706433, 0x7f.1, 0177.0.0.1, 127.1): the resolver may accept them
# as IPv4 addresses although `ipaddress` does not, so they are refused outright.
NUMERIC_HOST = re.compile(r"^(0x[0-9a-f]*|\d+)(\.(0x[0-9a-f]*|\d+))*$")


def url_refusal(url: str, allowed_hosts: frozenset[str] | None) -> str | None:
    """Why ingestion may not request `url`, or None if it may (T-007: SSRF and poisoning).

    Called by Politeness for the first URL, every redirect hop and every robots.txt hop: https
    on the default port, no credentials, no private, loopback or reserved IP literal, no
    localhost, and (when `allowed_hosts` is given, as ingest.run always does) a manifest host.
    """
    # urlparse silently drops tabs and newlines and treats `\` differently from httpx: refuse
    # them, so the checked URL and the requested URL are the same.
    if any(ch.isspace() or ord(ch) < 32 or ch == "\\" for ch in url):
        return "whitespace, control character or backslash in the URL"
    try:
        parts = urlparse(url)
        port = parts.port
    except ValueError:
        return "malformed URL"
    if parts.scheme != "https":
        return f"scheme {parts.scheme or 'missing'} (https only)"
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        return "no host"
    if parts.username is not None or parts.password is not None:
        return "credentials in the URL"
    if port not in (None, 443):
        return f"port {port}"
    if host == "localhost" or host.endswith(".localhost"):
        return "localhost"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        return "private or reserved address"
    if address is None and NUMERIC_HOST.match(host):
        return "numeric host"
    if allowed_hosts is not None and host not in allowed_hosts:
        return f"host {host} is not in the manifest"
    return None


class FetchedPage(BaseModel):
    """A page on disk, ready for cleaning. `kind` is `html` or `md`."""

    index: int
    url: str
    path: Path
    kind: str
    retrieved_at: str


def make_client() -> httpx.Client:
    """Client with our User-Agent and timeout (ingest.py; tests inject their own).

    Redirects are off on purpose: `_download` follows them itself so every hop passes robots.txt.
    """
    return httpx.Client(
        headers={"User-Agent": USER_AGENT}, follow_redirects=False, timeout=TIMEOUT_S
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
        allowed_hosts: frozenset[str] | None = None,
    ):
        self._sleep = sleep
        self.allowed_hosts = allowed_hosts
        self._clock = clock
        self._min_interval = min_interval
        self._last: dict[str, float] = {}
        # parser, or True (allow all) / False (disallow all) when robots.txt has no rules to parse
        self._robots: dict[str, urllib.robotparser.RobotFileParser | bool] = {}

    def refusal(self, url: str) -> str | None:
        """`url_refusal` with this run's manifest hosts."""
        return url_refusal(url, self.allowed_hosts)

    def wait(self, host: str) -> None:
        """Sleep until at least `min_interval` has passed since the last request to `host`."""
        last = self._last.get(host)
        if last is not None:
            gap = self._min_interval - (self._clock() - last)
            if gap > 0:
                self._sleep(gap)
        self._last[host] = self._clock()

    def _get_robots(self, url: str, client: httpx.Client) -> httpx.Response | None:
        """GET robots.txt following up to MAX_REDIRECTS redirects by hand (the client does not);
        None if the chain does not end in a non-redirect response. Called by `allowed`.
        """
        for _ in range(MAX_REDIRECTS + 1):
            resp = client.get(url)
            location = resp.headers.get("location")
            if resp.status_code not in REDIRECT_STATUSES:
                return resp
            if not location:
                return None  # a redirect with nowhere to go: treated as disallow

            url = urljoin(url, location)
            why = self.refusal(url)
            if why:
                log.warning("robots.txt redirect refused (%s)", why)
                return None  # treated as disallow
            self.wait(urlparse(url).netloc)
        return None

    def allowed(self, url: str, client: httpx.Client) -> bool:
        """Check robots.txt for the URL's host (cached per host for the run), per RFC 9309.

        200 -> parse the rules; 4xx (incl. 404) -> allow all; 5xx, an unresolved redirect chain or
        a network error -> disallow all (the site may be hiding rules), so ingest.py skips the URL.
        """
        if self.refusal(url):
            return False  # never contact a refused URL, not even for its robots.txt
        parts = urlparse(url)
        host = parts.netloc
        if host not in self._robots:
            rules: urllib.robotparser.RobotFileParser | bool
            try:
                self.wait(host)
                resp = self._get_robots(f"{parts.scheme}://{host}/robots.txt", client)
                if resp is None:
                    log.warning("robots.txt for %s redirects without resolving; skipping", host)
                    rules = False
                elif resp.status_code == 200:
                    rules = urllib.robotparser.RobotFileParser()
                    rules.parse(resp.text.splitlines())
                else:
                    rules = resp.status_code < 500
                    if not rules:
                        log.warning(
                            "robots.txt for %s returned %s; skipping host", host, resp.status_code
                        )
            except (httpx.HTTPError, httpx.InvalidURL) as exc:
                log.warning("robots.txt fetch failed for %s: %s; skipping host", host, exc)
                rules = False
            self._robots[host] = rules
        rules = self._robots[host]
        if isinstance(rules, bool):
            return rules
        return rules.can_fetch(USER_AGENT, url)


def _kind_for(url: str) -> str:
    return "md" if urlparse(url).path.lower().endswith((".md", ".mdx")) else "html"


def _cache_valid(record: dict, path: Path) -> bool:
    """True if `path` exists and its sha256 equals the logged one (else it is re-downloaded)."""
    return path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == record.get("sha256")


def _download(client: httpx.Client, url: str, politeness: Politeness) -> tuple[int, bytes | None]:
    """GET with a size cap; returns (status, body); body is None when the page is skipped.

    Called by fetch_source. Follows up to MAX_REDIRECTS redirects by hand so each hop is checked
    against robots.txt and spaced per host; the content type is checked before the body is read.
    """
    for _ in range(MAX_REDIRECTS + 1):
        with client.stream("GET", url) as resp:
            location = resp.headers.get("location")
            if resp.status_code in REDIRECT_STATUSES and location:
                next_url = urljoin(url, location)
                why = politeness.refusal(next_url)
                if why:
                    log.warning("skip %s: redirect to %s refused (%s)", url, next_url, why)
                    return resp.status_code, None
                if not politeness.allowed(next_url, client):
                    log.warning("skip %s: redirect to %s disallowed by robots.txt", url, next_url)
                    return resp.status_code, None
                politeness.wait(urlparse(next_url).netloc)
                url = next_url
                continue
            if resp.status_code != 200:
                return resp.status_code, None
            ctype = resp.headers.get("content-type")
            if ctype is not None:
                media = ctype.split(";")[0].strip().lower()
                if media not in TEXT_TYPES:
                    log.warning("skip %s: content type %s", url, ctype)
                    return resp.status_code, None
            body = bytearray()
            for chunk in resp.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    log.warning("skip %s: larger than %d bytes", url, MAX_BYTES)
                    return resp.status_code, None
            return resp.status_code, bytes(body)
    log.warning("skip %s: more than %d redirects", url, MAX_REDIRECTS)
    return 310, None


def fetch_source(
    entry: SourceEntry,
    raw_dir: Path,
    client: httpx.Client,
    refresh: bool = False,
    politeness: Politeness | None = None,
) -> list[FetchedPage]:
    """Download each of the entry's URLs into `raw_dir/<document_id>/<url hash>.<ext>` and log them.

    Called by ingest.py. Files are named by the URL's hash (not its position), so reordering
    `fetch_urls` cannot pair a URL with another page's file; `FetchedPage.index` is still the
    position (chunk ids use it). Cached pages (in fetch_log.json, on disk, sha256 matching) are
    reused unless `refresh`. Disallowed (robots), non-200 and oversized pages are logged, skipped.
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
        path = doc_dir / f"{hashlib.sha256(url.encode()).hexdigest()[:16]}.{kind}"
        cached = old.get(url)
        if cached and not refresh and _cache_valid(cached, path):
            records.append(cached)
            pages.append(
                FetchedPage(
                    index=index, url=url, path=path, kind=kind, retrieved_at=cached["retrieved_at"]
                )
            )
            continue
        why = politeness.refusal(url)
        if why:
            log.warning("skip %s: %s", url, why)
            continue
        if not politeness.allowed(url, client):
            log.warning("skip %s: disallowed by robots.txt", url)
            continue
        politeness.wait(urlparse(url).netloc)
        try:
            status, body = _download(client, url, politeness)
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
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

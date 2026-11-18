"""Local route log (T-006): one JSON line per routed request, for routing and fallback stats.

Written by `POST /api/assist` and the router CLI to `ROUTE_LOG_PATH` (default `logs/routes.jsonl`,
gitignored; empty turns it off). Entries come from `assist.route_log_entry` and hold no request
text. Writing never fails a request: an error is logged by type and the entry is dropped. The
file is capped: past `MAX_BYTES` it is moved to `<name>.1` (one old file kept), so repeated
requests can't fill the disk.
"""

import json
import logging
import threading
from pathlib import Path

from gradpath.config import REPO_ROOT, Settings

log = logging.getLogger(__name__)
_lock = threading.Lock()  # API requests run in worker threads; one writer at a time
MAX_BYTES = 5 * 1024 * 1024  # about 20,000 entries


def log_path(settings: Settings) -> Path | None:
    """The configured log file (relative paths are under the repo root), or None if off."""
    if not settings.route_log_path:
        return None
    path = Path(settings.route_log_path)
    return path if path.is_absolute() else REPO_ROOT / path


def record(path: Path | None, entry: dict, max_bytes: int = MAX_BYTES) -> None:
    """Append `entry` as one JSON line, rotating a full file first; never raises."""
    if path is None:
        return
    try:
        line = json.dumps(entry, ensure_ascii=False)
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.stat().st_size >= max_bytes:
                path.replace(path.with_name(path.name + ".1"))
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception as exc:  # called from a `finally`: it must not replace the real outcome
        log.warning("route log write failed (%s)", type(exc).__name__)

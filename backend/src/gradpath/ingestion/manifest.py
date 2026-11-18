"""Source manifest: parse `knowledge_base/source_manifest.csv` into typed entries."""

import csv
import re
from pathlib import Path

from pydantic import BaseModel, field_validator

MANUAL = "manual"
DOCUMENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class SourceEntry(BaseModel):
    """One manifest row. `fetch_urls` is what to download; `manual` means the owner saves it."""

    document_id: str
    title: str
    source_url: str
    source_type: str = ""
    collection: str = ""
    topic: str = ""
    license_or_usage_notes: str = ""
    license_verified: str = ""
    status: str
    added_by: str = ""
    fetch_urls: list[str] = []
    manual: bool = False

    @field_validator("document_id")
    @classmethod
    def _safe_id(cls, value: str) -> str:
        # The id becomes a folder name (raw_dir / document_id): no slashes, no ".." sequences.
        if not DOCUMENT_ID_RE.match(value) or ".." in value:
            raise ValueError(f"document_id {value!r} must match {DOCUMENT_ID_RE.pattern} (no '..')")
        return value

    @field_validator("fetch_urls", mode="before")
    @classmethod
    def _split_urls(cls, value: object) -> object:
        # The CSV holds a pipe-separated string; the literal `manual` is handled by load_manifest.
        if isinstance(value, str):
            return [u.strip() for u in value.split("|") if u.strip()]
        return value

    @property
    def approved(self) -> bool:
        return self.status.strip().lower() == "approved"


def load_manifest(path: Path) -> list[SourceEntry]:
    """Read the CSV into entries (called by ingest.py); `manual` in fetch_urls sets the flag."""
    entries: list[SourceEntry] = []
    with Path(path).open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row = {k: (v or "").strip() for k, v in row.items() if k}
            manual = row.get("fetch_urls", "").lower() == MANUAL
            if manual:
                row["fetch_urls"] = ""
            entries.append(SourceEntry(**row, manual=manual))
    return entries


def select_ingestible(
    entries: list[SourceEntry], only: list[str] | None = None
) -> list[SourceEntry]:
    """Keep `approved` entries only (link_only and others are never fetched), optionally by id."""
    chosen = [e for e in entries if e.approved]
    if only:
        chosen = [e for e in chosen if e.document_id in set(only)]
    return chosen

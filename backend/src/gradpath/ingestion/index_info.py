"""A small summary of the built index (`knowledge_base/index_info.json`), committed with the repo.

Written by `ingest.py` every time the index is rebuilt; read by the API lifespan in every mode, so
demo mode can say "Sources as of {date}" without opening Qdrant (T-018 step 3, DESIGN.md footer).
"""

import json
import logging
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path

from langchain_core.documents import Document
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

log = logging.getLogger(__name__)


class IndexInfo(BaseModel):
    """`sources_as_of` is the OLDEST page fetch date: "as of" may only claim a freshness every
    source has. `sources_newest` is the most recent fetch; `written_at` is when this file was
    written (an index rebuild, or `ingest --info-only`)."""

    model_config = ConfigDict(extra="forbid")

    written_at: date
    sources_as_of: date
    sources_newest: date
    documents: int
    chunks: int

    @model_validator(mode="after")
    def _ordered(self) -> "IndexInfo":
        if self.sources_as_of > self.sources_newest:
            raise ValueError("sources_as_of is after sources_newest")
        return self


def summarize(
    chunks: Iterable[Document],
    written_at: date | None = None,
    *,
    undated: Iterable[str] = (),
) -> IndexInfo:
    """Dates and counts from the chunks that went into the index (their `retrieved_at` metadata,
    an ISO timestamp set by `fetch.py`). Documents in `undated` (owner-saved manual sources) are
    counted but don't set the dates. Raises if no chunk carries a date."""
    skip = set(undated)
    dates: list[date] = []
    documents: set[str] = set()
    count = 0
    for chunk in chunks:
        count += 1
        documents.add(chunk.metadata.get("document_id", ""))
        stamp = chunk.metadata.get("retrieved_at")
        if stamp and chunk.metadata.get("document_id") not in skip:
            moment = datetime.fromisoformat(stamp)
            if moment.tzinfo is None:  # fetch.py writes UTC; treat a bare stamp as UTC too
                moment = moment.replace(tzinfo=UTC)
            dates.append(moment.astimezone(UTC).date())
    if not dates:
        raise ValueError("no chunk has a retrieved_at date")
    return IndexInfo(
        written_at=written_at or datetime.now(UTC).date(),
        sources_as_of=min(dates),
        sources_newest=max(dates),
        documents=len(documents - {""}),
        chunks=count,
    )


def write_index_info(path: Path, info: IndexInfo) -> None:
    """Write the summary as JSON (temp file, then rename, so a reader never sees half a file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(info.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def read_index_info(path: Path) -> IndexInfo | None:
    """The summary, or None (logged) if the file is missing or invalid: the footer then just
    leaves the date out. Called by the API lifespan."""
    try:
        return IndexInfo.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        log.warning("index info not found; the sources date is unavailable")
    except (OSError, ValueError, ValidationError) as exc:
        log.error("index info unreadable (%s); the sources date is unavailable", type(exc).__name__)
    return None

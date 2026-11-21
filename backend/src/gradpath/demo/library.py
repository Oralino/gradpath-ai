"""Recorded runs for demo mode: their schema, and the library the API serves them from.

A recording is one JSON file in `demo_runs/` holding the inputs (sample posting, sample profile,
question) and the exact response the API returned when it was recorded. Each file is validated
against the same Pydantic models the live routes return, so a recording that drifts from the API
is skipped (and a test fails) instead of reaching the browser. Lookups go by id through a dict,
never by building a file path from client input.
"""

import logging
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from gradpath.jobs import JobAnalysis
from gradpath.router.assist import AssistResponse
from gradpath.workflows import CareerPrepResult, UserProfile
from gradpath.workflows.schemas import MAX_JOB_DESCRIPTION_CHARS, Correction

log = logging.getLogger(__name__)

# Our own files, but a size cap keeps a mistake (a huge or wrong file) from loading into memory.
MAX_RECORDING_BYTES = 2_000_000

DemoId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]
JobDescription = Annotated[
    str, StringConstraints(min_length=50, max_length=MAX_JOB_DESCRIPTION_CHARS)
]


class _RecordingBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: DemoId
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=400)
    recorded_at: date


class AskRecording(_RecordingBase):
    """One Ask-screen request (`POST /api/assist`) and its response."""

    kind: Literal["ask"]
    message: str = Field(min_length=3, max_length=2000)
    job_description: JobDescription | None = None
    profile: UserProfile | None = None
    response: AssistResponse

    @model_validator(mode="after")
    def _finished(self) -> "AskRecording":
        """A "started" response only carries a run id, which means nothing once replayed."""
        if self.response.outcome == "started" or self.response.run_id is not None:
            raise ValueError("an ask recording must hold a finished response, not a run id")
        return self


class JobRecording(_RecordingBase):
    """One Job-screen analysis (`POST /api/jobs/analyze`)."""

    kind: Literal["job"]
    job_description: JobDescription
    analysis: JobAnalysis


class PlanRecording(_RecordingBase):
    """One finished preparation run (`POST /api/career/runs`, then polled to the end)."""

    kind: Literal["plan"]
    job_description: JobDescription
    profile: UserProfile
    corrections: list[Correction] = Field(default_factory=list, max_length=10)
    result: CareerPrepResult


DemoRecording = Annotated[AskRecording | JobRecording | PlanRecording, Field(discriminator="kind")]
RECORDING = TypeAdapter(DemoRecording)


class DemoSummary(BaseModel):
    """What `GET /api/demo` lists: enough to show a picker, without the recorded content."""

    id: str
    kind: Literal["ask", "job", "plan"]
    title: str
    summary: str
    recorded_at: date


class DemoLibrary:
    """The validated recordings, keyed by id. Built once per process by the API lifespan."""

    def __init__(self, recordings: list[AskRecording | JobRecording | PlanRecording]) -> None:
        self._by_id = {r.id: r for r in recordings}
        if len(self._by_id) != len(recordings):
            raise ValueError("duplicate demo recording ids")

    def __len__(self) -> int:
        return len(self._by_id)

    def summaries(self) -> list[DemoSummary]:
        order = {"ask": 0, "job": 1, "plan": 2}
        items = sorted(self._by_id.values(), key=lambda r: (order[r.kind], r.title, r.id))
        return [
            DemoSummary(
                id=r.id, kind=r.kind, title=r.title, summary=r.summary, recorded_at=r.recorded_at
            )
            for r in items
        ]

    def get(self, recording_id: str) -> AskRecording | JobRecording | PlanRecording | None:
        return self._by_id.get(recording_id)


def load_library(folder: Path) -> DemoLibrary:
    """Read every `*.json` in `folder` (not subfolders) into a library; called by the API lifespan.

    A file that is a link, unreadable, too big, invalid, or reuses an id is skipped and logged by
    file name and error count only (validation messages can quote the file's content).
    """
    if not folder.is_dir():
        log.warning("demo recordings folder not found; demo mode has no recordings")
        return DemoLibrary([])
    recordings: list[AskRecording | JobRecording | PlanRecording] = []
    seen: set[str] = set()
    for path in sorted(folder.glob("*.json")):
        # A link could point outside the folder (say at `.env`); recordings are plain files only.
        if path.is_symlink() or not path.is_file():
            log.error("demo recording %s skipped (not a plain file)", path.name)
            continue
        try:
            if path.stat().st_size > MAX_RECORDING_BYTES:
                log.error(
                    "demo recording %s skipped (larger than %d bytes)",
                    path.name,
                    MAX_RECORDING_BYTES,
                )
                continue
            data = path.read_bytes()
        except OSError as exc:
            # One unreadable file must not stop demo mode from starting.
            log.error("demo recording %s skipped (%s)", path.name, type(exc).__name__)
            continue
        try:
            recording = RECORDING.validate_json(data)
        except ValidationError as exc:
            log.error("demo recording %s skipped (%d errors)", path.name, exc.error_count())
            continue
        if recording.id in seen:
            log.error("demo recording %s skipped (duplicate id)", path.name)
            continue
        seen.add(recording.id)
        recordings.append(recording)
    log.info("demo recordings loaded: %d", len(recordings))
    return DemoLibrary(recordings)

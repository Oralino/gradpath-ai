"""`GET /api/demo` and `GET /api/demo/{recording_id}`: recorded runs for demo mode (T-018).

Read-only and open in every mode: they serve files from `demo_runs/` that the lifespan loaded at
startup, so they make no model or embedding calls and need no keys.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from gradpath.api.deps import get_demo_library
from gradpath.demo import DemoLibrary, DemoRecording, DemoSummary

router = APIRouter(prefix="/api/demo", tags=["demo"])

NOT_FOUND = "This recorded example was not found."


@router.get("", response_model=list[DemoSummary])
def list_recordings(
    library: Annotated[DemoLibrary, Depends(get_demo_library)],
) -> list[DemoSummary]:
    """The recorded examples, Ask first, then Job, then Plan."""
    return library.summaries()


@router.get("/{recording_id}", response_model=DemoRecording)
def get_recording(
    recording_id: str, library: Annotated[DemoLibrary, Depends(get_demo_library)]
) -> DemoRecording:
    """One recording with its inputs and recorded response; 404 for any unknown id."""
    recording = library.get(recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return recording

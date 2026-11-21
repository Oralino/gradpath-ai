"""`POST /api/profile/from-resume`: pasted resume text in, a draft profile out (T-014).

Nothing is stored: the draft goes back to the browser, where the visitor reviews and saves it. The
resume text is not traced or logged (see `profiles/resume.py`).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, ConfigDict, StringConstraints

from gradpath.api import limits
from gradpath.api.deps import get_extraction_model, require_model_routes
from gradpath.api.ratelimit import limit
from gradpath.profiles import MAX_RESUME_CHARS, MIN_RESUME_CHARS, ResumeImport, import_resume

router = APIRouter(
    prefix="/api/profile", tags=["profile"], dependencies=[Depends(require_model_routes)]
)


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown fields are a 422, not silently dropped
    # Stripped first, so 100 spaces can't spend a model call.
    resume_text: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=MIN_RESUME_CHARS, max_length=MAX_RESUME_CHARS
        ),
    ]


@router.post("/from-resume", response_model=ResumeImport, dependencies=[Depends(limit("model"))])
def from_resume(
    body: ResumeRequest,
    fast: Annotated[BaseChatModel, Depends(get_extraction_model)],
) -> ResumeImport:
    """One fast-tier model call under the chat cap (`limits.CHAT`)."""
    with limits.slot(limits.CHAT):
        return import_resume(body.resume_text, fast)

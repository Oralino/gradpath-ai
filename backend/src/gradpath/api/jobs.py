"""`POST /api/jobs/analyze`: requirements, evidence and cited study notes for a job description."""

from typing import Annotated

from fastapi import APIRouter, Depends
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, ConfigDict, Field

from gradpath.api import limits
from gradpath.api.deps import (
    get_answer_model,
    get_extraction_model,
    get_retrieval,
    require_model_routes,
)
from gradpath.jobs import JobAnalysis, analyze_job
from gradpath.retrieval import RetrievalService

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(require_model_routes)])


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown fields are a 422, not silently dropped
    job_description: str = Field(min_length=50, max_length=20_000)


@router.post("/analyze", response_model=JobAnalysis)
def analyze(
    body: AnalyzeRequest,
    retrieval: Annotated[RetrievalService, Depends(get_retrieval)],
    fast: Annotated[BaseChatModel, Depends(get_extraction_model)],
    smart: Annotated[BaseChatModel, Depends(get_answer_model)],
) -> JobAnalysis:
    """Synchronous for now (two model calls, roughly a minute on Claude Code); Milestone 3's
    end-to-end workflow returns a job id and status instead. One at a time (`limits`)."""
    with limits.slot(limits.JOBS):
        return analyze_job(body.job_description, retrieval, fast, smart)

"""The workflow's shared state (`CareerPrepState`) and its runtime context (`WorkflowContext`).

`graph.py` builds the LangGraph `StateGraph` over this state; every node reads it and returns only
the keys it changed. Services (retrieval, models) live in the context, not the state, so the state
stays plain data that can be logged, traced and asserted on in tests.
"""

import operator
from dataclasses import dataclass
from typing import Annotated, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel

from gradpath.retrieval import RetrievalService
from gradpath.workflows.schemas import (
    CareerPrepResult,
    Critique,
    GapItem,
    InterviewQuestion,
    JobSummary,
    ProfileEvidence,
    RequirementEvidence,
    RoadmapItem,
    UserProfile,
)


class CareerPrepState(TypedDict, total=False):
    """Keys grouped by who writes them. `errors` and `node_log` have a list reducer
    (`operator.add`) because parallel nodes may write them in the same step; without one,
    LangGraph refuses two writes to the same key in one step."""

    # input (set by run_workflow; max_revisions comes from settings, never from the request)
    job_description: str
    profile: UserProfile
    corrections: list[str]
    max_revisions: int

    # node outputs
    job: JobSummary  # analyze_job
    profile_evidence: list[ProfileEvidence]  # analyze_profile
    knowledge: list[RequirementEvidence]  # retrieve_knowledge
    gaps: list[GapItem]  # analyze_gaps
    roadmap: list[RoadmapItem]  # plan_roadmap, revise
    interview_questions: list[InterviewQuestion]  # interview_questions
    critique: Critique  # evaluate
    revision_count: int  # incremented by graph code around revise, not by the node itself
    result: CareerPrepResult  # finalize

    # bookkeeping
    errors: Annotated[list[str], operator.add]
    node_log: Annotated[list[str], operator.add]


@dataclass(frozen=True)
class WorkflowContext:
    """Services the nodes call, passed as LangGraph runtime context (`invoke(..., context=...)`).
    Optional so the skeleton and graph-shape tests can run without any of them."""

    retrieval: RetrievalService | None = None
    fast_llm: BaseChatModel | None = None
    smart_llm: BaseChatModel | None = None

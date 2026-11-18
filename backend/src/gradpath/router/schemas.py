"""Router input and output models (T-006).

The router never sees the job description or profile text, only whether each was attached: the
routing call stays small, and attached text has no way to steer it.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

Kind = Literal[
    "knowledge_question",  # a focused question one retrieval cycle can answer
    "job_preparation",  # gaps, roadmap or interview prep for one job and this user's profile
    "job_comparison",  # comparing several jobs (not supported yet)
    "progress_tracking",  # updating an earlier plan from progress (not supported yet)
    "resume_rewrite",  # rewriting or tailoring a resume (not supported yet)
    "other",  # none of the above
]
Route = Literal["traditional_rag", "agentic_workflow"]
Action = Literal["run", "needs_input", "unsupported"]
InputName = Literal["job_description", "profile"]
DecidedBy = Literal["rules", "model", "default"]

MAX_REASON_CHARS = 200


def _truncate_reason(value: object) -> object:
    """Cut an over-long model reason instead of failing the whole classification."""
    if isinstance(value, str) and len(value) > MAX_REASON_CHARS:
        return value[: MAX_REASON_CHARS - 1] + "…"
    return value


Reason = Annotated[str, BeforeValidator(_truncate_reason)]


class RouteRequest(BaseModel):
    """What the router decides on: the message and which inputs came with it."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=3, max_length=2000)
    has_job_description: bool = False
    has_profile: bool = False


class Classification(BaseModel):
    """The only thing the model answers: what kind of request this is. Code picks the route."""

    kind: Kind
    reason: Reason = Field(min_length=1, description="One short sentence on why this kind fits.")


class RouteDecision(BaseModel):
    """The recorded routing decision. Everything but `kind` and `reason` is filled in by code
    (`route.decide`), so a model reply can't contradict the route table. `reason` may be model
    text: clients render it as plain text only, and it never goes into a later prompt."""

    route: Route
    action: Action
    kind: Kind
    missing: list[InputName]
    reason: Reason
    requires_user_profile: bool
    requires_multi_step_workflow: bool
    decided_by: DecidedBy

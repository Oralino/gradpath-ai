"""Pydantic models for the career-preparation workflow (T-003): its input, what each node writes
into the state, and the final result.

Used by `workflows/state.py` (the typed LangGraph state), the nodes, and later the
`POST /api/career/prepare` route. Every node output is one of these models, so a malformed model
reply fails at the node that produced it instead of several nodes later.
"""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from gradpath.jobs.analyze import ExtractedRequirement, Seniority
from gradpath.rag.answer import Citation
from gradpath.retrieval import Evidence

# Profile, job description and corrections are untrusted user input: bound every string and list,
# and the profile's total size, so one request can't push a huge prompt through the workflow
# (free-tier Voyage and plan limits). Optional fields: the client omits them rather than sending "".
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)]
MAX_PROFILE_CHARS = 12_000  # about 3K tokens; the sample profile is ~1.6K characters
MAX_JOB_DESCRIPTION_CHARS = 20_000  # same cap as POST /api/jobs/analyze
MAX_MODEL_TEXT_CHARS = 1000


def _truncate(value: object) -> object:
    """Cut over-long model text instead of rejecting it: a long but valid reply shouldn't cost a
    retry. Strings only; anything else is left for normal validation."""
    if isinstance(value, str) and len(value) > MAX_MODEL_TEXT_CHARS:
        return value[: MAX_MODEL_TEXT_CHARS - 1] + "…"
    return value


# Text written by a model and returned to the client: bounded so a runaway reply can't bloat
# the response. The client must render it as text, never as HTML.
ModelText = Annotated[str, BeforeValidator(_truncate)]


# ---------- input ----------


class ProjectEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ShortText
    description: LongText
    technologies: list[ShortText] = Field(default_factory=list, max_length=15)


class ExperienceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ShortText
    organisation: ShortText | None = None
    description: LongText


class UserProfile(BaseModel):
    """The structured profile form (owner decision 2026-11-18: a form, not resume extraction)."""

    model_config = ConfigDict(extra="forbid")

    profile_id: ShortText | None = None
    note: LongText | None = None
    name: ShortText | None = None
    education: ShortText | None = None
    skills: list[ShortText] = Field(default_factory=list, max_length=50)
    coursework: list[ShortText] = Field(default_factory=list, max_length=30)
    projects: list[ProjectEntry] = Field(default_factory=list, max_length=6)
    experience: list[ExperienceEntry] = Field(default_factory=list, max_length=6)
    weekly_hours: int | None = Field(default=None, ge=1, le=80)
    timeline_weeks: int | None = Field(default=None, ge=1, le=52)

    @model_validator(mode="after")
    def _total_size(self) -> "UserProfile":
        """Each field is bounded, but their maximums add up; cap the whole profile too."""
        size = len(self.model_dump_json())
        if size > MAX_PROFILE_CHARS:
            raise ValueError(f"profile is too long ({size} > {MAX_PROFILE_CHARS} characters)")
        return self


Correction = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class WorkflowInput(BaseModel):
    """Everything a run takes from the user, validated in one place (`run_workflow`), so the API
    route, CLI and tests all get the same limits."""

    model_config = ConfigDict(extra="forbid")

    job_description: str = Field(min_length=50, max_length=MAX_JOB_DESCRIPTION_CHARS)
    profile: UserProfile
    corrections: list[Correction] = Field(default_factory=list, max_length=10)


# ---------- node outputs ----------


class ProfileEvidence(BaseModel):
    """One citable fact: from the profile form (p-1, p-2, ...) or a user correction (c-1, ...).
    Gap analysis cites these ids; code checks they exist."""

    id: str = Field(description="p-N for profile facts, c-N for corrections")
    kind: Literal["education", "skill", "coursework", "project", "experience", "correction"]
    text: str


class JobRequirement(ExtractedRequirement):
    id: str = Field(description="r-1, r-2, ... in extraction order")
    quote_verified: bool
    # Model-written and returned to the client: bounded like the other model text.
    skill: ModelText
    source_quote: ModelText


class JobSummary(BaseModel):
    title: ModelText
    seniority: Seniority
    responsibilities: list[str]
    requirements: list[JobRequirement]


class RequirementEvidence(BaseModel):
    """Knowledge-base search result for one requirement (eligibility items are not searched)."""

    requirement_id: str
    insufficient: bool
    best_score: float | None = None
    evidence: list[Evidence] = Field(default_factory=list)


GapStatus = Literal["demonstrated", "partially_evidenced", "not_yet_evidenced", "not_applicable"]


class GapItem(BaseModel):
    requirement_id: str
    skill: ModelText
    importance: Literal["required", "preferred"]
    status: GapStatus
    profile_evidence_ids: list[str] = Field(default_factory=list)
    knowledge_chunk_ids: list[str] = Field(default_factory=list)
    reasoning: ModelText
    confidence: Literal["low", "medium", "high"]


class RoadmapItem(BaseModel):
    order: int = Field(ge=1)
    topic: ModelText
    requirement_ids: list[str]
    why_it_matters: ModelText
    objective: ModelText
    resources: list[Citation] = Field(default_factory=list)
    exercise: ModelText
    completion_criteria: ModelText
    effort_hours_estimate: float = Field(ge=0, description="An estimate, shown as one")
    depends_on: list[int] = Field(default_factory=list)


class InterviewQuestion(BaseModel):
    requirement_id: str
    question: ModelText
    what_a_good_answer_shows: ModelText


class CritiqueIssue(BaseModel):
    code: str = Field(description="Short machine name, e.g. missing_requirement, bad_citation")
    message: ModelText
    severity: Literal["blocking", "minor"]


class Critique(BaseModel):
    passed: bool
    issues: list[CritiqueIssue] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Passed AND no blocking issue: code decides, the critic's own flag alone isn't enough."""
        return self.passed and not any(i.severity == "blocking" for i in self.issues)


# ---------- result ----------


class CareerPrepResult(BaseModel):
    """What the workflow returns. `status` is honest about what happened:
    complete = the critic passed with no blocking issue; complete_with_limitations = the revision
    limit was reached with issues left (listed in `unresolved_issues`); partial = a stage failed or
    the critic never ran (see `errors`)."""

    status: Literal["complete", "complete_with_limitations", "partial"]
    job: JobSummary | None
    gaps: list[GapItem]
    roadmap: list[RoadmapItem]
    interview_questions: list[InterviewQuestion]
    unresolved_issues: list[CritiqueIssue]
    revisions_used: int
    errors: list[str]
    node_log: list[str]

"""Fallback for the career workflow (T-006): a labelled partial result instead of an error.

`run_workflow` (graph.py) calls `build_fallback` when the graph stops early: a stage failed after
its retry, a dependency (model, Voyage, Qdrant) was unavailable, the time budget ran out, or the
loop limit was hit. Routing and fallback are separate decisions (spec 2A): the router picked the
workflow; this module only decides what can still be offered honestly once it couldn't finish.

What the result keeps: every output the graph had already validated (job, gaps, roadmap,
questions), the stages that finished and those that didn't, a fixed message per reason, the
sources already retrieved per requirement (free), and at most one traditional-RAG answer about
the job's main requirements. Nothing unsupported: if nothing was retrieved, there is no answer.
"""

import logging

import anthropic
import httpx
import voyageai.error
from langgraph.errors import GraphRecursionError
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from gradpath.jobs.analyze import NOT_STUDYABLE
from gradpath.providers import ClaudeCodeError
from gradpath.rag.answer import ChatAnswer, Citation, answer_question, to_citation
from gradpath.workflows.schemas import (
    CareerPrepResult,
    FallbackInfo,
    FallbackReason,
    JobRequirement,
    StudySource,
)
from gradpath.workflows.state import CareerPrepState, WorkflowContext

log = logging.getLogger(__name__)

# The workflow's stages in order. `revise` is optional, so it is listed as not completed only
# when it is the stage that failed.
STAGES = (
    "analyze_job",
    "analyze_profile",
    "retrieve_knowledge",
    "analyze_gaps",
    "plan_roadmap",
    "interview_questions",
    "evaluate",
    "finalize",
)

# Errors that are not outages but a setup problem the user must fix (a wrong or refused key):
# never turned into a fallback, so the API reports them as an error (api/main.py: 502).
NOT_A_FALLBACK: tuple[type[BaseException], ...] = (
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    voyageai.error.AuthenticationError,
)
RATE_LIMIT_ERRORS: tuple[type[BaseException], ...] = (
    anthropic.RateLimitError,
    voyageai.error.RateLimitError,
)

# Errors that mean a service we depend on is down or refusing, not that our code or a model
# reply was wrong. ClaudeCodeError is here: after its retry it means the model is unreachable.
DEPENDENCY_ERRORS: tuple[type[BaseException], ...] = (
    ClaudeCodeError,
    anthropic.APIError,
    voyageai.error.VoyageError,
    ResponseHandlingException,  # Qdrant unreachable
    UnexpectedResponse,  # Qdrant answered with an error
    httpx.HTTPError,
    ConnectionError,
    TimeoutError,
)

MESSAGES: dict[FallbackReason, str] = {
    "stage_failed": "Partial result: one stage of the preparation workflow failed after a retry, "
    "so the personalised plan is incomplete.",
    "dependency_unavailable": "Partial result: a service the workflow needs (the model or the "
    "knowledge-base search) was unavailable, so the personalised plan is incomplete.",
    "rate_limited": "Partial result: a service's rate limit was reached, so the personalised "
    "plan is incomplete. Wait a minute before trying again.",
    "time_budget": "Partial result: the workflow ran past its time limit and was stopped, so "
    "the personalised plan is incomplete.",
    "loop_limit": "Partial result: the workflow reached its step limit and was stopped, so the "
    "personalised plan is incomplete.",
}
RETRY_HINT = " What finished is shown below. Try again later, or add detail to your profile."
NO_HELP = " The knowledge base had nothing relevant to offer for this job."

MAX_ANSWER_SKILLS = 6
MAX_SKILL_CHARS = 80


def classify(exc: BaseException) -> FallbackReason:
    """Map the exception that stopped the graph to a fallback reason (type only)."""
    if isinstance(exc, GraphRecursionError):
        return "loop_limit"
    if isinstance(exc, RATE_LIMIT_ERRORS):
        return "rate_limited"
    if isinstance(exc, DEPENDENCY_ERRORS):
        return "dependency_unavailable"
    return "stage_failed"


def _completed(state: CareerPrepState) -> list[str]:
    """Stages that finished, in order of first completion (node_log may repeat revise/evaluate)."""
    seen: list[str] = []
    for name in state.get("node_log", []):
        if name not in seen:
            seen.append(name)
    return seen


def _study_sources(state: CareerPrepState) -> list[StudySource]:
    """Per requirement with evidence above the threshold, its sources (one citation per
    section), from what `retrieve_knowledge` already found: no extra call."""
    job = state.get("job")
    if job is None:
        return []
    skills = {r.id: r.skill for r in job.requirements}
    out = []
    for k in state.get("knowledge", []):
        if k.insufficient or not k.evidence:
            continue
        citations: dict[tuple[str, str], Citation] = {}
        for e in k.evidence:
            c = to_citation(e)
            citations.setdefault((c.source_url, c.section or ""), c)
        out.append(
            StudySource(
                requirement_id=k.requirement_id,
                skill=skills.get(k.requirement_id, ""),
                citations=list(citations.values()),
            )
        )
    return out


def _question(requirements: list[JobRequirement]) -> str | None:
    """One focused question for the RAG path: the main studyable requirements, required first."""
    studyable = [r for r in requirements if r.category not in NOT_STUDYABLE]
    studyable.sort(key=lambda r: r.importance != "required")
    skills = [r.skill[:MAX_SKILL_CHARS] for r in studyable[:MAX_ANSWER_SKILLS]]
    if not skills:
        return None
    return (
        "What should a new-grad software engineer study first to meet these job requirements: "
        + "; ".join(skills)
        + "?"
    )


def _rag_answer(state: CareerPrepState, context: WorkflowContext) -> ChatAnswer | None:
    """At most one traditional-RAG answer about the job's requirements. It abstains by itself
    when nothing relevant is retrieved. Any failure (the service that stopped the graph may
    still be down) gives None, logged by type only."""
    job = state.get("job")
    if job is None or context.retrieval is None or context.smart_llm is None:
        return None
    question = _question(job.requirements)
    if question is None:
        return None
    try:
        return answer_question(question, context.retrieval, context.smart_llm)
    except Exception as exc:  # the fallback itself must never raise
        log.warning("fallback answer failed (%s)", type(exc).__name__)
        return None


# Reasons where calling the RAG path again would hit the same failing or exhausted service, or
# spend time the budget no longer has. The free, already-retrieved sources are still returned.
NO_EXTRA_CALL: frozenset[str] = frozenset({"time_budget", "dependency_unavailable", "rate_limited"})


def build_fallback(
    state: CareerPrepState,
    reason: FallbackReason,
    failed_stage: str | None,
    context: WorkflowContext,
) -> CareerPrepResult:
    """Assemble the labelled fallback result from the last state the graph completed.

    `state` is the state after the last finished step (graph.py streams it), so every output in
    it was already validated. Never raises: if assembling fails, a minimal result with the
    reason and message only is returned (`_minimal`).
    """
    try:
        return _assemble(state, reason, failed_stage, context)
    except Exception as exc:  # the fallback must never turn into an error itself
        log.error("fallback assembly failed (%s); returning the minimal result", type(exc).__name__)
        return _minimal(state, reason, failed_stage)


def _revised_after_check(state: CareerPrepState) -> bool:
    """True if `revise` ran after the last `evaluate`: the critique describes the old roadmap."""
    log_ = state.get("node_log", [])
    return "revise" in log_ and (
        "evaluate" not in log_ or log_[::-1].index("revise") < log_[::-1].index("evaluate")
    )


def _not_completed(completed: list[str], failed_stage: str | None) -> list[str]:
    missing = [s for s in STAGES if s not in completed]
    if failed_stage == "revise":
        missing.insert(max(0, len(missing) - 1), "revise")  # before finalize
    return missing


def _assemble(
    state: CareerPrepState,
    reason: FallbackReason,
    failed_stage: str | None,
    context: WorkflowContext,
) -> CareerPrepResult:
    completed = _completed(state)
    sources = _study_sources(state)
    answer = None if reason in NO_EXTRA_CALL else _rag_answer(state, context)
    has_help = bool(sources) or (answer is not None and answer.status in ("answered", "partial"))
    message = MESSAGES[reason] + RETRY_HINT + ("" if has_help else NO_HELP)
    critique = state.get("critique")
    errors = [*state.get("errors", []), f"stopped early: {reason}"]
    issues = [] if critique is None else critique.issues
    if _revised_after_check(state):
        # The open issues were found in the roadmap before revision; they don't describe this one.
        issues = []
        errors.append("the revised roadmap was not re-checked")
    return CareerPrepResult(
        status="fallback",
        job=state.get("job"),
        gaps=state.get("gaps", []),
        roadmap=state.get("roadmap", []),
        interview_questions=state.get("interview_questions", []),
        unresolved_issues=issues,
        revisions_used=state.get("revision_count", 0),
        errors=errors,
        node_log=list(state.get("node_log", [])),
        fallback=FallbackInfo(
            reason=reason,
            failed_stage=failed_stage,
            completed_stages=completed,
            not_completed=_not_completed(completed, failed_stage),
            message=message,
            study_sources=sources,
            answer=answer,
        ),
    )


def _minimal(
    state: CareerPrepState, reason: FallbackReason, failed_stage: str | None
) -> CareerPrepResult:
    """Last resort when assembling fails: plain values only, nothing that can fail validation."""
    return CareerPrepResult(
        status="fallback",
        job=None,
        gaps=[],
        roadmap=[],
        interview_questions=[],
        unresolved_issues=[],
        revisions_used=0,
        errors=[f"stopped early: {reason}"],
        node_log=[],
        fallback=FallbackInfo(
            reason=reason,
            failed_stage=failed_stage,
            completed_stages=[],
            not_completed=list(STAGES),
            message=MESSAGES[reason] + RETRY_HINT,
            study_sources=[],
            answer=None,
        ),
    )

"""One entry point for a user request: route it, then run the chosen path (T-006 step 6).

Used by `POST /api/assist` (api/assist.py) and the terminal runner (router/cli.py). Split in two
so the API can hold the right concurrency slot for each part: `decide` makes the routing call;
`respond` runs RAG or the workflow, or replies "needs input" / "not supported yet" without
running anything. The route log entry (`route_log_entry`) records what happened, never the text.
"""

from datetime import UTC, datetime
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, ConfigDict, Field

from gradpath.config import Settings
from gradpath.rag.answer import ChatAnswer, answer_question
from gradpath.retrieval import RetrievalService
from gradpath.router.route import route_request
from gradpath.router.schemas import Kind, RouteDecision, RouteRequest
from gradpath.workflows import CareerPrepResult, UserProfile, WorkflowContext, run_workflow
from gradpath.workflows.schemas import MAX_JOB_DESCRIPTION_CHARS, Correction

Outcome = Literal["answered", "prepared", "needs_input", "unsupported"]

INPUT_NAMES = {"job_description": "a job description", "profile": "your profile"}
UNSUPPORTED: dict[Kind, str] = {
    "job_comparison": "Comparing several jobs isn't supported yet. Send one job description at "
    "a time and compare the plans.",
    "progress_tracking": "Updating an earlier plan from your progress isn't supported yet. "
    "Send the job description and your current profile for a fresh plan.",
    "resume_rewrite": "Rewriting or tailoring a resume isn't supported yet. A preparation plan "
    "for the job is available: send the job description and your profile.",
}


class AssistRequest(BaseModel):
    """A message plus optional inputs. Bounds match the routes they lead to (`/api/chat`,
    `/api/career/prepare`); unknown fields are refused."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=3, max_length=2000)
    job_description: str | None = Field(
        default=None, min_length=50, max_length=MAX_JOB_DESCRIPTION_CHARS
    )
    profile: UserProfile | None = None
    corrections: list[Correction] = Field(default_factory=list, max_length=10)


class AssistResponse(BaseModel):
    """The routing decision and what came of it: a RAG answer, a workflow result, or a fixed
    message saying what is missing or unsupported."""

    decision: RouteDecision
    outcome: Outcome
    message: str | None = None
    answer: ChatAnswer | None = None
    result: CareerPrepResult | None = None


def decide(req: AssistRequest, fast_llm: BaseChatModel) -> RouteDecision:
    """Route the request: the router sees the message and which inputs are attached only."""
    return route_request(
        RouteRequest(
            message=req.message,
            has_job_description=req.job_description is not None,
            has_profile=req.profile is not None,
        ),
        fast_llm,
    )


def respond(
    req: AssistRequest,
    decision: RouteDecision,
    *,
    retrieval: RetrievalService,
    fast_llm: BaseChatModel,
    smart_llm: BaseChatModel,
    settings: Settings,
) -> AssistResponse:
    """Run the decided path. Nothing runs for needs_input or unsupported; the workflow's own
    fallback labels a run that can't finish (status "fallback")."""
    if decision.action == "unsupported":
        text = UNSUPPORTED.get(decision.kind, "This kind of request isn't supported yet.")
        return AssistResponse(decision=decision, outcome="unsupported", message=text)
    if decision.action == "needs_input":
        missing = " and ".join(INPUT_NAMES[m] for m in decision.missing)
        text = f"To prepare a personal plan I need {missing}. Add it and send the request again."
        return AssistResponse(decision=decision, outcome="needs_input", message=text)
    if decision.route == "traditional_rag":
        answer = answer_question(req.message, retrieval, smart_llm)
        return AssistResponse(decision=decision, outcome="answered", answer=answer)
    # agentic_workflow + run: the route table only allows this with both inputs attached. An
    # explicit check (not `assert`, which `python -O` removes) in case the table ever changes.
    if req.job_description is None or req.profile is None:
        raise RuntimeError("workflow route chosen without both inputs")
    result = run_workflow(
        req.job_description,
        req.profile,
        context=WorkflowContext(retrieval=retrieval, fast_llm=fast_llm, smart_llm=smart_llm),
        max_revisions=settings.workflow_max_revisions,
        corrections=list(req.corrections),
        time_budget_s=settings.workflow_time_budget_s,
    )
    return AssistResponse(decision=decision, outcome="prepared", result=result)


def route_log_entry(
    decision: RouteDecision | None,
    response: AssistResponse | None,
    seconds: float,
    error: str | None = None,
) -> dict:
    """One route-log line: route, kind, who decided, outcome, status and time. No message,
    reason or result text (the reason is model text and may echo the message). `error` is
    "busy" for a 503 or the exception's type name, so busy and failed requests stay apart."""
    status = None
    fallback_reason = None
    if response is not None and response.answer is not None:
        status = response.answer.status
    if response is not None and response.result is not None:
        status = response.result.status
        if response.result.fallback is not None:
            fallback_reason = response.result.fallback.reason
    return {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "route": decision.route if decision else None,
        "action": decision.action if decision else None,
        "kind": decision.kind if decision else None,
        "decided_by": decision.decided_by if decision else None,
        "missing": decision.missing if decision else [],
        "outcome": response.outcome if response else "error",
        "error": None if response else (error or "unknown"),
        "status": status,
        "fallback_reason": fallback_reason,
        "seconds": round(seconds, 2),
    }

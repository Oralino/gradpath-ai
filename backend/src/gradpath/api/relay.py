"""Browser relay runs (T-029 step 2): Ask, Analyse a job and Plan on the visitor's own model.

`POST /api/relay/runs` starts a background run whose model calls are relayed to the browser
(`providers/relay.py`); `GET /api/relay/runs/{id}` reports its progress plus the prompts waiting
for an answer; `POST /api/relay/runs/{id}/replies` delivers the browser's answer to one prompt.
The browser polls about once a second, runs each prompt on Ollama, LM Studio or transformers.js
and posts the reply. Every relay request is a background run (owner decision), so no request
waits on a model and Vercel's 120 s proxy limit never applies.

Client rule: keep polling while the local model works. A run whose browser goes
RELAY_IDLE_TIMEOUT_S (90 s) without a poll or reply is treated as a closed tab and stopped, and
one local generation can take minutes (measured: 133 s for a job extraction on llama3.1:8b).

Always-hard area. Live mode needs a GitHub sign-in (no API key: the model is the visitor's);
runs are tied to the signed-in user (`deps.relay_owner`), at most one per user and two on the
server (`limits.RELAY`, apart from the Claude run slot); starts count against the `model` or
`workflow` rate limits (checked after the slot, so a refused start costs nothing) and polls,
replies and cancels against `relay`. Replies are untrusted model
output: bounded here and in the channel, validated by the same schemas as any model reply.
"""

import time
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from gradpath.api import limits
from gradpath.api.deps import get_retrieval, relay_access, relay_owner
from gradpath.api.jobs import AnalyzeRequest
from gradpath.api.ratelimit import LIMITED, charge, ensure_room, limit
from gradpath.api.runs import NOT_FOUND
from gradpath.config import Settings, get_settings
from gradpath.jobs import JobAnalysis, analyze_job
from gradpath.providers import get_chat_model
from gradpath.providers.relay import (
    MAX_REPLY_CHARS,
    RelayBadOutput,
    RelayCancelled,
    RelayChannel,
    RelayClosed,
    RelayLimit,
    RelayModelFailed,
    RelayPrompt,
    RelayTimeout,
)
from gradpath.retrieval import RetrievalService
from gradpath.router import route_log
from gradpath.router.assist import AssistRequest, AssistResponse, decide, respond, route_log_entry
from gradpath.workflows import WorkflowContext
from gradpath.workflows.graph import run_workflow
from gradpath.workflows.runs import (
    OwnerBusy,
    RunBusy,
    RunKind,
    RunStore,
    Stage,
    Work,
    stage_states,
)
from gradpath.workflows.schemas import CareerPrepResult, WorkflowInput

router = APIRouter(prefix="/api/relay", tags=["relay"], dependencies=[Depends(relay_access)])

UUID_SHAPE = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"  # prompt ids (uuid4)
RELAY_BUSY = "The server is running two local-model requests already. Try again in a few minutes."
OWNER_BUSY = "You already have a local-model request running. Wait for it to finish first."
PROMPT_GONE = "This prompt is no longer waiting for a reply."
# Fixed text for how a relay run can fail (`describe`); never the exception's own message.
RELAY_TIMED_OUT = "Your local model did not answer in time. Try a smaller model, then try again."
RELAY_STOPPED = "The request was stopped."
RELAY_GONE = "The request stopped because this page stopped checking in. Start it again."
RELAY_MODEL_FAILED = "Your local model reported an error. Check that it is running, then try again."
RELAY_TOO_MANY = "The request made more model calls than allowed and was stopped."
RELAY_UNREADABLE = "Your local model's reply could not be read. A larger model may do better."

# The process-wide store with its own slot; tests replace it through `get_relay_store`.
RELAY_RUNS = RunStore(limits.RELAY)


def get_relay_store() -> RunStore:
    """The relay run store (a dependency, so tests can swap in their own)."""
    return RELAY_RUNS


class AskStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["ask"]
    request: AssistRequest


class JobStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["job"]
    request: AnalyzeRequest


class PlanStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["plan"]
    request: WorkflowInput


RelayStart = Annotated[AskStart | JobStart | PlanStart, Field(discriminator="kind")]


class RelayStarted(BaseModel):
    run_id: str


class RelayRunStatus(BaseModel):
    """What the browser polls. `prompts` are the model calls waiting for it (running runs only);
    the result is in the field named after the run's kind. `error` is fixed text only."""

    kind: RunKind
    status: Literal["running", "done", "failed"]
    elapsed_s: int
    stages: list[Stage]
    revisions: int
    prompts: list[RelayPrompt]
    ask: AssistResponse | None = None
    job: JobAnalysis | None = None
    plan: CareerPrepResult | None = None
    error: str | None = None


class RelayReply(BaseModel):
    """The browser's answer to one prompt: the model's text, or `failed` if its model errored.
    The text is untrusted model output, bounded like any reply."""

    model_config = ConfigDict(extra="forbid")
    prompt_id: str = Field(pattern=UUID_SHAPE)
    text: str | None = Field(default=None, max_length=MAX_REPLY_CHARS)
    failed: bool = False

    @model_validator(mode="after")
    def _one_of(self) -> "RelayReply":
        if (self.text is None) == (not self.failed):
            raise ValueError("send either text or failed=true")
        return self


def describe(exc: Exception) -> str | None:
    """Fixed text for an exception a relay run's work let through; None means the generic
    failure text. Called by `RunStore._work`."""
    if isinstance(exc, RelayTimeout):
        return RELAY_TIMED_OUT
    if isinstance(exc, RelayCancelled):
        return RELAY_STOPPED
    if isinstance(exc, RelayClosed):
        return RELAY_GONE
    if isinstance(exc, RelayModelFailed):
        return RELAY_MODEL_FAILED
    if isinstance(exc, RelayLimit):
        return RELAY_TOO_MANY
    if isinstance(exc, RelayBadOutput):
        return RELAY_UNREADABLE
    if isinstance(exc, HTTPException) and exc.status_code == 429:
        return LIMITED
    return None


def build_work(
    body: AskStart | JobStart | PlanStart,
    *,
    retrieval: RetrievalService,
    channel: RelayChannel,
    settings: Settings,
    charge_workflow: Callable[[], None],
) -> Work:
    """The run's work for its kind, with both tiers on the relay. A plan gets the relay time
    budget; an Ask the router sends to the workflow becomes a plan in the same run, counted
    against the `workflow` limit only then (`charge_workflow`). Called by `start_run`."""
    fast = get_chat_model("fast", relay=channel)
    smart = get_chat_model("smart", relay=channel)
    context = WorkflowContext(retrieval=retrieval, fast_llm=fast, smart_llm=smart)

    def plan(data: WorkflowInput, progress: Callable[[list[str]], None]) -> CareerPrepResult:
        return run_workflow(
            data.job_description,
            data.profile,
            context=context,
            max_revisions=settings.workflow_max_revisions,
            corrections=data.corrections,
            time_budget_s=settings.relay_time_budget_s,
            on_step=progress,
        )

    if isinstance(body, JobStart):
        return lambda progress: analyze_job(body.request.job_description, retrieval, fast, smart)
    if isinstance(body, PlanStart):
        return lambda progress: plan(body.request, progress)

    req = body.request

    def ask(progress: Callable[[list[str]], None]) -> AssistResponse:
        # The same steps as `POST /api/assist`, with the workflow run inline instead of in a
        # second background run; one route-log line per request, as there.
        start = time.monotonic()
        decision, response, error = None, None, None
        try:
            decision = decide(req, fast)
            if not (decision.route == "agentic_workflow" and decision.action == "run"):
                response = respond(
                    req, decision, retrieval=retrieval, fast_llm=fast, smart_llm=smart,
                    settings=settings,
                )  # fmt: skip
                return response
            if req.job_description is None or req.profile is None:
                raise RuntimeError("workflow route chosen without both inputs")
            charge_workflow()
            data = WorkflowInput(
                job_description=req.job_description,
                profile=req.profile,
                corrections=list(req.corrections),
            )
            response = AssistResponse(
                decision=decision, outcome="prepared", result=plan(data, progress)
            )
            return response
        except Exception as exc:
            error = type(exc).__name__
            raise
        finally:
            route_log.record(
                route_log.log_path(settings),
                route_log_entry(decision, response, time.monotonic() - start, error),
            )

    return ask


@router.post("/runs", status_code=202, response_model=RelayStarted)
def start_run(
    request: Request,
    body: RelayStart,
    retrieval: Annotated[RetrievalService, Depends(get_retrieval)],
    store: Annotated[RunStore, Depends(get_relay_store)],
    owner: Annotated[str | None, Depends(relay_owner)],
) -> RelayStarted:
    """Start a relay run and return its id at once. Counts against `workflow` for a plan and
    `model` otherwise; an Ask with both a posting and a profile attached may become a plan, so
    it is refused up front if the caller has no `workflow` room left (as `/api/assist` does)."""
    settings = get_settings()
    # Refuse a double start or a full server before charging (a plan is 1 of 3 an hour).
    refusal = store.refusal(owner, one_per_owner=True)
    if refusal is OwnerBusy:
        raise HTTPException(status_code=409, detail=OWNER_BUSY)
    if refusal is RunBusy:
        raise HTTPException(status_code=503, detail=RELAY_BUSY)
    ask = body.request if isinstance(body, AskStart) else None
    if ask is not None and ask.job_description is not None and ask.profile is not None:
        ensure_room("workflow", request)
    charge("workflow" if isinstance(body, PlanStart) else "model", request)
    channel = RelayChannel(
        reply_timeout_s=settings.relay_reply_timeout_s,
        idle_timeout_s=settings.relay_idle_timeout_s,
        # Bounds every kind, not just a plan: no relay run holds a thread longer than this.
        deadline_s=settings.relay_time_budget_s + settings.relay_reply_timeout_s,
    )
    work = build_work(
        body,
        retrieval=retrieval,
        channel=channel,
        settings=settings,
        charge_workflow=lambda: charge("workflow", request),
    )
    try:
        run_id = store.start_task(
            work, owner=owner, kind=body.kind, relay=channel, one_per_owner=True, describe=describe
        )
    except OwnerBusy:
        raise HTTPException(status_code=409, detail=OWNER_BUSY) from None
    except RunBusy:
        raise HTTPException(status_code=503, detail=RELAY_BUSY) from None
    return RelayStarted(run_id=run_id)


@router.get("/runs/{run_id}", response_model=RelayRunStatus, dependencies=[Depends(limit("relay"))])
def get_run(
    run_id: str,
    store: Annotated[RunStore, Depends(get_relay_store)],
    owner: Annotated[str | None, Depends(relay_owner)],
) -> RelayRunStatus:
    """Progress, waiting prompts and, once done, the result. Each poll tells the run the browser
    is still there. 404 for an unknown, expired or malformed id and for another user's run."""
    snap = store.snapshot(run_id, owner)
    if snap is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    finished = snap.status != "running"
    result = {snap.kind: snap.result} if snap.result is not None else {}
    return RelayRunStatus(
        kind=snap.kind,
        status=snap.status,
        elapsed_s=snap.elapsed_s,
        stages=stage_states(snap.node_log, finished=finished)
        if snap.kind == "plan" or snap.node_log
        else [],
        revisions=snap.node_log.count("revise"),
        prompts=snap.prompts,
        error=snap.error,
        **result,
    )


@router.delete("/runs/{run_id}", status_code=204, dependencies=[Depends(limit("relay"))])
def cancel_run(
    run_id: str,
    store: Annotated[RunStore, Depends(get_relay_store)],
    owner: Annotated[str | None, Depends(relay_owner)],
) -> Response:
    """Stop the caller's run (the page's Stop button, or leaving the page): the slot is freed as
    soon as the waiting stage gives up. 404 under the same rules as polling."""
    if not store.cancel(run_id, owner):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return Response(status_code=204)


@router.post("/runs/{run_id}/replies", status_code=204, dependencies=[Depends(limit("relay"))])
def post_reply(
    run_id: str,
    body: RelayReply,
    store: Annotated[RunStore, Depends(get_relay_store)],
    owner: Annotated[str | None, Depends(relay_owner)],
) -> Response:
    """Deliver the browser's answer to one waiting prompt. 404 for a run the caller can't see,
    and for a prompt that is unknown, already answered or no longer waiting (one reply each)."""
    channel = store.relay_channel(run_id, owner)
    if channel is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    if not channel.reply(body.prompt_id, body.text, body.failed):
        raise HTTPException(status_code=404, detail=PROMPT_GONE)
    return Response(status_code=204)

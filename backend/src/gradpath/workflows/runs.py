"""Background preparation runs with a run id the browser polls (T-016).

A workflow run takes 80-300 s, too long to hold one HTTP request open. `RunStore.start` runs
`run_workflow` in a background thread and returns a random run id at once. `RunStore.get`
reports the stages done so far and, at the end, the result. Used by `api/runs.py` and
`api/assist.py`; `/api/career/prepare` stays synchronous for the CLI and tests.

Limits are unchanged. The same one-run-at-a-time slot (`limits.CAREER`) is held for the whole
run, and the workflow's own revision limit, time budget and fallback still decide how it ends.
Runs live in memory only: the record never holds the posting or profile, ids are uuid4 and
can't be listed, finished runs expire after RUN_TTL_S, and an API restart forgets them all.

Relay runs (T-029 step 2, `api/relay.py`) use a second store with its own slot: `start_task`
runs any job (an answer, a job analysis or a plan) whose model calls go to the visitor's
browser through the run's `RelayChannel`, which the store closes when the run ends.
"""

import contextvars
import hmac
import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, cast

from pydantic import BaseModel

from gradpath.config import Settings
from gradpath.providers.relay import RelayChannel, RelayPrompt
from gradpath.workflows.fallback import NOT_A_FALLBACK
from gradpath.workflows.graph import NodeSet, run_workflow
from gradpath.workflows.schemas import CareerPrepResult, WorkflowInput
from gradpath.workflows.state import WorkflowContext

log = logging.getLogger(__name__)

RUN_TTL_S = 15 * 60  # a finished run (and its result) is kept this long after it ends
MAX_RUNS = 20  # finished runs kept at most; the oldest go first
FAILED = "The preparation run could not finish. Try again in a few minutes."
# A refused or wrong API key (`fallback.NOT_A_FALLBACK`): retrying won't help, so say so.
KEY_REFUSED = "The model or search service refused the API key. Check the key, then try again."

# The graph's stages, in display order, and what each waits for (workflows/graph.py
# `build_graph`; a test checks this table against the compiled graph so they can't drift).
# After `evaluate` the graph chooses `revise` or `finalize`, so neither is "running" until it
# shows up in the log.
STAGES = (
    "analyze_job",
    "analyze_profile",
    "retrieve_knowledge",
    "analyze_gaps",
    "plan_roadmap",
    "interview_questions",
    "evaluate",
    "revise",
    "finalize",
)
PREREQS: dict[str, tuple[str, ...]] = {
    "analyze_job": (),
    "analyze_profile": (),
    "retrieve_knowledge": ("analyze_job",),
    "analyze_gaps": ("retrieve_knowledge", "analyze_profile"),
    "plan_roadmap": ("analyze_gaps",),
    "interview_questions": ("analyze_gaps",),
    "evaluate": ("plan_roadmap", "interview_questions"),
}
CHOSEN_AFTER_EVALUATE = ("revise", "finalize")

StageState = Literal["done", "running", "waiting"]


class Stage(BaseModel):
    name: str
    state: StageState


class RunStarted(BaseModel):
    run_id: str


class RunStatus(BaseModel):
    """What `GET /api/career/runs/{id}` returns. `error` is fixed text only."""

    status: Literal["running", "done", "failed"]
    elapsed_s: int
    stages: list[Stage]
    revisions: int
    result: CareerPrepResult | None = None
    error: str | None = None


class RunBusy(Exception):
    """A run is already going (the one-at-a-time slot is taken)."""


class OwnerBusy(RunBusy):
    """This owner already has a run going (relay runs: one per signed-in user)."""


RunKind = Literal["ask", "job", "plan"]
# Names in log lines; "preparation run" is the wording the log searches already use.
LOG_NAMES: dict[str, str] = {"plan": "preparation", "ask": "ask", "job": "job analysis"}
# A run's work: called in the worker thread with the progress callback, returns the result.
Work = Callable[[Callable[[list[str]], None]], BaseModel]


def stage_states(node_log: list[str], *, finished: bool = False) -> list[Stage]:
    """Done, running or waiting for each stage, from the stages finished so far. Called by
    `RunStore.get`; pure, so every point of a run is tested. "running" means every stage it
    waits for is done; while the critic's verdict is unknown, nothing after it is running.
    `revise` is listed only once it has run, and a revise makes `evaluate` run again."""
    done = set(node_log)
    rechecking = not finished and bool(node_log) and node_log[-1] == "revise"
    stages: list[Stage] = []
    for name in STAGES:
        if name == "revise" and name not in done:
            continue
        if name == "evaluate" and rechecking:
            state: StageState = "running"
        elif name in done:
            state = "done"
        elif finished or name in CHOSEN_AFTER_EVALUATE:
            state = "waiting"
        elif all(p in done for p in PREREQS[name]):
            state = "running"
        else:
            state = "waiting"
        stages.append(Stage(name=name, state=state))
    return stages


@dataclass
class _Run:
    started: float
    node_log: list[str] = field(default_factory=list)
    status: Literal["running", "done", "failed"] = "running"
    finished: float | None = None
    result: BaseModel | None = None
    error: str | None = None
    owner: str | None = None  # live mode: a keyed hash of the starter's key (`deps.run_owner`)
    kind: RunKind = "plan"
    relay: RelayChannel | None = None  # relay runs only: the browser's prompts and replies
    # Fixed text for an exception the work let through; None means FAILED.
    describe: Callable[[Exception], str | None] | None = None


@dataclass(frozen=True)
class RunSnapshot:
    """A run's state at one moment, for the API to shape (`get` for career runs, the relay
    route for relay runs). `prompts` are the browser's waiting prompts (relay runs only)."""

    kind: RunKind
    status: Literal["running", "done", "failed"]
    elapsed_s: int
    node_log: list[str]
    result: BaseModel | None
    error: str | None
    prompts: list[RelayPrompt]


class RunStore:
    """In-memory runs, guarded by one lock. One process-wide instance lives in `api/runs.py`;
    tests make their own with a fake clock and their own slot."""

    def __init__(
        self,
        slot: threading.BoundedSemaphore,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._slot = slot
        self._clock = clock
        self._lock = threading.Lock()
        self._runs: dict[str, _Run] = {}

    def start(
        self,
        data: WorkflowInput,
        *,
        context: WorkflowContext,
        settings: Settings,
        impl: NodeSet | None = None,
        owner: str | None = None,
    ) -> str:
        """Take the slot (or raise RunBusy), start the run in a thread, return its id at once.
        With an `owner` tag (live mode), `get` shows the run only to a caller with the same tag.

        The thread runs in a copy of the caller's context (`contextvars`), so the tracing rules
        and any request-scoped settings apply exactly as they would in the request itself.
        """

        def work(progress: Callable[[list[str]], None]) -> BaseModel:
            return run_workflow(
                data.job_description,
                data.profile,
                context=context,
                max_revisions=settings.workflow_max_revisions,
                corrections=data.corrections,
                time_budget_s=settings.workflow_time_budget_s,
                impl=impl,
                on_step=progress,
            )

        return self.start_task(work, owner=owner)

    def start_task(
        self,
        work: Work,
        *,
        owner: str | None = None,
        kind: RunKind = "plan",
        relay: RelayChannel | None = None,
        one_per_owner: bool = False,
        describe: Callable[[Exception], str | None] | None = None,
    ) -> str:
        """Take the slot (or raise RunBusy), start `work` in a thread, return its id at once.
        Used by `start` and by relay runs (`api/relay.py`). With `one_per_owner`, an owner who
        already has a running run gets OwnerBusy (checked and recorded under one lock).
        `describe` maps an exception the work lets through to fixed text for the caller."""
        if not self._slot.acquire(blocking=False):
            raise RunBusy
        # Until the thread starts, a failure here is ours: release the slot and forget the run.
        # Once it has started, the thread owns the slot and releases it itself.
        run_id = str(uuid.uuid4())
        run = _Run(started=self._clock(), owner=owner, kind=kind, relay=relay, describe=describe)
        try:
            with self._lock:
                self._purge()
                if one_per_owner and owner is not None and self._has_running(owner):
                    raise OwnerBusy
                self._runs[run_id] = run
            worker = threading.Thread(
                target=contextvars.copy_context().run,
                args=(self._work, run, work),
                name=f"gradpath-run-{run_id[:8]}",
                daemon=True,
            )
            worker.start()
        except BaseException:
            with self._lock:
                self._runs.pop(run_id, None)  # a run that never started can't linger
            if relay is not None:
                relay.close()
            self._slot.release()
            raise
        return run_id

    def refusal(self, owner: str | None, *, one_per_owner: bool = False) -> type[RunBusy] | None:
        """Why `start_task` would refuse now (OwnerBusy or RunBusy), or None. A peek, so a route
        can refuse before it charges a rate limit; `start_task` still decides, under its lock."""
        with self._lock:
            if one_per_owner and owner is not None and self._has_running(owner):
                return OwnerBusy
        if not self._slot.acquire(blocking=False):
            return RunBusy
        self._slot.release()
        return None

    def cancel(self, run_id: str, owner: str | None = None) -> bool:
        """Stop a relay run: close its channel, so the stage waiting on the browser fails at once
        and the run ends (as a labelled fallback for a plan). False under the rules of
        `snapshot`, or for a run without a relay."""
        run = self._find(run_id, owner)
        if run is None or run.relay is None:
            return False
        run.relay.close(cancelled=True)
        return True

    def _has_running(self, owner: str) -> bool:
        """Whether `owner` has a run still going. Called with the lock held."""
        return any(
            r.status == "running" and r.owner is not None and hmac.compare_digest(r.owner, owner)
            for r in self._runs.values()
        )

    def _work(self, run: _Run, work: Work) -> None:
        """The thread body: run the work, free the slot, then publish the outcome. The slot
        is released BEFORE "done" or "failed" is visible, so a client that sees a finished run
        can start the next one at once (no spurious 503). A relay run's channel is closed
        first, so a stage still waiting on the browser stops at once."""

        def progress(node_log: list[str]) -> None:
            with self._lock:
                run.node_log = node_log

        result: BaseModel | None = None
        error: str | None = FAILED  # until the work returns
        try:
            result = work(progress)
            error = None
        except Exception as exc:
            # run_workflow turns stage failures into a fallback result; this is only for what
            # it lets through (a refused key, bad input, a relay answer that never came).
            # Type only: messages can quote input.
            log.error("%s run failed (%s)", LOG_NAMES[run.kind], type(exc).__name__)
            if isinstance(exc, NOT_A_FALLBACK):
                error = KEY_REFUSED
            else:
                error = (run.describe(exc) if run.describe else None) or FAILED
        finally:
            # Also reached on a BaseException: the run is then published as failed, never left
            # "running" until it expires.
            if run.relay is not None:
                run.relay.close()
            self._slot.release()
            with self._lock:
                run.finished = self._clock()
                if result is not None:
                    run.result = result
                    run.node_log = list(getattr(result, "node_log", None) or run.node_log)
                    run.status = "done"
                else:
                    run.status = "failed"
                    run.error = error
            # Type-only completion line, so fallback frequency stays observable (the route log
            # records only that a run started).
            fallback = getattr(result, "fallback", None)
            log.info(
                "%s run finished: %s, %s, %ds",
                LOG_NAMES[run.kind],
                getattr(result, "status", "done") if result is not None else "failed",
                fallback.reason if fallback is not None else "-",
                int(run.finished - run.started),
            )

    def snapshot(self, run_id: str, owner: str | None = None) -> RunSnapshot | None:
        """The run's state now, or None if the id is unknown, expired, not a uuid, or the run
        belongs to another owner: all four look the same to the caller (no way to probe ids).
        For a running relay run this also counts as the browser's poll."""
        run = self._find(run_id, owner)
        if run is None:
            return None
        # Read the prompts outside the store lock: the channel has its own.
        prompts = run.relay.pending() if run.relay is not None else []
        with self._lock:
            end = run.finished if run.finished is not None else self._clock()
            return RunSnapshot(
                kind=run.kind,
                status=run.status,
                elapsed_s=int(end - run.started),
                node_log=list(run.node_log),
                result=run.result,
                error=run.error,
                prompts=prompts if run.status == "running" else [],
            )

    def relay_channel(self, run_id: str, owner: str | None = None) -> RelayChannel | None:
        """A relay run's channel, for the reply route; None under the same rules as `snapshot`,
        or if the run has no relay."""
        run = self._find(run_id, owner)
        return None if run is None else run.relay

    def _find(self, run_id: str, owner: str | None) -> _Run | None:
        """The run for `run_id` if `owner` may see it (purging expired runs first)."""
        try:
            key = str(uuid.UUID(run_id))
        except (ValueError, AttributeError, TypeError):
            return None
        with self._lock:
            self._purge()
            run = self._runs.get(key)
            if run is None:
                return None
            if run.owner is not None and not hmac.compare_digest(run.owner, owner or ""):
                return None
            return run

    def get(self, run_id: str, owner: str | None = None) -> RunStatus | None:
        """A career run's current status (`GET /api/career/runs/{id}`), or None under the rules
        of `snapshot`."""
        snap = self.snapshot(run_id, owner)
        if snap is None:
            return None
        return RunStatus(
            status=snap.status,
            elapsed_s=snap.elapsed_s,
            stages=stage_states(snap.node_log, finished=snap.status != "running"),
            revisions=snap.node_log.count("revise"),
            result=cast(CareerPrepResult | None, snap.result),
            error=snap.error,
        )

    def _purge(self) -> None:
        """Drop finished runs past RUN_TTL_S, then the oldest finished ones over MAX_RUNS.
        Called with the lock held, on every start and get."""
        now = self._clock()
        finished = [(k, r) for k, r in self._runs.items() if r.finished is not None]
        for key, run in finished:
            if now - run.finished > RUN_TTL_S:
                del self._runs[key]
        finished = sorted(
            ((k, r) for k, r in self._runs.items() if r.finished is not None),
            key=lambda kr: kr[1].finished,
        )
        while len(self._runs) > MAX_RUNS and finished:
            del self._runs[finished.pop(0)[0]]

"""The career-preparation graph (T-003): wiring, the bounded revision loop, and `run_workflow`.

    START -+- analyze_job -- retrieve_knowledge -+
           +- analyze_profile -------------------+- analyze_gaps
    analyze_gaps -+- plan_roadmap --------+
                  +- interview_questions -+- evaluate
    evaluate -> revise -> evaluate (at most max_revisions times) | evaluate -> finalize -> END

Called by the API route and CLI (step 6) and by tests, which pass their own node implementations.
The loop limit is enforced here, not in the nodes: the revision counter is incremented by a
wrapper around `revise`; no node may write the input or bookkeeping keys (`PROTECTED`), so none
can reset the counter or raise the limit; and `recursion_limit` is set from the same number as a
second, independent stop.
"""

import contextlib
import inspect
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from typing import Literal

from langchain_core.exceptions import OutputParserException
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RetryPolicy
from pydantic import ValidationError

from gradpath.config import MAX_REVISIONS_CAP
from gradpath.providers import ClaudeCodeError
from gradpath.workflows import critic, fallback, gaps, nodes, roadmap
from gradpath.workflows.schemas import CareerPrepResult, UserProfile, WorkflowInput
from gradpath.workflows.state import CareerPrepState, WorkflowContext

log = logging.getLogger(__name__)

# Keys only run_workflow and the graph's own wrappers write. A node update containing one is
# refused, so a buggy or confused node can't change the input, the limit or the counter.
PROTECTED = frozenset(
    {"job_description", "profile", "corrections", "max_revisions", "revision_count", "node_log"}
)


@dataclass(frozen=True)
class NodeSet:
    """One implementation per node: the real nodes by default; tests pass their own."""

    analyze_job: Callable = nodes.analyze_job
    analyze_profile: Callable = nodes.analyze_profile
    retrieve_knowledge: Callable = nodes.retrieve_knowledge
    analyze_gaps: Callable = gaps.analyze_gaps
    plan_roadmap: Callable = roadmap.plan_roadmap
    interview_questions: Callable = gaps.interview_questions
    evaluate: Callable = critic.evaluate
    revise: Callable = roadmap.revise
    finalize: Callable = nodes.finalize


# Nodes that call a model. Each gets ONE retry (max_attempts=2), and only for an allow-list of
# errors: a model reply that fails validation, or a Claude Code call that errors. LangGraph's
# default would skip the first (ValidationError is a ValueError) yet retry almost anything else,
# including an API 401 from a bad visitor key. Network errors are not on the list: the Anthropic
# SDK already retries those itself (max_retries=2 in providers.factory), so retrying here too
# would multiply requests. A second failure ends in a fallback result (`run_workflow`).
MODEL_NODES = frozenset(
    {"analyze_job", "analyze_gaps", "plan_roadmap", "interview_questions", "evaluate", "revise"}
)
MODEL_ATTEMPTS = 2
RETRYABLE = (ValidationError, OutputParserException, ClaudeCodeError)


def _retry_on(exc: Exception) -> bool:
    """True only for RETRYABLE errors. Our guard errors (protected keys, non-dict returns) are
    plain ValueError/TypeError, so they're never retried. Known cost: a ValidationError from our
    own construction code (a bug, not bad model output) also gets one retry."""
    return isinstance(exc, RETRYABLE)


class _NoExceptionText(logging.Filter):
    """LangGraph logs each retry as "Retrying task ... after <Type> <message>" with the traceback.
    For a Pydantic error the message quotes the model's reply (posting or profile text), so keep
    the exception type and drop its text and traceback."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Only the retry line; other records on this logger (e.g. observer failures) are left
        # as they are.
        is_retry = isinstance(record.msg, str) and record.msg.startswith("Retrying task")
        if is_retry and record.exc_info and record.exc_info[1] is not None:
            name = type(record.exc_info[1]).__name__
            msg = record.getMessage()
            cut = msg.find(f" after {name}")
            record.msg = (
                msg[: cut + len(f" after {name}")] if cut >= 0 else f"retrying after {name}"
            )
            record.args = ()
            record.exc_info = None
            record.exc_text = None
        return True


# langgraph 1.2.22 logs retries from this (internal) module; a test pins the name.
RETRY_LOGGER = "langgraph.pregel._retry"
logging.getLogger(RETRY_LOGGER).addFilter(_NoExceptionText())

MODEL_RETRY = RetryPolicy(max_attempts=MODEL_ATTEMPTS, initial_interval=1.0, retry_on=_retry_on)


FAILED_NODE_ATTR = "gradpath_failed_node"


def _wrap(name: str, fn: Callable) -> Callable:
    """Wrap a node for the graph: pass the runtime only if the node has a parameter named
    `runtime` (the convention; pure nodes take just the state), check it returned a mapping
    without protected keys (and `result` only from finalize), log its name to `node_log`, and
    for `revise` add one to the counter, whatever the node returned."""
    wants_runtime = "runtime" in inspect.signature(fn).parameters
    forbidden = PROTECTED if name == "finalize" else PROTECTED | {"result"}

    def run(state: CareerPrepState, runtime) -> dict:
        try:
            update = fn(state, runtime) if wants_runtime else fn(state)
            if not isinstance(update, Mapping):
                raise TypeError(f"node {name!r} returned {type(update).__name__}, expected a dict")
            bad = forbidden & update.keys()
            if bad:
                raise ValueError(f"node {name!r} may not write {sorted(bad)}")
        except Exception as exc:
            # Record which stage failed for the fallback (`run_workflow`); the first one wins.
            if getattr(exc, FAILED_NODE_ATTR, None) is None:
                with contextlib.suppress(AttributeError):
                    setattr(exc, FAILED_NODE_ATTR, name)
            raise
        update = {**update, "node_log": [name]}
        if name == "revise":
            update["revision_count"] = state.get("revision_count", 0) + 1
        return update

    run.__name__ = name
    return run


def route_after_evaluation(state: CareerPrepState) -> Literal["revise", "finalize"]:
    """The loop's only decision: revise while the critique is not ok AND rounds are left."""
    critique = state.get("critique")
    if critique is None or critique.ok:
        return "finalize"
    if state.get("revision_count", 0) >= state.get("max_revisions", 0):
        return "finalize"
    return "revise"


def _only_finalize_left(state: CareerPrepState) -> bool:
    """True right after an `evaluate` that routes to `finalize`: the plan is checked and only
    assembly is left, so a time-budget stop there would only hide a finished result."""
    log_ = state.get("node_log", [])
    return bool(log_) and log_[-1] == "evaluate" and route_after_evaluation(state) == "finalize"


def recursion_limit_for(max_revisions: int) -> int:
    """Super-steps the graph can need: 7 without revisions (LangGraph counts the input step, then
    job+profile, retrieve, gaps, roadmap+questions, evaluate, finalize; parallel nodes share a
    step) plus 2 per revision (revise, evaluate), plus 2 spare. Measured, and pinned by a test.
    A loop bug stops here with GraphRecursionError."""
    return 7 + 2 * max_revisions + 2


def build_graph(impl: NodeSet | None = None) -> CompiledStateGraph:
    """Wire the nodes into a compiled LangGraph graph (see the module docstring for the shape)."""
    impl = impl or NodeSet()
    graph = StateGraph(CareerPrepState, context_schema=WorkflowContext)
    for f in fields(NodeSet):
        retry = MODEL_RETRY if f.name in MODEL_NODES else None
        graph.add_node(f.name, _wrap(f.name, getattr(impl, f.name)), retry_policy=retry)

    graph.add_edge(START, "analyze_job")
    graph.add_edge(START, "analyze_profile")
    graph.add_edge("analyze_job", "retrieve_knowledge")
    # A list of start nodes = wait for all of them (a join), however many steps each branch takes.
    graph.add_edge(["retrieve_knowledge", "analyze_profile"], "analyze_gaps")
    graph.add_edge("analyze_gaps", "plan_roadmap")
    graph.add_edge("analyze_gaps", "interview_questions")
    graph.add_edge(["plan_roadmap", "interview_questions"], "evaluate")
    graph.add_conditional_edges(
        "evaluate", route_after_evaluation, {"revise": "revise", "finalize": "finalize"}
    )
    graph.add_edge("revise", "evaluate")
    graph.add_edge("finalize", END)
    return graph.compile(name="career_prep")


def run_workflow(
    job_description: str,
    profile: UserProfile,
    *,
    context: WorkflowContext,
    max_revisions: int,
    corrections: list[str] | None = None,
    impl: NodeSet | None = None,
    time_budget_s: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    on_step: Callable[[list[str]], None] | None = None,
) -> CareerPrepResult:
    """Validate the input (`WorkflowInput`), run the graph once and return its result.

    `on_step` (T-016) gets a copy of `node_log` after each finished step, so a background run
    (`workflows/runs.py`) can report progress. It only observes: an error in it is logged by type
    and ignored, never changing the run's limits or result.

    `max_revisions` and `time_budget_s` come from settings, never from the request. Raises
    pydantic.ValidationError for bad input. Once the graph is running, nothing it raises reaches
    the caller (except KeyboardInterrupt and the like): the graph is streamed step by step, and a
    stage that fails after its retry, an unavailable service, the loop limit, or the budget
    being exceeded (checked between steps; a running stage is not interrupted) ends in a result
    with status "fallback" built from the last completed step (`fallback.build_fallback`).
    """
    if type(max_revisions) is not int or not 0 <= max_revisions <= MAX_REVISIONS_CAP:
        raise ValueError(
            f"max_revisions must be an int 0..{MAX_REVISIONS_CAP}, got {max_revisions!r}"
        )
    if time_budget_s is not None and not time_budget_s > 0:
        raise ValueError(f"time_budget_s must be positive, got {time_budget_s!r}")
    data = WorkflowInput(
        job_description=job_description, profile=profile, corrections=list(corrections or [])
    )
    state: CareerPrepState = {
        "job_description": data.job_description,
        "profile": data.profile,
        "corrections": data.corrections,
        "max_revisions": max_revisions,
        "revision_count": 0,
        "errors": [],
        "node_log": [],
    }
    graph = build_graph(impl)
    last: CareerPrepState = state
    start = clock()
    stopped: tuple[fallback.FallbackReason, str | None] | None = None
    try:
        # stream_mode="values": the whole state after each finished step, so `last` always
        # holds validated outputs only (a failed step's writes are never applied). `closing`
        # shuts the graph down at once when we stop early, instead of at garbage collection.
        steps = graph.stream(
            state,
            context=context,
            config={"recursion_limit": recursion_limit_for(max_revisions)},
            stream_mode="values",
        )
        with contextlib.closing(steps):
            for values in steps:
                last = values
                if on_step is not None:
                    try:
                        on_step(list(values.get("node_log", [])))
                    except Exception as exc:  # progress reporting must never break a run
                        log.warning("on_step failed (%s)", type(exc).__name__)
                if "result" in values:
                    break
                over = time_budget_s is not None and clock() - start > time_budget_s
                if over and not _only_finalize_left(values):
                    log.warning("workflow fallback: time budget of %.0fs exceeded", time_budget_s)
                    stopped = ("time_budget", None)
                    break
    except fallback.NOT_A_FALLBACK:
        raise  # a wrong or refused key is a setup error to report, not an outage to work around
    except Exception as exc:
        stopped = (fallback.classify(exc), getattr(exc, FAILED_NODE_ATTR, None))
        log.warning(
            "workflow fallback: %s at %s (%s)",
            stopped[0],
            stopped[1] or "unknown",
            type(exc).__name__,
        )
    if stopped is not None:
        return fallback.build_fallback(last, stopped[0], stopped[1], context)
    if "result" not in last:  # the graph ended without finalize: treat it as a failed stage
        log.warning("workflow fallback: graph ended without a result")
        return fallback.build_fallback(last, "stage_failed", None, context)
    return last["result"].model_copy(update={"node_log": last["node_log"]})

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

import inspect
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
from gradpath.workflows import critic, gaps, nodes, roadmap
from gradpath.workflows.schemas import CareerPrepResult, UserProfile, WorkflowInput
from gradpath.workflows.state import CareerPrepState, WorkflowContext

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
# would multiply requests. A second failure propagates (fallback is Milestone 4).
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


MODEL_RETRY = RetryPolicy(max_attempts=MODEL_ATTEMPTS, initial_interval=1.0, retry_on=_retry_on)


def _wrap(name: str, fn: Callable) -> Callable:
    """Wrap a node for the graph: pass the runtime only if the node has a parameter named
    `runtime` (the convention; pure nodes take just the state), check it returned a mapping
    without protected keys (and `result` only from finalize), log its name to `node_log`, and
    for `revise` add one to the counter, whatever the node returned."""
    wants_runtime = "runtime" in inspect.signature(fn).parameters
    forbidden = PROTECTED if name == "finalize" else PROTECTED | {"result"}

    def run(state: CareerPrepState, runtime) -> dict:
        update = fn(state, runtime) if wants_runtime else fn(state)
        if not isinstance(update, Mapping):
            raise TypeError(f"node {name!r} returned {type(update).__name__}, expected a dict")
        bad = forbidden & update.keys()
        if bad:
            raise ValueError(f"node {name!r} may not write {sorted(bad)}")
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
) -> CareerPrepResult:
    """Validate the input (`WorkflowInput`), run the whole graph once and return its result.
    `max_revisions` comes from settings (the caller passes `settings.workflow_max_revisions`),
    never from the request. Raises pydantic.ValidationError for bad input; GraphRecursionError
    and node exceptions propagate for now (step 6 maps them to API errors)."""
    if type(max_revisions) is not int or not 0 <= max_revisions <= MAX_REVISIONS_CAP:
        raise ValueError(
            f"max_revisions must be an int 0..{MAX_REVISIONS_CAP}, got {max_revisions!r}"
        )
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
    final = build_graph(impl).invoke(
        state,
        context=context,
        config={"recursion_limit": recursion_limit_for(max_revisions)},
    )
    return final["result"].model_copy(update={"node_log": final["node_log"]})

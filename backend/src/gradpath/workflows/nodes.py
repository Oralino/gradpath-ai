"""Workflow nodes. Each takes the state (and, when it needs services, the runtime) and returns only
the keys it changed.

This module: `analyze_job`, `retrieve_knowledge`, `analyze_profile`, `finalize`. The model-heavy
nodes live in `gaps.py`, `roadmap.py` and `critic.py`. `graph.build_graph` wires whichever
implementations it is given. Nodes that need services take a parameter named `runtime`
(LangGraph's `Runtime`) and read them from `runtime.context` (`WorkflowContext`).
"""

from langgraph.runtime import Runtime

from gradpath.jobs.analyze import (
    NOT_STUDYABLE,
    clean_requirements,
    extract_requirements,
    quote_in_text,
)
from gradpath.workflows.schemas import (
    CareerPrepResult,
    JobRequirement,
    JobSummary,
    ProfileEvidence,
    RequirementEvidence,
    UserProfile,
)
from gradpath.workflows.state import CareerPrepState, WorkflowContext

SEARCH_K = 3  # evidence chunks per requirement, as in jobs.analyze_job
SEARCH_MAX_PER_DOCUMENT = 2
MAX_RESPONSIBILITIES = 15  # model-written, returned to the client


def _need(service, name: str):
    """Fail with a clear message when a node runs without a service it needs."""
    if service is None:
        raise RuntimeError(f"WorkflowContext.{name} is not set")
    return service


def analyze_job(state: CareerPrepState, runtime: Runtime[WorkflowContext]) -> dict:
    """Haiku extracts requirements from the (untrusted) posting; each gets an id (r-1, r-2, ...)
    and its quote is checked against the posting in code. Reuses `jobs.analyze`'s extraction, so
    the endpoint and the workflow extract the same way. Feeds `retrieve_knowledge` and gaps."""
    llm = _need(runtime.context.fast_llm, "fast_llm")
    jd = state["job_description"]
    extraction = extract_requirements(jd, llm)
    reqs = [
        JobRequirement(
            **r.model_dump(), id=f"r-{i}", quote_verified=quote_in_text(r.source_quote, jd)
        )
        for i, r in enumerate(clean_requirements(extraction), 1)
    ]
    job = JobSummary(
        title=extraction.title,
        seniority=extraction.seniority,
        responsibilities=[r[:300] for r in extraction.responsibilities[:MAX_RESPONSIBILITIES]],
        requirements=reqs,
    )
    return {"job": job}


def retrieve_knowledge(state: CareerPrepState, runtime: Runtime[WorkflowContext]) -> dict:
    """One batched search (one Voyage request) for every studyable requirement; eligibility items
    (degree, clearance) are not searched. `insufficient` results are kept so gap analysis and the
    roadmap know the knowledge base doesn't cover that requirement."""
    retrieval = _need(runtime.context.retrieval, "retrieval")
    searchable = [r for r in state["job"].requirements if r.category not in NOT_STUDYABLE]
    if not searchable:
        return {"knowledge": []}
    found = retrieval.search_many(
        [r.skill for r in searchable], k=SEARCH_K, max_per_document=SEARCH_MAX_PER_DOCUMENT
    )
    knowledge = [
        RequirementEvidence(
            requirement_id=r.id,
            insufficient=res.insufficient,
            best_score=None if res.best_score is None else round(res.best_score, 3),
            evidence=res.evidence,
        )
        for r, res in zip(searchable, found, strict=True)
    ]
    return {"knowledge": knowledge}


def profile_to_evidence(profile: UserProfile) -> list[ProfileEvidence]:
    """Flatten the profile form into numbered facts (p-1, p-2, ...) that gap analysis can cite.
    Called by `analyze_profile`. Pure code: with a structured form there is nothing to extract."""
    items: list[tuple[str, str]] = []
    if profile.education:
        items.append(("education", profile.education))
    items += [("skill", s) for s in profile.skills]
    items += [("coursework", c) for c in profile.coursework]
    for p in profile.projects:
        tech = f" (technologies: {', '.join(p.technologies)})" if p.technologies else ""
        items.append(("project", f"{p.name}: {p.description}{tech}"))
    for e in profile.experience:
        where = f" at {e.organisation}" if e.organisation else ""
        items.append(("experience", f"{e.role}{where}: {e.description}"))
    return [ProfileEvidence(id=f"p-{i}", kind=k, text=t) for i, (k, t) in enumerate(items, 1)]


def analyze_profile(state: CareerPrepState) -> dict:
    """Profile facts plus the user's corrections ("I have used PostgreSQL indexes"), which become
    self-reported facts c-1, c-2, ... that gap analysis may cite: how "correct assumptions and
    regenerate" works (owner decision 2026-11-18). They are facts, never instructions."""
    corrections = [
        ProfileEvidence(id=f"c-{i}", kind="correction", text=c)
        for i, c in enumerate(state.get("corrections", []), 1)
    ]
    return {"profile_evidence": profile_to_evidence(state["profile"]) + corrections}


def finalize(state: CareerPrepState) -> dict:
    """Assemble the result and label it honestly (see `CareerPrepResult.status`). Runs once,
    after the critique is ok or the revision limit was reached. Unresolved issues are kept even
    when the result is partial."""
    critique = state.get("critique")
    errors = list(state.get("errors", []))
    if critique is None:
        errors.append("the result was never evaluated")
    if errors:
        status = "partial"
    elif critique.ok:
        status = "complete"
    else:
        status = "complete_with_limitations"
    result = CareerPrepResult(
        status=status,
        job=state.get("job"),
        gaps=state.get("gaps", []),
        roadmap=state.get("roadmap", []),
        interview_questions=state.get("interview_questions", []),
        # Minor issues stay visible on a complete result too (the first real run lost a
        # no_resources warning this way).
        unresolved_issues=[] if critique is None else critique.issues,
        revisions_used=state.get("revision_count", 0),
        errors=errors,
        # node_log is still being written by this step's own wrapper, so it's added in run_workflow
        node_log=[],
    )
    return {"result": result}

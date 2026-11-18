"""Workflow nodes. Each takes the state (and, when it needs services, the runtime) and returns only
the keys it changed.

Step 4 (skeleton): `analyze_profile` and `finalize` are real (pure code, no model). The others are
placeholders (`stub_*`) that return valid, empty outputs without calling any model or Voyage; step
5 replaces them one by one. `graph.build_graph` wires whichever implementations it is given.
"""

from gradpath.workflows.schemas import (
    CareerPrepResult,
    Critique,
    JobSummary,
    ProfileEvidence,
    UserProfile,
)
from gradpath.workflows.state import CareerPrepState


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
    return {"profile_evidence": profile_to_evidence(state["profile"])}


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
        unresolved_issues=[] if critique is None or critique.ok else critique.issues,
        revisions_used=state.get("revision_count", 0),
        errors=errors,
        # node_log is still being written by this step's own wrapper, so it's added in run_workflow
        node_log=[],
    )
    return {"result": result}


# ---------- placeholders, replaced in step 5 ----------


def stub_analyze_job(state: CareerPrepState) -> dict:
    return {"job": JobSummary(title="", seniority="unknown", responsibilities=[], requirements=[])}


def stub_retrieve_knowledge(state: CareerPrepState) -> dict:
    return {"knowledge": []}


def stub_analyze_gaps(state: CareerPrepState) -> dict:
    return {"gaps": []}


def stub_plan_roadmap(state: CareerPrepState) -> dict:
    return {"roadmap": []}


def stub_interview_questions(state: CareerPrepState) -> dict:
    return {"interview_questions": []}


def stub_evaluate(state: CareerPrepState) -> dict:
    return {"critique": Critique(passed=True)}


def stub_revise(state: CareerPrepState) -> dict:
    return {"roadmap": state.get("roadmap", [])}

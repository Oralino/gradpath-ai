"""The critic: the workflow node `evaluate`, run after `plan_roadmap` and after every `revise`.

Code checks come first (cheap, exact). Only when they find nothing blocking does Haiku check what
code can't: whether each item really follows from its gap and its sources. Its findings are
validated too: they must name an item that exists. `graph.route_after_evaluation` then decides
revise or finalize from `Critique.ok`.
"""

import re
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from gradpath.providers import with_structure
from gradpath.workflows.prompting import DATA_RULE, block
from gradpath.workflows.roadmap import budget_hours, gaps_to_address
from gradpath.workflows.schemas import Critique, CritiqueIssue
from gradpath.workflows.state import CareerPrepState, WorkflowContext

OVER_BUDGET_FACTOR = 1.25  # owner-approved design 2026-11-18
MAX_MODEL_ISSUES = 5


def code_checks(state: CareerPrepState) -> list[CritiqueIssue]:
    """Blocking: gaps to address but no roadmap at all; a required gap with no item; total effort
    over 1.25x the hours available. Minor: two items with the same topic; an item with no
    resource although the knowledge base had evidence for its gaps."""
    roadmap = state.get("roadmap", [])
    todo = gaps_to_address(state)
    issues: list[CritiqueIssue] = []
    if todo and not roadmap:
        issues.append(
            CritiqueIssue(
                code="empty_roadmap",
                message=f"{len(todo)} gaps need work but the roadmap has no items.",
                severity="blocking",
            )
        )
    covered = {r for item in roadmap for r in item.requirement_ids}
    for g in todo:
        if g.importance == "required" and g.requirement_id not in covered:
            issues.append(
                CritiqueIssue(
                    code="missing_requirement",
                    message=f"Required gap {g.requirement_id} ({g.skill}) has no roadmap item.",
                    severity="blocking",
                )
            )
    hours = budget_hours(state)
    total = sum(i.effort_hours_estimate for i in roadmap)
    if hours is not None and total > OVER_BUDGET_FACTOR * hours:
        issues.append(
            CritiqueIssue(
                code="over_budget",
                message=f"The plan needs about {total:g} hours but {hours:g} are available.",
                severity="blocking",
            )
        )
    seen: dict[str, int] = {}
    for item in roadmap:
        key = re.sub(r"\W+", " ", item.topic.lower()).strip()
        if key in seen:
            issues.append(
                CritiqueIssue(
                    code="duplicate_topic",
                    message=f"Items {seen[key]} and {item.order} cover the same topic.",
                    severity="minor",
                )
            )
        seen.setdefault(key, item.order)
    has_evidence = {g.requirement_id for g in todo if g.knowledge_chunk_ids}
    for item in roadmap:
        if not item.resources and has_evidence & set(item.requirement_ids):
            issues.append(
                CritiqueIssue(
                    code="no_resources",
                    message=f"Item {item.order} cites no source, though sources exist for it.",
                    severity="minor",
                )
            )
    return issues


CRITIC_PROMPT = f"""You review a study plan for a student. For each <roadmap_item>, check that
its topic, objective and exercise follow from the <gap> it addresses, and that its sources (titles
listed on the item) plausibly teach that topic.

Rules:
- {DATA_RULE}
- Report only real problems, at most {MAX_MODEL_ISSUES}. `item_order` is the item's order number.
- `severity`: "blocking" if the item is unsupported, misleading or unrelated to its gap;
  "minor" for small improvements.
- If the plan is fine, return no issues."""


class CriticFinding(BaseModel):
    item_order: int
    problem: str
    severity: Literal["blocking", "minor"]


class CriticReply(BaseModel):
    issues: list[CriticFinding] = Field(default_factory=list)


def _render(state: CareerPrepState) -> str:
    gaps = {g.requirement_id: g for g in state.get("gaps", [])}
    parts = []
    for g in gaps_to_address(state):
        parts.append(block("gap", f"{g.skill}: {g.reasoning}", id=g.requirement_id))
    for item in state.get("roadmap", []):
        sources = "; ".join(
            f"{c.title} > {c.section}" if c.section else c.title for c in item.resources
        )
        text = (
            f"topic: {item.topic}\nwhy: {item.why_it_matters}\nobjective: {item.objective}\n"
            f"exercise: {item.exercise}\nsources: {sources or 'none'}"
        )
        reqs = ", ".join(r for r in item.requirement_ids if r in gaps)
        parts.append(block("roadmap_item", text, order=item.order, gaps=reqs))
    return "\n".join(parts)


def evaluate(state: CareerPrepState, runtime: Runtime[WorkflowContext]) -> dict:
    """Code checks, then (if nothing blocking and there is a roadmap) a Haiku review. Passed =
    no blocking issue; code, not the model, sets it."""
    issues = code_checks(state)
    roadmap = state.get("roadmap", [])
    if roadmap and not any(i.severity == "blocking" for i in issues):
        llm = runtime.context.fast_llm
        if llm is None:
            raise RuntimeError("WorkflowContext.fast_llm is not set")
        reply: CriticReply = with_structure(llm, CriticReply).invoke(
            [SystemMessage(CRITIC_PROMPT), HumanMessage(_render(state))]
        )
        orders = {i.order for i in roadmap}
        for f in reply.issues[:MAX_MODEL_ISSUES]:
            if f.item_order in orders and f.problem.strip():
                issues.append(
                    CritiqueIssue(
                        code="unsupported_item",
                        message=f"Item {f.item_order}: {f.problem.strip()}",
                        severity=f.severity,
                    )
                )
    passed = not any(i.severity == "blocking" for i in issues)
    return {"critique": Critique(passed=passed, issues=issues)}

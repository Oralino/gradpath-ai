"""Roadmap planning: the workflow nodes `plan_roadmap` and `revise` (both Sonnet).

`plan_roadmap` runs after `analyze_gaps` (in parallel with `interview_questions`); `revise` runs
when `evaluate` finds blocking issues and rounds are left. Both call `_plan`, so a revised roadmap
goes through exactly the same checks as the first: resources only from retrieved chunk ids,
requirement ids that exist, dependencies only on earlier items, at most MAX_ITEMS items.
"""

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from gradpath.providers import with_structure
from gradpath.rag.answer import to_citation
from gradpath.retrieval import Evidence
from gradpath.workflows.prompting import DATA_RULE, block, evidence_blocks
from gradpath.workflows.schemas import CritiqueIssue, GapItem, RoadmapItem
from gradpath.workflows.state import CareerPrepState, WorkflowContext

MAX_ITEMS = 10
TO_ADDRESS = ("not_yet_evidenced", "partially_evidenced")

ROADMAP_PROMPT = f"""You plan how a student prepares for a job. Turn the <gap> blocks into an
ordered list of study items.

Rules:
- {DATA_RULE}
- Required gaps first. Put prerequisites before the items that build on them, and list in
  `depends_on` the `order` numbers of earlier items an item builds on.
- `requirement_ids`: the ids of the gaps the item addresses (one item may cover related gaps).
- `resource_chunk_ids`: ids of <evidence> blocks that teach the topic, chosen only from the
  evidence ids listed on those gaps. If a gap lists none, leave it empty: the knowledge base does
  not cover it, and you must not name or invent other resources.
- `exercise`: a concrete practice task. `completion_criteria`: how the student knows it's done.
- `effort_hours_estimate`: a realistic estimate in hours. Keep the total within the <budget>
  when one is given.
- At most {MAX_ITEMS} items. Never promise that the plan leads to a job."""

REVISE_PROMPT = (
    ROADMAP_PROMPT
    + """

You are revising an earlier plan (<roadmap_item> blocks) that a reviewer found problems with
(<critique_issue> blocks). Fix every issue; keep the items that were fine. Return the whole
revised list."""
)


class DraftItem(BaseModel):
    order: int
    topic: str
    requirement_ids: list[str]
    why_it_matters: str
    objective: str
    resource_chunk_ids: list[str] = Field(default_factory=list)
    exercise: str
    completion_criteria: str
    effort_hours_estimate: float = Field(ge=0)
    depends_on: list[int] = Field(default_factory=list)


class RoadmapReply(BaseModel):
    items: list[DraftItem]


def budget_hours(state: CareerPrepState) -> float | None:
    """Hours available (weekly hours x weeks), or None when the profile doesn't say."""
    p = state["profile"]
    if p.weekly_hours and p.timeline_weeks:
        return float(p.weekly_hours * p.timeline_weeks)
    return None


def gaps_to_address(state: CareerPrepState) -> list[GapItem]:
    """Gaps worth studying, required first and least evidenced first."""
    gaps = [g for g in state.get("gaps", []) if g.status in TO_ADDRESS]
    return sorted(gaps, key=lambda g: (g.importance != "required", TO_ADDRESS.index(g.status)))


def _evidence_by_id(state: CareerPrepState) -> dict[str, Evidence]:
    return {e.chunk_id: e for k in state.get("knowledge", []) for e in k.evidence}


def _render(state: CareerPrepState, gaps: list[GapItem], feedback: list[CritiqueIssue]) -> str:
    chunks = _evidence_by_id(state)
    wanted = [chunks[c] for g in gaps for c in g.knowledge_chunk_ids if c in chunks]
    parts = [evidence_blocks(wanted), ""]
    for g in gaps:
        parts.append(
            block(
                "gap",
                f"{g.skill}: {g.reasoning}",
                id=g.requirement_id,
                importance=g.importance,
                status=g.status,
                evidence_ids=", ".join(g.knowledge_chunk_ids) or "none",
            )
        )
    hours = budget_hours(state)
    parts.append(block("budget", f"{hours:g} hours in total" if hours else "not given"))
    if feedback:
        parts.append("")
        parts += [
            block("roadmap_item", item.model_dump_json(exclude={"resources"}), order=item.order)
            for item in state.get("roadmap", [])
        ]
        parts += [block("critique_issue", i.message, code=i.code) for i in feedback]
    return "\n".join(parts)


def check_items(drafts: list[DraftItem], gaps: list[GapItem], state: CareerPrepState):
    """Keep only what the evidence supports: drop unknown requirement ids (and items left with
    none), keep resources only from chunks retrieved for that item's requirements, renumber 1..n
    in list order, and keep only dependencies on earlier items. Returns the RoadmapItems."""
    by_req = {g.requirement_id: set(g.knowledge_chunk_ids) for g in gaps}
    chunks = _evidence_by_id(state)
    items: list[RoadmapItem] = []
    renumber: dict[int, int] = {}
    for d in drafts:
        if len(items) == MAX_ITEMS:
            break
        req_ids = [r for r in dict.fromkeys(d.requirement_ids) if r in by_req]
        if not req_ids or not d.topic.strip():
            continue
        allowed = set().union(*(by_req[r] for r in req_ids))
        # One citation per source section: two chunks of the same section would show as the same
        # line twice (seen in the first real run).
        resources, shown = [], set()
        for c in dict.fromkeys(d.resource_chunk_ids):
            if c in allowed and c in chunks:
                cite = to_citation(chunks[c])
                if (cite.source_url, cite.section) not in shown:
                    shown.add((cite.source_url, cite.section))
                    resources.append(cite)
        order = len(items) + 1
        deps = sorted({renumber[o] for o in d.depends_on if o in renumber})
        renumber.setdefault(d.order, order)
        items.append(
            RoadmapItem(
                order=order,
                topic=d.topic.strip(),
                requirement_ids=req_ids,
                why_it_matters=d.why_it_matters,
                objective=d.objective,
                resources=resources,
                exercise=d.exercise,
                completion_criteria=d.completion_criteria,
                effort_hours_estimate=d.effort_hours_estimate,
                depends_on=deps,
            )
        )
    return items


def _plan(state: CareerPrepState, runtime, prompt: str, feedback: list[CritiqueIssue]) -> dict:
    """Shared by plan_roadmap and revise: one Sonnet call, then `check_items`."""
    gaps = gaps_to_address(state)
    if not gaps:
        return {"roadmap": []}
    llm = runtime.context.smart_llm
    if llm is None:
        raise RuntimeError("WorkflowContext.smart_llm is not set")
    reply: RoadmapReply = with_structure(llm, RoadmapReply).invoke(
        [SystemMessage(prompt), HumanMessage(_render(state, gaps, feedback))]
    )
    return {"roadmap": check_items(reply.items, gaps, state)}


def plan_roadmap(state: CareerPrepState, runtime: Runtime[WorkflowContext]) -> dict:
    """First roadmap from the gaps that need work."""
    return _plan(state, runtime, ROADMAP_PROMPT, [])


def revise(state: CareerPrepState, runtime: Runtime[WorkflowContext]) -> dict:
    """Re-plan the roadmap with the critic's issues. Keep the previous plan if the revision has no
    valid item or more blocking code-check issues (critic.code_checks) than it: a revision must
    not make the plan worse. The graph counts the round either way (graph._wrap)."""
    from gradpath.workflows.critic import code_checks  # critic imports this module

    critique = state.get("critique")
    update = _plan(state, runtime, REVISE_PROMPT, critique.issues if critique else [])
    old = state.get("roadmap", [])
    if not old:
        return update
    if not update["roadmap"]:
        return {"roadmap": old}

    def blocking(roadmap: list[RoadmapItem]) -> int:
        return sum(i.severity == "blocking" for i in code_checks({**state, "roadmap": roadmap}))

    return {"roadmap": old} if blocking(update["roadmap"]) > blocking(old) else update

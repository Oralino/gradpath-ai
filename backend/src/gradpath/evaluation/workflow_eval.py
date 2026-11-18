"""Workflow eval: run the career workflow on labelled cases and score each result in code.

Run from `backend/` (stop the API first; local Qdrant allows one process):
    uv run python -m gradpath.evaluation.workflow_eval [--only wf-001 ...]
    uv run python -m gradpath.evaluation.workflow_eval --rescore ../evaluation/results/<file>.json

Each case runs the whole workflow with the real models (about 5-7 calls on the plan, one Voyage
request), so keep the case list small. `--rescore` re-scores a saved run with the current cases
and checks, with no model or Voyage call. Cases use fictional sample profiles only.
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gradpath.config import REPO_ROOT, get_settings
from gradpath.workflows import CareerPrepResult, UserProfile, WorkflowContext, run_workflow
from gradpath.workflows.critic import OVER_BUDGET_FACTOR

DEFAULT_CASES = REPO_ROOT / "evaluation" / "workflow_cases.jsonl"
RESULTS_DIR = REPO_ROOT / "evaluation" / "results"
TO_ADDRESS = ("not_yet_evidenced", "partially_evidenced")


class GapExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_any: list[str] = Field(min_length=1, description="lowercase substrings of the skill")
    status_in: list[str] = Field(min_length=1)
    cites_correction: bool = False

    @field_validator("skill_any")
    @classmethod
    def _lower(cls, v: list[str]) -> list[str]:
        return [s.lower() for s in v]


class Expectations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gaps: list[GapExpectation] = Field(default_factory=list)
    roadmap_covers: list[str] = Field(default_factory=list)
    max_demonstrated_share: float = 1.0

    @field_validator("roadmap_covers")
    @classmethod
    def _lower(cls, v: list[str]) -> list[str]:
        return [s.lower() for s in v]


class WorkflowCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    job_description: str = Field(description="path relative to the repo root")
    profile: str = Field(description="path relative to the repo root")
    corrections: list[str] = Field(default_factory=list)
    expect: Expectations
    notes: str = ""

    def load_profile(self) -> UserProfile:
        """The case's profile; must be a fictional sample (results are committed)."""
        profile = UserProfile.model_validate(
            json.loads(_repo_file(self.profile).read_text("utf-8"))
        )
        if not (profile.profile_id or "").startswith("sample-"):
            raise ValueError(f"{self.id}: workflow eval cases must use a sample- profile")
        return profile

    def load_job_description(self) -> str:
        return _repo_file(self.job_description).read_text(encoding="utf-8")


def _repo_file(relative: str) -> Path:
    """Resolve a path from the cases file; it must stay inside the repo."""
    path = (REPO_ROOT / relative).resolve()
    if not path.is_relative_to(REPO_ROOT.resolve()):
        raise ValueError(f"path outside the repo: {relative}")
    return path


def load_cases(path: Path = DEFAULT_CASES) -> list[WorkflowCase]:
    """Read the JSONL case file; unknown fields and duplicate ids are errors."""
    cases = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                cases.append(WorkflowCase.model_validate_json(line))
            except ValueError as exc:
                raise ValueError(f"{path.name} line {n}: {exc}") from exc
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids")
    return cases


def score(case: WorkflowCase, result: CareerPrepResult, profile: UserProfile, max_rev: int):
    """All checks for one result; returns {check: bool} plus counts. Pure: no model calls.
    Called by `run_case` and `--rescore`; tested with hand-made results."""
    gaps = result.gaps
    by_id = {g.requirement_id: g for g in gaps}
    checks: dict[str, bool] = {
        "not_partial": result.status != "partial",
        "loop_terminated": result.revisions_used <= max_rev,
    }
    for i, exp in enumerate(case.expect.gaps, 1):
        matched = [g for g in gaps if any(s in g.skill.lower() for s in exp.skill_any)]
        ok = any(
            g.status in exp.status_in
            and (
                not exp.cites_correction or any(f.startswith("c-") for f in g.profile_evidence_ids)
            )
            for g in matched
        )
        checks[f"gap_{i}:{exp.skill_any[0]}"] = ok
    for kw in case.expect.roadmap_covers:
        checks[f"covers:{kw}"] = any(
            kw in item.topic.lower()
            or any(kw in by_id[r].skill.lower() for r in item.requirement_ids if r in by_id)
            for item in result.roadmap
        )
    studyable = [g for g in gaps if g.status != "not_applicable"]
    demonstrated = sum(g.status == "demonstrated" for g in studyable)
    share = demonstrated / len(studyable) if studyable else 0.0
    checks["demonstrated_share"] = share <= case.expect.max_demonstrated_share
    covered = {r for item in result.roadmap for r in item.requirement_ids}
    checks["required_gaps_covered"] = all(
        g.requirement_id in covered
        for g in gaps
        if g.importance == "required" and g.status in TO_ADDRESS
    )
    # An item that cites sources must name only known requirements, and every source must have
    # been retrieved for one of them.
    checks["citations_retrieved"] = all(
        all(r in by_id for r in item.requirement_ids)
        and {c.chunk_id for c in item.resources}
        <= {cid for r in item.requirement_ids for cid in by_id[r].knowledge_chunk_ids}
        for item in result.roadmap
        if item.resources
    )
    total = sum(i.effort_hours_estimate for i in result.roadmap)
    budget = (
        profile.weekly_hours * profile.timeline_weeks
        if profile.weekly_hours and profile.timeline_weeks
        else None
    )
    flagged = any(i.code == "over_budget" for i in result.unresolved_issues)
    checks["budget_respected_or_flagged"] = (
        budget is None or total <= OVER_BUDGET_FACTOR * budget or flagged
    )
    uncited = sum(
        1
        for item in result.roadmap
        if not item.resources
        and any(by_id[r].knowledge_chunk_ids for r in item.requirement_ids if r in by_id)
    )
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "counts": {
            "requirements": len(gaps),
            "demonstrated_share": round(share, 2),
            "roadmap_items": len(result.roadmap),
            "effort_hours": total,
            "budget_hours": budget,
            "uncited_items_with_evidence": uncited,
            "questions": len(result.interview_questions),
            "revisions": result.revisions_used,
        },
    }


def run_case(case: WorkflowCase, ctx: WorkflowContext, max_rev: int) -> dict:
    """Run one case with real services. A failed run is recorded by exception type only (its
    message can quote a model reply). Reading inputs and scoring are inside the try too, so
    one bad case can't stop the run."""
    start = time.monotonic()
    try:
        profile = case.load_profile()
        jd = case.load_job_description()
        result = run_workflow(
            jd, profile, context=ctx, max_revisions=max_rev, corrections=case.corrections
        )
        scored = score(case, result, profile, max_rev)
    except Exception as exc:  # noqa: BLE001 - an eval records failures instead of stopping
        return {"id": case.id, "error": type(exc).__name__, "seconds": time.monotonic() - start}
    return {
        "id": case.id,
        "seconds": round(time.monotonic() - start, 1),
        "score": scored,
        "result": json.loads(result.model_dump_json()),
    }


def summarise(records: list[dict]) -> str:
    """Markdown table: one row per case, then the pass rate per check."""
    lines = [
        "| Case | Passed | Failed checks | Revisions | Items | Uncited* | Time |",
        "|---|---|---|---|---|---|---|",
    ]
    per_check: dict[str, list[bool]] = {}
    for r in records:
        if "error" in r:
            lines.append(f"| {r['id']} | error: {r['error']} | | | | | {r['seconds']:.0f} s |")
            continue
        s = r["score"]
        failed = [k for k, v in s["checks"].items() if not v]
        for k, v in s["checks"].items():
            # gap_1:docker, gap_2:... -> "gap_checks"; covers:docker -> "covers"
            group = "gap_checks" if k.startswith("gap_") else k.split(":")[0]
            per_check.setdefault(group, []).append(v)
        c = s["counts"]
        lines.append(
            f"| {r['id']} | {'yes' if s['passed'] else 'no'} | {', '.join(failed) or '-'} | "
            f"{c['revisions']} | {c['roadmap_items']} | {c['uncited_items_with_evidence']} | "
            f"{r.get('seconds', 0):.0f} s |"
        )
    lines += ["", "*items with no source although the knowledge base had evidence for them", ""]
    lines += ["| Check | Pass rate |", "|---|---|"]
    lines += [f"| {k} | {sum(v)}/{len(v)} |" for k, v in per_check.items()]
    return "\n".join(lines)


def main() -> None:
    """Run (or re-score) the cases, print the summary and save the records."""
    from gradpath.providers import get_chat_model
    from gradpath.retrieval import get_retrieval_service
    from gradpath.tracing import configure_tracing, flush

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", metavar="CASE_ID")
    parser.add_argument("--rescore", type=Path, help="re-score a saved run; no model calls")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    cases = {c.id: c for c in load_cases()}
    settings = get_settings()
    if args.rescore:
        saved = json.loads(args.rescore.read_text(encoding="utf-8"))
        for r in saved["cases"]:
            if "result" in r and r["id"] in cases:
                case = cases[r["id"]]
                result = CareerPrepResult.model_validate(r["result"])
                r["score"] = score(case, result, case.load_profile(), saved["max_revisions"])
        print(summarise(saved["cases"]))
        return

    selected = [cases[i] for i in args.only] if args.only else list(cases.values())
    configure_tracing(settings)
    retrieval = get_retrieval_service()
    ctx = WorkflowContext(
        retrieval=retrieval, fast_llm=get_chat_model("fast"), smart_llm=get_chat_model("smart")
    )
    records: list[dict] = []
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"workflow-eval-{datetime.now(UTC):%Y%m%d-%H%M%S}.json"
    out = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "provider": settings.llm_provider,
        "model_fast": settings.model_fast,
        "model_smart": settings.model_smart,
        "max_revisions": settings.workflow_max_revisions,
        "cases_file": DEFAULT_CASES.name,
        "cases": records,
    }
    try:
        for case in selected:
            print(f"running {case.id} ...", flush=True)
            records.append(run_case(case, ctx, settings.workflow_max_revisions))
            # Saved after every case: an interrupt never loses the paid runs before it.
            path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    finally:
        retrieval.store.client.close()
        flush()
    print(summarise(records))
    print(f"\nsaved: {path}")


if __name__ == "__main__":
    main()

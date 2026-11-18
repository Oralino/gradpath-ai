"""Run the career-preparation workflow from the terminal.

Run from `backend/` (stop the API server first: local Qdrant allows one process):
  uv run python -m gradpath.workflows.cli ../evaluation/job_descriptions/sample_backend_new_grad.txt
      ../evaluation/profiles/sample_new_grad.json [--correction "..."] [--json] [--out FILE]
Uses LLM_PROVIDER and WORKFLOW_MAX_REVISIONS from .env. Use only the sample profile or your own
data from `private/`; with tracing on, prompts (including the profile) go to LangSmith.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from gradpath.config import REPO_ROOT, get_settings
from gradpath.providers import get_chat_model
from gradpath.retrieval import get_retrieval_service
from gradpath.tracing import configure_tracing, flush
from gradpath.workflows import CareerPrepResult, UserProfile, WorkflowContext, run_workflow

STATUS = {
    "demonstrated": "✓",
    "partially_evidenced": "~",
    "not_yet_evidenced": "✗",
    "not_applicable": "–",
}


def report(result: CareerPrepResult, seconds: float) -> str:
    """Readable summary of a result: status, gaps, roadmap, questions, open issues."""
    lines = [f"\nstatus: {result.status}  revisions: {result.revisions_used}  time: {seconds:.0f}s"]
    if result.job:
        lines.append(f"\n{result.job.title} ({result.job.seniority})")
    lines.append("\nGaps:")
    for g in result.gaps:
        facts = f"  [{', '.join(g.profile_evidence_ids)}]" if g.profile_evidence_ids else ""
        lines.append(f"{STATUS[g.status]} [{g.importance}] {g.skill} ({g.confidence}){facts}")
        lines.append(f"    {g.reasoning}")
    lines.append("\nRoadmap:")
    for i in result.roadmap:
        deps = f"  after {i.depends_on}" if i.depends_on else ""
        lines.append(f"{i.order}. {i.topic}  (~{i.effort_hours_estimate:g} h, estimate){deps}")
        lines.append(f"    why: {i.why_it_matters}")
        lines.append(f"    exercise: {i.exercise}")
        lines.append(f"    done when: {i.completion_criteria}")
        for c in i.resources:
            lines.append(f"    - {c.title} > {c.section}" if c.section else f"    - {c.title}")
        if not i.resources:
            lines.append("    - (no source in the knowledge base)")
    lines.append("\nInterview questions:")
    lines += [f"- [{q.requirement_id}] {q.question}" for q in result.interview_questions]
    if result.unresolved_issues:
        lines.append("\nOpen issues:")
        lines += [f"- [{i.severity}] {i.message}" for i in result.unresolved_issues]
    if result.fallback:
        fb = result.fallback
        lines.append(f"\nStopped early ({fb.reason}, stage: {fb.failed_stage or '-'})")
        lines.append(f"    {fb.message}")
        lines.append(f"    finished: {', '.join(fb.completed_stages) or '-'}")
        lines.append(f"    not finished: {', '.join(fb.not_completed) or '-'}")
        for s in fb.study_sources:
            lines.append(f"    {s.skill}:")
            lines += [f"      - {c.title} > {c.section}" for c in s.citations]
        if fb.answer:
            lines.append(f"    answer ({fb.answer.status}): {fb.answer.answer}")
    if result.errors:
        lines.append("\nErrors:")
        lines += [f"- {e}" for e in result.errors]
    lines.append(f"\nnodes: {' -> '.join(result.node_log)}")
    lines.append("✓ demonstrated   ~ partially evidenced   ✗ not yet evidenced   – eligibility")
    return "\n".join(lines)


def out_allowed(path: Path, profile: UserProfile) -> bool:
    """`--out` may write a real profile's results only under `private/` (gitignored); anywhere
    else (e.g. `evaluation/results/`, `demo_runs/`, which are committed) needs a sample profile,
    whose id starts with "sample-"."""
    if (profile.profile_id or "").startswith("sample-"):
        return True
    return path.resolve().is_relative_to((REPO_ROOT / "private").resolve())


def main() -> None:
    """Parse arguments, run the workflow once with real services, print and optionally save."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_description", type=Path)
    parser.add_argument("profile", type=Path, help="profile JSON (the structured form)")
    parser.add_argument("--correction", action="append", default=[], help="repeatable")
    parser.add_argument("--json", action="store_true", help="print the full JSON result")
    parser.add_argument("--out", type=Path, help="also save the JSON result here")
    args = parser.parse_args()
    # Windows consoles and redirects default to cp1252, which can't print the report's markers
    # (or model text): without this, printing could fail after a paid run.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    jd = args.job_description.read_text(encoding="utf-8")
    profile = UserProfile.model_validate(json.loads(args.profile.read_text(encoding="utf-8")))
    if args.out and not out_allowed(args.out, profile):
        raise SystemExit(
            "--out: only a sample profile (profile_id 'sample-...') may be saved outside private/"
        )
    settings = get_settings()
    status = configure_tracing(settings)
    print(f"tracing: {'on' if status.enabled else 'off'} ({status.reason})", file=sys.stderr)
    print(f"provider: {settings.llm_provider}, max revisions: {settings.workflow_max_revisions}",
          file=sys.stderr)  # fmt: skip
    retrieval = get_retrieval_service()
    start = time.monotonic()
    try:
        ctx = WorkflowContext(
            retrieval=retrieval,
            fast_llm=get_chat_model("fast"),
            smart_llm=get_chat_model("smart"),
        )
        result = run_workflow(
            jd,
            profile,
            context=ctx,
            max_revisions=settings.workflow_max_revisions,
            corrections=args.correction,
            time_budget_s=settings.workflow_time_budget_s,
        )
    finally:
        retrieval.store.client.close()
        flush()
    seconds = time.monotonic() - start

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        print(f"saved: {args.out}", file=sys.stderr)
    print(result.model_dump_json(indent=2) if args.json else report(result, seconds))


if __name__ == "__main__":
    main()

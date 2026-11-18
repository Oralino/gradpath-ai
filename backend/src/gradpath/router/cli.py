"""Route one message from the terminal and run the chosen path (what `POST /api/assist` does).

Run from `backend/` (stop the API server first: local Qdrant allows one process):
  uv run python -m gradpath.router.cli "What is MVCC?"
  uv run python -m gradpath.router.cli "Make me a roadmap for this job" \\
      --job ../evaluation/job_descriptions/sample_backend_new_grad.txt \\
      --profile ../evaluation/profiles/sample_new_grad.json [--route-only] [--json]
`--route-only` stops after the routing decision (one Haiku call at most). Uses LLM_PROVIDER from
.env; use the sample profile or your own data from `private/`. A full run writes one line to the
route log; `--route-only` writes none.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from gradpath.config import get_settings
from gradpath.providers import get_chat_model
from gradpath.retrieval import get_retrieval_service
from gradpath.router import route_log
from gradpath.router.assist import AssistRequest, AssistResponse, decide, respond, route_log_entry
from gradpath.tracing import configure_tracing, flush
from gradpath.workflows import UserProfile
from gradpath.workflows.cli import report


def show(response: AssistResponse, seconds: float) -> str:
    """Readable summary: the decision, then the answer, the workflow report or the message."""
    d = response.decision
    missing = f", missing: {', '.join(d.missing)}" if d.missing else ""
    lines = [
        f"route: {d.route} / {d.action} (kind: {d.kind}, decided by: {d.decided_by}{missing})",
        f"reason: {d.reason}",
    ]
    if response.message:
        lines.append(f"\n{response.message}")
    if response.answer:
        a = response.answer
        lines.append(f"\n[{a.status}] {a.answer}")
        lines += [f"  - {c.title} > {c.section}" for c in a.citations]
    if response.result:
        lines.append(report(response.result, seconds))
    return "\n".join(lines)


def main() -> None:
    """Parse arguments, route once with real services, run the path unless --route-only."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message")
    parser.add_argument("--job", type=Path, help="job description text file")
    parser.add_argument("--profile", type=Path, help="profile JSON (the structured form)")
    parser.add_argument("--correction", action="append", default=[], help="repeatable")
    parser.add_argument("--route-only", action="store_true", help="stop after routing")
    parser.add_argument("--json", action="store_true", help="print the full JSON response")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    req = AssistRequest(
        message=args.message,
        job_description=args.job.read_text(encoding="utf-8") if args.job else None,
        profile=(
            UserProfile.model_validate(json.loads(args.profile.read_text(encoding="utf-8")))
            if args.profile
            else None
        ),
        corrections=args.correction,
    )
    settings = get_settings()
    status = configure_tracing(settings)
    print(f"tracing: {'on' if status.enabled else 'off'} ({status.reason})", file=sys.stderr)
    fast = get_chat_model("fast")
    start = time.monotonic()
    decision = None
    response = None
    try:
        decision = decide(req, fast)
        if args.route_only:
            print(decision.model_dump_json(indent=2))
            return
        retrieval = get_retrieval_service()
        try:
            response = respond(
                req, decision, retrieval=retrieval, fast_llm=fast,
                smart_llm=get_chat_model("smart"), settings=settings,
            )  # fmt: skip
        finally:
            retrieval.store.client.close()
    finally:
        if not args.route_only:
            route_log.record(
                route_log.log_path(settings),
                route_log_entry(decision, response, time.monotonic() - start),
            )
        flush()
    seconds = time.monotonic() - start
    print(response.model_dump_json(indent=2) if args.json else show(response, seconds))


if __name__ == "__main__":
    main()

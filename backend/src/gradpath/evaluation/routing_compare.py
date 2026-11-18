"""Adaptive routing vs always-RAG vs always-workflow on a few labelled requests (T-006, spec 2A).

Run from `backend/` (stop the API first; local Qdrant allows one process):
    uv run python -m gradpath.evaluation.routing_compare [--only rt-001 ...]

Owner decision 2026-11-18: 4 requests only (each workflow run is ~100 s of Pro-plan use).
Each path runs at most once per request and is reused by every strategy that takes it (adaptive
= the path the router picked, plus its routing call), so the cost is 4 RAG answers, the workflow
runs, and the routing calls. Per strategy and request it records time, model calls, the outcome,
and whether the outcome serves the labelled need, decided in code:
- a request labelled for RAG is served by a RAG answer with at least one citation (or an honest
  "not covered"); a workflow run does not answer the question asked;
- a request labelled for the workflow is served by a complete workflow result; a generic RAG
  answer is not personalised, and a request that can't run (missing inputs) is not served.
"""

import argparse
import json
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from gradpath.config import get_settings
from gradpath.evaluation.routing_eval import RESULTS_DIR, RoutingCase, load_cases
from gradpath.evaluation.workflow_eval import _repo_file
from gradpath.workflows import UserProfile

COMPARE_IDS = ("rt-001", "rt-017", "rt-011", "rt-016")  # simple, simple + inputs, 2 complex
STRATEGIES = ("adaptive", "always_rag", "always_workflow")


class CallCounter(BaseCallbackHandler):
    """Counts chat-model calls through the two model instances it is attached to (`callbacks`);
    a retried call counts twice, and work inside the Claude Code CLI is not visible here."""

    def __init__(self) -> None:
        self.calls = 0

    def on_chat_model_start(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1

    def on_llm_start(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1


def load_inputs(case: RoutingCase) -> tuple[str | None, UserProfile | None]:
    """The case's attached job description and sample profile (results are committed)."""
    jd = _repo_file(case.job_description).read_text("utf-8") if case.job_description else None
    profile = None
    if case.profile:
        profile = UserProfile.model_validate(
            json.loads(_repo_file(case.profile).read_text("utf-8"))
        )
        if not (profile.profile_id or "").startswith("sample-"):
            raise ValueError(f"{case.id}: comparison cases must use a sample- profile")
    return jd, profile


def served(case: RoutingCase, path: str, outcome: dict) -> bool:
    """Does this outcome meet the labelled need? (See the module docstring.)"""
    if case.expected_route == "traditional_rag":
        return path == "rag" and (
            outcome.get("citations", 0) > 0 or outcome.get("status") == "insufficient_evidence"
        )
    if case.expected_action != "run":
        return False  # this script compares runnable requests only
    return path == "workflow" and outcome.get("status") in ("complete", "complete_with_limitations")


def compare_case(
    case: RoutingCase,
    route: Callable[[RoutingCase], tuple[str, float, int]],
    run_rag: Callable[[RoutingCase], dict],
    run_workflow: Callable[[RoutingCase], dict] | None,
) -> dict:
    """All three strategies for one case. `route` returns (path, seconds, model calls) where
    path is "rag", "workflow" or "none"; `run_rag` / `run_workflow` return an outcome dict with
    seconds and calls and are each called at most once. `run_workflow` is None when the case
    lacks an input (the workflow can't run)."""
    cache: dict[str, dict] = {}

    def path_outcome(path: str) -> dict:
        if path == "none":
            return {"status": "not_run", "seconds": 0.0, "calls": 0}
        if path not in cache:
            fn = run_rag if path == "rag" else run_workflow
            cache[path] = (
                {"status": "not_run: missing input", "seconds": 0.0, "calls": 0}
                if fn is None
                else fn(case)
            )
        return cache[path]

    path, route_secs, route_calls = route(case)
    rows = {}
    for strategy, chosen in (
        ("adaptive", path),
        ("always_rag", "rag"),
        ("always_workflow", "workflow"),
    ):
        o = path_outcome(chosen)
        extra_s, extra_c = (route_secs, route_calls) if strategy == "adaptive" else (0.0, 0)
        rows[strategy] = {
            "path": chosen,
            "outcome": {k: v for k, v in o.items() if k not in ("seconds", "calls")},
            "seconds": round(o["seconds"] + extra_s, 1),
            "model_calls": o["calls"] + extra_c,
            "served": served(case, chosen, o),
        }
    return {"id": case.id, "expected": case.expected_route, "strategies": rows}


def summarise(records: list[dict]) -> str:
    """Markdown: per request, each strategy's served / time / calls; then totals."""
    lines = ["| Request | Expected | " + " | ".join(STRATEGIES) + " |", "|---|---|---|---|---|"]
    totals = {s: [0, 0.0, 0] for s in STRATEGIES}
    for r in records:
        if "error" in r:
            lines.append(f"| {r['id']} | error: {r['error']} | | | |")
            continue
        cells = []
        for s in STRATEGIES:
            x = r["strategies"][s]
            mark = "✓" if x["served"] else "✗"
            cells.append(f"{mark} {x['seconds']:.0f} s, {x['model_calls']} calls")
            totals[s][0] += x["served"]
            totals[s][1] += x["seconds"]
            totals[s][2] += x["model_calls"]
        lines.append(f"| {r['id']} | {r['expected']} | " + " | ".join(cells) + " |")
    lines.append(
        "| **Total** | | "
        + " | ".join(
            f"{t[0]}/{len(records)} served, {t[1]:.0f} s, {t[2]} calls" for t in totals.values()
        )
        + " |"
    )
    return "\n".join(lines)


def main() -> None:
    """Run the comparison with real services; print the table and save the records."""
    from gradpath.providers import get_chat_model
    from gradpath.rag.answer import answer_question
    from gradpath.retrieval import get_retrieval_service
    from gradpath.router import route_request
    from gradpath.tracing import configure_tracing, flush
    from gradpath.workflows import WorkflowContext
    from gradpath.workflows import run_workflow as run_graph

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", metavar="CASE_ID")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    cases = {c.id: c for c in load_cases()}
    selected = [cases[i] for i in (args.only or COMPARE_IDS)]
    settings = get_settings()
    configure_tracing(settings)
    counter = CallCounter()
    fast, smart = get_chat_model("fast"), get_chat_model("smart")
    fast.callbacks = [counter]
    smart.callbacks = [counter]
    retrieval = get_retrieval_service()

    def timed(fn: Callable[[], dict]) -> dict:
        before, start = counter.calls, time.monotonic()
        out = fn()
        return {**out, "seconds": time.monotonic() - start, "calls": counter.calls - before}

    def route(case: RoutingCase) -> tuple[str, float, int]:
        before, start = counter.calls, time.monotonic()
        d = route_request(case.request(), fast)
        path = (
            "none" if d.action != "run" else ("rag" if d.route == "traditional_rag" else "workflow")
        )
        return path, time.monotonic() - start, counter.calls - before

    def rag(case: RoutingCase) -> dict:
        def go() -> dict:
            a = answer_question(case.message, retrieval, smart)
            return {"status": a.status, "citations": len(a.citations)}

        return timed(go)

    def workflow_for(case: RoutingCase) -> Callable[[RoutingCase], dict] | None:
        jd, profile = load_inputs(case)
        if jd is None or profile is None:
            return None

        def go_case(_: RoutingCase) -> dict:
            def go() -> dict:
                res = run_graph(
                    jd, profile,
                    context=WorkflowContext(retrieval=retrieval, fast_llm=fast, smart_llm=smart),
                    max_revisions=settings.workflow_max_revisions,
                    time_budget_s=settings.workflow_time_budget_s,
                )  # fmt: skip
                return {"status": res.status, "gaps": len(res.gaps), "items": len(res.roadmap)}

            return timed(go)

        return go_case

    records: list[dict] = []
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"routing-compare-{datetime.now(UTC):%Y%m%d-%H%M%S}.json"
    out = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "provider": settings.llm_provider,
        "model_fast": settings.model_fast,
        "model_smart": settings.model_smart,
        "max_revisions": settings.workflow_max_revisions,
        "cases": records,
    }
    try:
        for case in selected:
            print(f"comparing {case.id} ...", flush=True, file=sys.stderr)
            try:
                records.append(compare_case(case, route, rag, workflow_for(case)))
            except Exception as exc:  # noqa: BLE001 - record the failure, keep the other cases
                records.append({"id": case.id, "error": type(exc).__name__})
            path.write_text(json.dumps(out, indent=2), encoding="utf-8")  # saved after each case
    finally:
        retrieval.store.client.close()
        flush()
    print(summarise(records))
    print(f"\nsaved: {path}")


if __name__ == "__main__":
    main()

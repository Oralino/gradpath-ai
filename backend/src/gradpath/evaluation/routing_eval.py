"""Routing eval (T-006): run the router on the labelled requests and score it in code.

Run from `backend/`:
    uv run python -m gradpath.evaluation.routing_eval --rules-only      # free: rules only
    uv run python -m gradpath.evaluation.routing_eval [--only rt-001 ...] # rules + Haiku
    uv run python -m gradpath.evaluation.routing_eval --rescore ../evaluation/results/<file>.json

A full run makes one Haiku call per case the rules leave open (20 of 30 today), no Voyage call and
no Qdrant access. `--rescore` re-scores saved decisions against the current labels for free.
Metrics follow spec 2A: accuracy, precision and recall for the workflow route, simple requests
over-routed to the workflow, complex requests under-routed to RAG, and the same per decider.
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, ConfigDict

from gradpath.config import REPO_ROOT, get_settings
from gradpath.router import RouteRequest, route_request
from gradpath.router.route import decide
from gradpath.router.rules import rule_kind
from gradpath.router.schemas import Action, Route

DEFAULT_CASES = REPO_ROOT / "evaluation" / "routing_cases.jsonl"
RESULTS_DIR = REPO_ROOT / "evaluation" / "results"
WORKFLOW: Route = "agentic_workflow"


class RoutingCase(BaseModel):
    """One labelled request (evaluation/routing_cases.jsonl, owner-approved 2026-11-18)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    message: str
    job_description: str | None = None  # path relative to the repo root, or null
    profile: str | None = None
    expected_route: Route
    expected_action: Action
    tags: list[str]
    notes: str = ""

    def request(self) -> RouteRequest:
        """What the router sees: the message and whether each input is attached."""
        return RouteRequest(
            message=self.message,
            has_job_description=self.job_description is not None,
            has_profile=self.profile is not None,
        )


def load_cases(path: Path = DEFAULT_CASES) -> list[RoutingCase]:
    """Read the JSONL labels; unknown fields and duplicate ids are errors."""
    cases = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                cases.append(RoutingCase.model_validate_json(line))
            except ValueError as exc:
                raise ValueError(f"{path.name} line {n}: {exc}") from exc
    if len({c.id for c in cases}) != len(cases):
        raise ValueError("duplicate case ids")
    return cases


def run_case(case: RoutingCase, llm: BaseChatModel | None) -> dict:
    """Route one case. With `llm=None` only the rules run; cases they leave open are recorded
    as undecided (no route) instead of calling a model."""
    start = time.monotonic()
    if llm is None:
        hit = rule_kind(case.request())
        if hit is None:
            return {"id": case.id, "decided_by": "undecided", "seconds": 0.0}
        d = decide(hit[0], hit[1], case.request(), "rules")
    else:
        d = route_request(case.request(), llm)
    return {
        "id": case.id,
        "route": d.route,
        "action": d.action,
        "kind": d.kind,
        "decided_by": d.decided_by,
        "seconds": round(time.monotonic() - start, 2),
    }


def _expected(case: RoutingCase) -> tuple[str, str]:
    return case.expected_route, case.expected_action


def _share(num: int, den: int) -> float | None:
    return None if den == 0 else round(num / den, 3)


def metrics(records: list[dict], cases: dict[str, RoutingCase]) -> dict:
    """Spec 2A routing metrics over decided records, scored against the current labels."""
    unknown = sorted({r["id"] for r in records if r["id"] not in cases})
    decided = [r for r in records if r.get("route") and r["id"] in cases]
    exp = {r["id"]: cases[r["id"]] for r in decided}
    right_ids = {r["id"] for r in decided if (r["route"], r["action"]) == _expected(exp[r["id"]])}
    right = [r for r in decided if r["id"] in right_ids]
    route_right = [r for r in decided if r["route"] == exp[r["id"]].expected_route]
    pred_wf = [r for r in decided if r["route"] == WORKFLOW]
    true_wf = [r for r in decided if exp[r["id"]].expected_route == WORKFLOW]
    tp = [r for r in pred_wf if exp[r["id"]].expected_route == WORKFLOW]
    simple = [r for r in decided if exp[r["id"]].expected_route != WORKFLOW]
    by: dict[str, dict] = {}
    for who in ("rules", "model", "default"):
        rs = [r for r in decided if r["decided_by"] == who]
        ok = sum(r["id"] in right_ids for r in rs)
        by[who] = {"cases": len(rs), "correct": ok}
    tags: dict[str, list[bool]] = {}
    for r in decided:
        for t in exp[r["id"]].tags:
            tags.setdefault(t, []).append(r["id"] in right_ids)
    model_secs = [r["seconds"] for r in decided if r["decided_by"] == "model"]
    return {
        "cases": len(records),
        "decided": len(decided),
        "undecided": sum(r.get("decided_by") == "undecided" for r in records),
        "unknown_ids": unknown,  # records whose case is no longer in the labels
        "accuracy": _share(len(right), len(decided)),  # route and action both right
        "route_accuracy": _share(len(route_right), len(decided)),
        "workflow_precision": _share(len(tp), len(pred_wf)),
        "workflow_recall": _share(len(tp), len(true_wf)),
        "over_routed": _share(sum(r["route"] == WORKFLOW for r in simple), len(simple)),
        "under_routed": _share(sum(r["route"] != WORKFLOW for r in true_wf), len(true_wf)),
        "by_decider": by,
        "by_tag": {t: f"{sum(v)}/{len(v)}" for t, v in sorted(tags.items())},
        "model_seconds_mean": round(sum(model_secs) / len(model_secs), 2) if model_secs else None,
        "wrong": [r["id"] for r in decided if r["id"] not in right_ids],
    }


def summarise(records: list[dict], cases: dict[str, RoutingCase]) -> str:
    """Markdown: the headline metrics, then one row per wrong case."""
    m = metrics(records, cases)
    rows = [
        "| Metric | Value |",
        "|---|---|",
        f"| Decided / undecided / unknown ids | {m['decided']} / {m['undecided']} / "
        f"{len(m['unknown_ids'])} |",
        f"| Accuracy (route + action) | {m['accuracy']} |",
        f"| Route accuracy | {m['route_accuracy']} |",
        f"| Workflow precision / recall | {m['workflow_precision']} / {m['workflow_recall']} |",
        f"| Simple over-routed / complex under-routed | {m['over_routed']} / {m['under_routed']} |",
    ]
    rows += [
        f"| Decided by {k} | {v['correct']}/{v['cases']} correct |"
        for k, v in m["by_decider"].items()
        if v["cases"]
    ]
    rows.append(f"| Mean routing call (model) | {m['model_seconds_mean']} s |")
    rows += ["", "| Tag | Correct |", "|---|---|"]
    rows += [f"| {t} | {v} |" for t, v in m["by_tag"].items()]
    if m["wrong"]:
        rows += ["", "| Wrong case | Expected | Got | Decided by |", "|---|---|---|---|"]
        recs = {r["id"]: r for r in records}
        for i in m["wrong"]:
            c, r = cases[i], recs[i]
            rows.append(
                f"| {i} | {c.expected_route} / {c.expected_action} | "
                f"{r['route']} / {r['action']} ({r['kind']}) | {r['decided_by']} |"
            )
    return "\n".join(rows).replace("None", "n/a")  # metrics are None when nothing was decided


def main() -> None:
    """Run (rules only, or rules + model) or re-score; print the summary and save the records."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", metavar="CASE_ID")
    parser.add_argument("--rules-only", action="store_true", help="no model calls")
    parser.add_argument("--rescore", type=Path, help="re-score a saved run; no model calls")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    cases = {c.id: c for c in load_cases()}
    if args.rescore:
        saved = json.loads(args.rescore.read_text(encoding="utf-8"))
        print(summarise(saved["cases"], cases))
        return

    settings = get_settings()
    llm = None
    if not args.rules_only:
        from gradpath.providers import get_chat_model
        from gradpath.tracing import configure_tracing, flush

        configure_tracing(settings)
        llm = get_chat_model("fast")
    ids = list(dict.fromkeys(args.only)) if args.only else list(cases)  # no duplicates
    selected = [cases[i] for i in ids]
    records: list[dict] = []
    stamp = f"{datetime.now(UTC):%Y%m%d-%H%M%S}"
    path = RESULTS_DIR / f"routing-{'rules-' if llm is None else ''}{stamp}.json"
    out = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "rules_only" if llm is None else "rules_and_model",
        "provider": None if llm is None else settings.llm_provider,
        "model_fast": None if llm is None else settings.model_fast,
        "cases_file": DEFAULT_CASES.name,
        "cases": records,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        for case in selected:
            print(f"routing {case.id} ...", flush=True, file=sys.stderr)
            records.append(run_case(case, llm))
            path.write_text(json.dumps(out, indent=2), encoding="utf-8")  # saved after each case
    finally:
        if llm is not None:
            flush()
    out["metrics"] = metrics(records, cases)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(summarise(records, cases))
    print(f"\nsaved: {path}")


if __name__ == "__main__":
    main()

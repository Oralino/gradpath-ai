"""Answer eval (T-018 step 10): run the traditional RAG path on labelled questions, score in code.

Run from `backend/` (stop the API first; local Qdrant allows one process):
    uv run python -m gradpath.evaluation.answer_eval [--only a-001 ...] [--no-grounding]
    uv run python -m gradpath.evaluation.answer_eval --rescore ../evaluation/results/<file>.json

Each case makes one Voyage query request (paced by the throttled embeddings behind
`get_retrieval_service`: 3 per minute), one smart-tier answer call and, unless `--no-grounding`,
one fast-tier grounding call (`grounding.py`). `--rescore` re-scores a saved run against the
current cases with no model or Voyage call.
"""

import argparse
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gradpath.config import REPO_ROOT, get_settings
from gradpath.evaluation.grounding import GroundingResult, check_grounding, load_chunks
from gradpath.rag.answer import ChatAnswer, answer_question

DEFAULT_CASES = REPO_ROOT / "evaluation" / "answer_cases.jsonl"
RESULTS_DIR = REPO_ROOT / "evaluation" / "results"
REFUSE_OUTCOMES = ("refused", "grounded partial", "invented", "not checked")


class AnswerCase(BaseModel):
    """One labelled question (evaluation/answer_cases.jsonl)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    question_id: str
    question: str
    expect: Literal["answer", "refuse"]
    must_contain: list[list[str]] = Field(default_factory=list)
    source: str = ""


def load_cases(path: Path = DEFAULT_CASES) -> list[AnswerCase]:
    """Read the JSONL cases; unknown fields and duplicate ids are errors."""
    cases = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                cases.append(AnswerCase.model_validate_json(line))
            except ValueError as exc:
                raise ValueError(f"{path.name} line {n}: {exc}") from exc
    if len({c.id for c in cases}) != len(cases):
        raise ValueError("duplicate case ids")
    return cases


def phrase_matches(phrase: str, text: str) -> bool:
    """Case-insensitive, whitespace-normalised match on word boundaries ("put" is not in
    "output"; "pytest.raises" and "retry-after" match literally). Used by `group_matches`."""
    words = _straight(phrase).lower().split()
    if not words:
        return False
    pattern = r"(?<!\w)" + r"\s+".join(re.escape(w) for w in words) + r"(?!\w)"
    return re.search(pattern, " ".join(_straight(text).lower().split())) is not None


def _straight(text: str) -> str:
    """Curly apostrophes and quotes as straight ones, so "don't" matches "don’t"."""
    return text.translate({0x2019: "'", 0x2018: "'", 0x201C: '"', 0x201D: '"'})


def group_matches(group: list[str], text: str) -> bool:
    """A group passes when any of its phrasings appears in `text`."""
    return any(phrase_matches(p, text) for p in group)


def score_case(case: AnswerCase, answer: ChatAnswer, grounding: GroundingResult | None) -> dict:
    """Pure scoring of one result (used by `run_case`'s callers and by `--rescore`). Facts are
    looked up in `answer.answer` only, never in `not_covered`."""
    missed = [g for g in case.must_contain if not group_matches(g, answer.answer)]
    facts = {"matched": len(case.must_contain) - len(missed), "total": len(case.must_contain)}
    claims = grounding.claims if grounding else []
    sup = {"supported": sum(c.supported for c in claims), "total": len(claims)}
    answered = answer.status in ("answered", "partial")
    if case.expect == "answer":
        passed = answered and bool(answer.citations) and not missed
        outcome = "answered" if passed else "failed"
    elif not answered:
        passed, outcome = True, "refused"
    elif grounding is None or not claims:
        # No judge run, or a judge that found no claims in a shown answer: nothing was checked.
        passed, outcome = False, "not checked"
    elif all(c.supported for c in claims):
        passed, outcome = True, "grounded partial"
    else:
        passed, outcome = False, "invented"
    return {
        "passed": passed,
        "outcome": outcome,
        "facts": facts,
        "missed_groups": missed,
        "claims": sup,
    }


def run_case(case: AnswerCase, retrieval, answer_llm, judge_llm, grounding_on: bool = True) -> dict:
    """Run one case with real services and keep everything raw. A failure is recorded by exception
    type only (a message can quote a model reply), so one bad case doesn't stop the run."""
    start = time.monotonic()
    try:
        answer = answer_question(case.question, retrieval, answer_llm)
        answer_seconds = round(time.monotonic() - start, 2)
        grounding, grounding_seconds = None, None
        if grounding_on and answer.status != "insufficient_evidence":
            g_start = time.monotonic()
            chunks = load_chunks([c.chunk_id for c in answer.citations])
            grounding = check_grounding(answer, chunks, judge_llm)
            grounding_seconds = round(time.monotonic() - g_start, 2)
    except Exception as exc:  # noqa: BLE001 - an eval records failures instead of stopping
        return {"id": case.id, "error": type(exc).__name__, "seconds": time.monotonic() - start}
    return {
        "id": case.id,
        "seconds": answer_seconds,
        "grounding_seconds": grounding_seconds,
        "answer": json.loads(answer.model_dump_json()),
        "grounding": json.loads(grounding.model_dump_json()) if grounding else None,
    }


def rescore(records: list[dict], cases: dict[str, AnswerCase]) -> list[dict]:
    """Attach a fresh `score` to every record whose case still exists (no model calls). Called by
    `main` for both a live run and `--rescore`."""
    for r in records:
        if "answer" in r and r["id"] in cases:
            g = r.get("grounding")
            r["score"] = score_case(
                cases[r["id"]],
                ChatAnswer.model_validate(r["answer"]),
                GroundingResult.model_validate(g) if g else None,
            )
    return records


def _pct(num: int, den: int) -> str:
    return "n/a" if den == 0 else f"{num}/{den} ({num / den:.0%})"


def summarise(records: list[dict], cases: dict[str, AnswerCase]) -> str:
    """Markdown: one row per case, then the totals."""
    lines = [
        "| Case | Expect | Status | Facts | Citations | Supported claims | Outcome | Pass |",
        "|---|---|---|---|---|---|---|---|",
    ]
    scored = [r for r in records if "score" in r]
    for r in records:
        if "score" not in r:
            lines.append(f"| {r['id']} | | error: {r.get('error', 'not scored')} | | | | | no |")
            continue
        s, a = r["score"], r["answer"]
        c = s["claims"]
        claims = "n/a" if r.get("grounding") is None else f"{c['supported']}/{c['total']}"
        lines.append(
            f"| {r['id']} | {cases[r['id']].expect} | {a['status']} | "
            f"{s['facts']['matched']}/{s['facts']['total']} | {len(a['citations'])} | {claims} | "
            f"{s['outcome']} | {'yes' if s['passed'] else 'no'} |"
        )
    ans = [r for r in scored if cases[r["id"]].expect == "answer"]
    ref = [r for r in scored if cases[r["id"]].expect == "refuse"]
    outcomes = {o: sum(r["score"]["outcome"] == o for r in ref) for o in REFUSE_OUTCOMES}
    all_claims = sum(r["score"]["claims"]["total"] for r in scored)
    sup_claims = sum(r["score"]["claims"]["supported"] for r in scored)
    secs = [r["seconds"] + (r.get("grounding_seconds") or 0) for r in scored]
    latency = f"{sum(secs) / len(secs):.1f} s" if secs else "n/a"
    lines += [
        "",
        "| Total | Value |",
        "|---|---|",
        f"| Answer cases passed | {_pct(sum(r['score']['passed'] for r in ans), len(ans))} |",
        f"| Refuse cases passed | {_pct(sum(r['score']['passed'] for r in ref), len(ref))} |",
        "| Refuse outcomes | " + ", ".join(f"{k} {v}" for k, v in outcomes.items()) + " |",
        f"| Supported claims (all answers) | {_pct(sup_claims, all_claims)} |",
        f"| Mean latency | {latency} |",
    ]
    return "\n".join(lines)


def main() -> None:
    """Run (or re-score) the cases, print the summary and save the records."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", metavar="CASE_ID")
    parser.add_argument("--no-grounding", action="store_true", help="skip the grounding calls")
    parser.add_argument("--rescore", type=Path, help="re-score a saved run; no model calls")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    cases = {c.id: c for c in load_cases()}
    if args.rescore:
        saved = json.loads(args.rescore.read_text(encoding="utf-8"))
        print(summarise(rescore(saved["cases"], cases), cases))
        return

    from gradpath.providers import get_chat_model
    from gradpath.retrieval import get_retrieval_service
    from gradpath.tracing import configure_tracing, flush

    settings = get_settings()
    ids = list(dict.fromkeys(args.only)) if args.only else list(cases)
    unknown = [i for i in ids if i not in cases]
    if unknown:
        parser.error(f"unknown case ids: {', '.join(unknown)}")
    selected = [cases[i] for i in ids]
    configure_tracing(settings)
    retrieval = get_retrieval_service()
    answer_llm, judge_llm = get_chat_model("smart"), get_chat_model("fast")
    records: list[dict] = []
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"answer-eval-{datetime.now(UTC):%Y%m%d-%H%M%S}.json"
    out = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "provider": settings.llm_provider,
        "model_smart": settings.model_smart,
        "model_fast": settings.model_fast,
        "grounding": not args.no_grounding,
        "cases_file": DEFAULT_CASES.name,
        "cases": records,
    }
    try:
        for case in selected:
            print(f"answering {case.id} ...", flush=True, file=sys.stderr)
            records.append(run_case(case, retrieval, answer_llm, judge_llm, not args.no_grounding))
            path.write_text(json.dumps(out, indent=2), encoding="utf-8")  # saved after each case
    finally:
        retrieval.store.client.close()
        flush()
    print(summarise(rescore(records, cases), cases))
    print(f"\nsaved: {path}")


if __name__ == "__main__":
    main()

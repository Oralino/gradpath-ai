"""Retrieval eval runner: labelled questions -> Recall@K, Precision@K, MRR, abstention, latency.

Run from `backend/` (stop the API first; local Qdrant allows one process):
    uv run python -m gradpath.evaluation.retrieval_eval [--k 1,3,5,10] [--max-per-document N]

All questions are embedded in one batched Voyage call (`RetrievalService.search_many`), so a full
run fits the free tier. Ranking is scored on the raw top-K (no threshold), so it compares search
methods fairly; the threshold is then judged separately, offline, from each question's best score.
"""

import argparse
import hashlib
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from gradpath.config import REPO_ROOT, get_settings
from gradpath.evaluation.dataset import DEFAULT_DATASET, Question, load_questions
from gradpath.evaluation.metrics import is_relevant, precision_at_k, recall_at_k, reciprocal_rank
from gradpath.retrieval import Evidence, RetrievalService, get_retrieval_service

RESULTS_DIR = REPO_ROOT / "evaluation" / "results"
DEFAULT_KS = (1, 3, 5, 10)
SWEEP = tuple(round(0.30 + 0.05 * i, 2) for i in range(7))  # 0.30 .. 0.60


class RankedChunk(BaseModel):
    chunk_id: str
    score: float
    relevant: bool


class QuestionResult(BaseModel):
    id: str
    question: str
    covered: bool
    tags: list[str]
    best_score: float | None
    first_relevant_rank: int | None = None
    recall: dict[int, float] = {}
    precision: dict[int, float] = {}
    reciprocal_rank: dict[int, float] = {}
    recall_after_threshold: dict[int, float] = {}
    ranked: list[RankedChunk]


class ThresholdRow(BaseModel):
    threshold: float
    covered_kept: float  # covered questions whose best score clears the threshold
    uncovered_rejected: float  # uncovered questions correctly left `insufficient`


class Summary(BaseModel):
    covered: int
    uncovered: int
    recall: dict[int, float]
    precision: dict[int, float]
    mrr: dict[int, float]
    recall_after_threshold: dict[int, float]
    threshold: float
    covered_kept: float
    uncovered_rejected: float
    lowest_covered_best: float | None
    highest_uncovered_best: float | None
    recall_by_tag: dict[str, float]  # at the report K
    embed_seconds: float  # one batched call for all questions; includes any rate-limit wait
    search_ms_per_question: float  # vector search only (local Qdrant)


class EvalReport(BaseModel):
    run_at: str
    config: dict[str, str | int | float | None]
    summary: Summary
    threshold_sweep: list[ThresholdRow]
    questions: list[QuestionResult]


def score_question(
    q: Question, ranked: list[Evidence], ks: tuple[int, ...], threshold: float
) -> QuestionResult:
    """Metrics for one question at every K; uncovered questions only get their best score."""
    best = ranked[0].score if ranked else None
    result = QuestionResult(
        id=q.id,
        question=q.question,
        covered=q.covered,
        tags=q.tags,
        best_score=best,
        ranked=[
            RankedChunk(
                chunk_id=c.chunk_id, score=round(c.score, 4), relevant=is_relevant(c, q.relevant)
            )
            for c in ranked
        ],
    )
    if not q.covered:
        return result
    kept = [c for c in ranked if c.score >= threshold]  # what production search would return
    for k in ks:
        result.recall[k] = recall_at_k(ranked, q.relevant, k)
        result.precision[k] = precision_at_k(ranked, q.relevant, k)
        result.reciprocal_rank[k] = reciprocal_rank(ranked, q.relevant, k)
        result.recall_after_threshold[k] = recall_at_k(kept, q.relevant, k)
    result.first_relevant_rank = next(
        (i for i, c in enumerate(result.ranked, 1) if c.relevant), None
    )
    return result


def threshold_sweep(results: list[QuestionResult], thresholds=SWEEP) -> list[ThresholdRow]:
    """For each candidate threshold: covered questions kept vs uncovered questions rejected."""
    covered = [r.best_score or 0.0 for r in results if r.covered]
    uncovered = [r.best_score or 0.0 for r in results if not r.covered]
    rows = []
    for t in thresholds:
        rows.append(
            ThresholdRow(
                threshold=t,
                covered_kept=_share(covered, lambda s, t=t: s >= t),
                uncovered_rejected=_share(uncovered, lambda s, t=t: s < t),
            )
        )
    return rows


def _share(values: list[float], test) -> float:
    return sum(1 for v in values if test(v)) / len(values) if values else 0.0


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def summarise(
    results: list[QuestionResult],
    ks: tuple[int, ...],
    report_k: int,
    threshold: float,
    embed_seconds: float,
    search_seconds: float,
) -> Summary:
    """Average the per-question metrics over covered questions; abstention from best scores."""
    cov = [r for r in results if r.covered]
    unc = [r for r in results if not r.covered]
    tags = sorted({t for r in cov for t in r.tags})
    sweep = threshold_sweep(results, (threshold,))[0]
    cov_best = [r.best_score for r in cov if r.best_score is not None]
    unc_best = [r.best_score for r in unc if r.best_score is not None]
    return Summary(
        covered=len(cov),
        uncovered=len(unc),
        recall={k: _mean([r.recall[k] for r in cov]) for k in ks},
        precision={k: _mean([r.precision[k] for r in cov]) for k in ks},
        mrr={k: _mean([r.reciprocal_rank[k] for r in cov]) for k in ks},
        recall_after_threshold={k: _mean([r.recall_after_threshold[k] for r in cov]) for k in ks},
        threshold=threshold,
        covered_kept=sweep.covered_kept,
        uncovered_rejected=sweep.uncovered_rejected,
        lowest_covered_best=min(cov_best) if cov_best else None,
        highest_uncovered_best=max(unc_best) if unc_best else None,
        recall_by_tag={t: _mean([r.recall[report_k] for r in cov if t in r.tags]) for t in tags},
        embed_seconds=round(embed_seconds, 3),
        search_ms_per_question=round(1000 * search_seconds / len(results), 1) if results else 0.0,
    )


def run_eval(
    service: RetrievalService,
    questions: list[Question],
    *,
    ks: tuple[int, ...] = DEFAULT_KS,
    report_k: int = 5,
    max_per_document: int | None = None,
) -> tuple[Summary, list[ThresholdRow], list[QuestionResult]]:
    """Embed every question in one batch, search each, and score the results (timed apart).

    The service's threshold is lifted to -1 for the search so the raw ranking is visible, then
    restored; the original value is the threshold the abstention numbers are judged against.
    Not safe on a service shared with live API requests: use a service built for the run.
    """
    if not questions:
        raise ValueError("no questions to evaluate")
    if not ks or min(ks) < 1:
        raise ValueError(f"every K must be a positive integer, got {ks}")
    if report_k not in ks:
        raise ValueError(f"report_k {report_k} must be one of {ks}")
    threshold = service.min_score
    service.min_score = -1.0
    queries = [q.question for q in questions]
    try:
        start = time.perf_counter()
        vectors = service.embed_many(queries)
        embed_seconds = time.perf_counter() - start
        start = time.perf_counter()
        found = service.search_vectors(
            queries, vectors, k=max(ks), max_per_document=max_per_document
        )
        search_seconds = time.perf_counter() - start
    finally:
        service.min_score = threshold
    results = [
        score_question(q, r.evidence, ks, threshold) for q, r in zip(questions, found, strict=True)
    ]
    summary = summarise(results, ks, report_k, threshold, embed_seconds, search_seconds)
    return summary, threshold_sweep(results), results


def format_report(report: EvalReport, report_k: int) -> str:
    """Markdown tables, ready to paste into EVALUATION.md."""
    s = report.summary
    ks = sorted(s.recall)
    lines = [
        f"Retrieval eval {report.run_at}: {s.covered} covered + {s.uncovered} uncovered questions",
        "",
        "| K | Recall@K | Precision@K | MRR@K | Recall@K after threshold |",
        "|---|---|---|---|---|",
    ]
    for k in ks:
        lines.append(
            f"| {k} | {s.recall[k]:.3f} | {s.precision[k]:.3f} | {s.mrr[k]:.3f} "
            f"| {s.recall_after_threshold[k]:.3f} |"
        )
    lines += [
        "",
        f"Threshold {s.threshold}: covered kept {s.covered_kept:.0%}, "
        f"uncovered rejected {s.uncovered_rejected:.0%}; lowest covered best score "
        f"{_fmt(s.lowest_covered_best)}, highest uncovered best score "
        f"{_fmt(s.highest_uncovered_best)}",
        f"Latency: embedding {s.embed_seconds} s for all questions (one batched Voyage call, "
        f"incl. any rate-limit wait); vector search {s.search_ms_per_question} ms per question",
        "",
        "| Threshold | Covered kept | Uncovered rejected |",
        "|---|---|---|",
    ]
    for row in report.threshold_sweep:
        lines.append(
            f"| {row.threshold:.2f} | {row.covered_kept:.0%} | {row.uncovered_rejected:.0%} |"
        )
    lines += ["", f"| Tag | Recall@{report_k} |", "|---|---|"]
    lines += [f"| {t} | {v:.3f} |" for t, v in s.recall_by_tag.items()]
    misses = [q for q in report.questions if q.covered and q.recall.get(report_k, 1.0) < 1.0]
    lines += ["", f"Covered questions with Recall@{report_k} < 1 ({len(misses)}):"]
    for q in misses:
        lines.append(
            f"- {q.id} recall {q.recall[report_k]:.2f}, first relevant rank "
            f"{q.first_relevant_rank or '-'}: {q.question}"
        )
    over = [
        q
        for q in report.questions
        if not q.covered and q.best_score is not None and q.best_score >= s.threshold
    ]
    lines += ["", f"Uncovered questions above the threshold ({len(over)}):"]
    lines += [f"- {q.id} best {q.best_score:.3f}: {q.question}" for q in over]
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def main() -> None:
    """CLI: run the eval against the local index, print tables, save JSON to evaluation/results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--k", default=",".join(map(str, DEFAULT_KS)), help="e.g. 1,3,5,10")
    parser.add_argument("--max-per-document", type=int, default=None)
    parser.add_argument("--no-save", action="store_true", help="print only, write no JSON")
    args = parser.parse_args()

    settings = get_settings()
    try:
        ks = tuple(sorted({int(k) for k in args.k.split(",")}))
    except ValueError:
        parser.error(f"--k must be comma-separated integers, got {args.k!r}")
    if min(ks) < 1:
        parser.error("--k values must be positive")
    report_k = settings.retrieval_k if settings.retrieval_k in ks else ks[-1]
    questions = load_questions(args.dataset)
    service = get_retrieval_service(settings)
    try:
        chunks = service.store.client.count(settings.qdrant_collection).count
        summary, sweep, results = run_eval(
            service, questions, ks=ks, report_k=report_k, max_per_document=args.max_per_document
        )
    finally:
        service.store.client.close()  # release the local Qdrant lock

    report = EvalReport(
        run_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        config={
            "dataset": args.dataset.name,
            "dataset_sha256": file_sha256(args.dataset),
            "embed_model": settings.embed_model,
            "collection": settings.qdrant_collection,
            "chunks": chunks,
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "search": "semantic (cosine)",
            "threshold": settings.retrieval_min_score,
            "max_per_document": args.max_per_document,
        },
        summary=summary,
        threshold_sweep=sweep,
        questions=results,
    )
    print(format_report(report, report_k))
    if not args.no_save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out = RESULTS_DIR / f"retrieval-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.json"
        out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        print(f"\nSaved {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()

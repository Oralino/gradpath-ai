"""Retrieval eval runner: labelled questions -> Recall@K, Precision@K, MRR, abstention, latency.

Run from `backend/` (stop the API first; local Qdrant allows one process):
    uv run python -m gradpath.evaluation.retrieval_eval [--k 1,3,5,10] [--max-per-document N]
        [--rerank 10,20] [--rerank-threshold 0.5]

All questions are embedded in one batched Voyage call (`RetrievalService.search_many`), so a full
run fits the free tier. Ranking is scored on the raw top-K (no threshold), so it compares search
methods fairly; the threshold is then judged separately, offline, from each question's best score.
With `--rerank`, the same semantic results are also reranked by the local cross-encoder (top N
candidates per question), so semantic and reranked are compared on one embedding call (T-010).
"""

import argparse
import hashlib
import math
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from gradpath.config import REPO_ROOT, get_settings
from gradpath.evaluation.dataset import DEFAULT_DATASET, Question, load_questions
from gradpath.evaluation.metrics import is_relevant, precision_at_k, recall_at_k, reciprocal_rank
from gradpath.retrieval import Evidence, RetrievalService, get_retrieval_service
from gradpath.retrieval.rerank import (
    DEFAULT_RERANK_MODEL,
    CrossEncoderReranker,
    Reranker,
    rerank,
)

RESULTS_DIR = REPO_ROOT / "evaluation" / "results"
DEFAULT_KS = (1, 3, 5, 10)
SWEEP = tuple(round(0.30 + 0.05 * i, 2) for i in range(7))  # 0.30 .. 0.60
# Reranker scores are sigmoid(logit), 0..1, and spread far wider than cosine: a wider grid.
RERANK_SWEEP = (0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9)


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
    rerank_ms_p50: float | None = None  # reranking only, per question (rerank variants)
    rerank_ms_p95: float | None = None


class EvalReport(BaseModel):
    run_at: str
    config: dict[str, str | int | float | None]
    summary: Summary
    threshold_sweep: list[ThresholdRow]
    questions: list[QuestionResult]


class ComparisonReport(BaseModel):
    """Semantic and reranked variants from one embedding call (`--rerank`)."""

    run_at: str
    config: dict[str, str | int | float | None]
    variants: dict[str, EvalReport]


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


def _validate(questions: list[Question], ks: tuple[int, ...], report_k: int) -> None:
    if not questions:
        raise ValueError("no questions to evaluate")
    if not ks or min(ks) < 1:
        raise ValueError(f"every K must be a positive integer, got {ks}")
    if report_k not in ks:
        raise ValueError(f"report_k {report_k} must be one of {ks}")


def _search_all(
    service: RetrievalService, questions: list[Question], k: int, max_per_document: int | None
) -> tuple[list[list[Evidence]], float, float]:
    """Embed every question in one batch and take each raw top-k (threshold lifted, restored).

    Shared by run_eval and run_rerank_eval. Returns the ranked lists plus embedding and search
    seconds, timed apart.
    """
    threshold = service.min_score
    service.min_score = -1.0
    queries = [q.question for q in questions]
    try:
        start = time.perf_counter()
        vectors = service.embed_many(queries)
        embed_seconds = time.perf_counter() - start
        start = time.perf_counter()
        found = service.search_vectors(queries, vectors, k=k, max_per_document=max_per_document)
        search_seconds = time.perf_counter() - start
    finally:
        service.min_score = threshold
    return [r.evidence for r in found], embed_seconds, search_seconds


def _score_all(
    questions: list[Question],
    ranked: list[list[Evidence]],
    ks: tuple[int, ...],
    report_k: int,
    threshold: float,
    timings: tuple[float, float],
    sweep: tuple[float, ...] = SWEEP,
) -> tuple[Summary, list[ThresholdRow], list[QuestionResult]]:
    """Score every question's ranked list, summarise, and sweep thresholds."""
    results = [score_question(q, r, ks, threshold) for q, r in zip(questions, ranked, strict=True)]
    summary = summarise(results, ks, report_k, threshold, *timings)
    return summary, threshold_sweep(results, sweep), results


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
    _validate(questions, ks, report_k)
    ranked, embed_s, search_s = _search_all(service, questions, max(ks), max_per_document)
    return _score_all(questions, ranked, ks, report_k, service.min_score, (embed_s, search_s))


def run_rerank_eval(
    service: RetrievalService,
    questions: list[Question],
    reranker: Reranker,
    *,
    candidates: tuple[int, ...] = (10, 20),
    ks: tuple[int, ...] = DEFAULT_KS,
    report_k: int = 5,
    max_per_document: int | None = None,
    rerank_threshold: float = 0.5,
) -> dict[str, tuple[Summary, list[ThresholdRow], list[QuestionResult]]]:
    """Semantic-only plus one reranked variant per candidate count, from one embedding call.

    Each variant reranks the semantic top-N and is scored on the reranker's 0..1 score (ranking
    and the abstention threshold alike). N must be >= max(ks) so every K is measured on the same
    number of chunks. The model is warmed up before timing, so its one-off load isn't counted.
    """
    _validate(questions, ks, report_k)
    if not candidates or min(candidates) < max(ks):
        raise ValueError(f"every candidate count must be >= max(ks) {max(ks)}, got {candidates}")
    ranked, embed_s, search_s = _search_all(service, questions, max(candidates), max_per_document)
    timings = (embed_s, search_s)
    top = [r[: max(ks)] for r in ranked]
    variants = {"semantic": _score_all(questions, top, ks, report_k, service.min_score, timings)}
    reranker.score("warm up", ["warm up"])
    for n in sorted(set(candidates)):
        reordered, times = [], []
        for q, r in zip(questions, ranked, strict=True):
            start = time.perf_counter()
            pairs = rerank(q.question, r[:n], reranker)
            times.append(1000 * (time.perf_counter() - start))
            reordered.append([e.model_copy(update={"score": s}) for e, s in pairs])
        summary, sweep, results = _score_all(
            questions, reordered, ks, report_k, rerank_threshold, timings, RERANK_SWEEP
        )
        summary.rerank_ms_p50 = round(statistics.median(times), 1)
        summary.rerank_ms_p95 = round(percentile(times, 0.95), 1)
        variants[f"rerank@{n}"] = (summary, sweep, results)
    return variants


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile (p in 0..1) of a non-empty list."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p * len(ordered)) - 1)]


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
        f"incl. any rate-limit wait); vector search {s.search_ms_per_question} ms per question"
        + (
            f"; reranking p50 {s.rerank_ms_p50} ms, p95 {s.rerank_ms_p95} ms per question"
            if s.rerank_ms_p50 is not None
            else ""
        ),
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
    under = [
        q
        for q in report.questions
        if q.covered and (q.best_score is None or q.best_score < s.threshold)
    ]
    lines += ["", f"Covered questions below the threshold ({len(under)}):"]
    lines += [f"- {q.id} best {_fmt(q.best_score)}: {q.question}" for q in under]
    return "\n".join(lines)


COMPARE_ROWS = (
    ("Recall@5", lambda s: s.recall.get(5)),
    ("Precision@5", lambda s: s.precision.get(5)),
    ("MRR@5", lambda s: s.mrr.get(5)),
    ("Covered kept at threshold", lambda s: s.covered_kept),
    ("Uncovered rejected at threshold", lambda s: s.uncovered_rejected),
    ("Lowest covered best score", lambda s: s.lowest_covered_best),
    ("Highest uncovered best score", lambda s: s.highest_uncovered_best),
)


def format_comparison(report: ComparisonReport) -> str:
    """One table, one column per variant (semantic and rerank thresholds use different scales)."""
    names = list(report.variants)
    sums = [report.variants[n].summary for n in names]
    lines = [
        "| Metric | " + " | ".join(names) + " |",
        "|---|" + "---|" * len(names),
        "| Threshold | " + " | ".join(str(s.threshold) for s in sums) + " |",
    ]
    for label, get in COMPARE_ROWS:
        lines.append(f"| {label} | " + " | ".join(_fmt(get(s)) for s in sums) + " |")
    lines.append(
        "| Rerank ms p50 / p95 | "
        + " | ".join(
            "-" if s.rerank_ms_p50 is None else f"{s.rerank_ms_p50} / {s.rerank_ms_p95}"
            for s in sums
        )
        + " |"
    )
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
    parser.add_argument(
        "--rerank", default=None, help="also rerank the semantic top N, e.g. 10,20 (local model)"
    )
    parser.add_argument("--rerank-threshold", type=float, default=0.5)
    parser.add_argument("--rerank-model", default=DEFAULT_RERANK_MODEL, help="a fastembed model")
    args = parser.parse_args()

    settings = get_settings()
    ks = _int_list(parser, "--k", args.k)
    candidates = _int_list(parser, "--rerank", args.rerank) if args.rerank else None
    report_k = settings.retrieval_k if settings.retrieval_k in ks else ks[-1]
    questions = load_questions(args.dataset)
    service = get_retrieval_service(settings)
    try:
        chunks = service.store.client.count(settings.qdrant_collection).count
        if candidates:
            reranker = CrossEncoderReranker(args.rerank_model)
            variants = run_rerank_eval(
                service,
                questions,
                reranker,
                candidates=candidates,
                ks=ks,
                report_k=report_k,
                max_per_document=args.max_per_document,
                rerank_threshold=args.rerank_threshold,
            )
        else:
            variants = {
                "semantic": run_eval(
                    service,
                    questions,
                    ks=ks,
                    report_k=report_k,
                    max_per_document=args.max_per_document,
                )
            }
    finally:
        service.store.client.close()  # release the local Qdrant lock

    run_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    config = {
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
    }
    reports = {}
    for name, (summary, sweep, results) in variants.items():
        cfg = dict(config)
        if name != "semantic":
            cfg.update(
                search=f"semantic top {name.split('@')[1]}, reranked",
                reranker=reranker.model_name,
                threshold=args.rerank_threshold,
            )
        reports[name] = EvalReport(
            run_at=run_at, config=cfg, summary=summary, threshold_sweep=sweep, questions=results
        )
        print(f"\n## {name}\n\n{format_report(reports[name], report_k)}")
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    if candidates:
        comparison = ComparisonReport(run_at=run_at, config=config, variants=reports)
        print(f"\n## Comparison\n\n{format_comparison(comparison)}")
        payload, out_name = comparison.model_dump_json(indent=2), f"retrieval-rerank-{stamp}.json"
    else:
        payload, out_name = reports["semantic"].model_dump_json(indent=2), f"retrieval-{stamp}.json"
    if not args.no_save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out = RESULTS_DIR / out_name
        out.write_text(payload, encoding="utf-8")
        print(f"\nSaved {out.relative_to(REPO_ROOT)}")


def _int_list(parser: argparse.ArgumentParser, flag: str, value: str) -> tuple[int, ...]:
    """Parse "1,3,5" into sorted unique positive ints, or exit with a usage error."""
    try:
        values = tuple(sorted({int(v) for v in value.split(",")}))
    except ValueError:
        parser.error(f"{flag} must be comma-separated integers, got {value!r}")
    if min(values) < 1:
        parser.error(f"{flag} values must be positive")
    return values


if __name__ == "__main__":
    main()

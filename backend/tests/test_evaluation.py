"""Retrieval evaluation: dataset validation, metric definitions and the runner (no Voyage)."""

import json

import pytest
from conftest import KB_DOCS, KeywordEmbeddings
from pydantic import ValidationError
from qdrant_client import QdrantClient

from gradpath.evaluation.dataset import DEFAULT_DATASET, Question, Target, load_questions
from gradpath.evaluation.metrics import matches, precision_at_k, recall_at_k, reciprocal_rank
from gradpath.evaluation.retrieval_eval import (
    EvalReport,
    format_report,
    run_eval,
    threshold_sweep,
)
from gradpath.ingestion.index import rebuild_index
from gradpath.retrieval import Evidence, RetrievalService


def ev(chunk_id: str, doc: str = "pg", section: str = "Primer > Cache > Client", score=0.9):
    return Evidence(
        chunk_id=chunk_id,
        document_id=doc,
        title=doc,
        section=section,
        source_url=f"https://example.org/{doc}",
        text="",
        score=score,
    )


PG = Target(document_id="pg", page="https://example.org/pg")
MDN = Target(document_id="mdn", page="https://example.org/mdn")
SQLITE = Target(document_id="sqlite", page="https://example.org/sqlite")


# --- metrics -------------------------------------------------------------------------------


def test_section_must_be_a_whole_heading():
    chunk = ev("pg:0:0", section="Primer > Cache > Client caching")
    assert matches(chunk, PG.model_copy(update={"section": "Cache"}))
    assert not matches(chunk, PG.model_copy(update={"section": "Cach"}))
    assert not matches(
        ev("pg:0:1", section="Primer > Cache-control"), PG.model_copy(update={"section": "Cache"})
    )


def test_page_and_document_must_both_match():
    assert matches(ev("pg:0:0"), PG)
    assert not matches(ev("mdn:0:0", doc="mdn"), PG)
    wrong_page = ev("pg:1:0").model_copy(update={"source_url": "https://example.org/other"})
    assert not matches(wrong_page, PG)


def test_recall_precision_and_reciprocal_rank():
    ranked = [ev("git:0:0", doc="git"), ev("pg:0:0"), ev("pg:0:1"), ev("x:0:0", doc="x")]
    assert recall_at_k(ranked, [PG, MDN], 4) == 0.5  # one of two targets found
    assert recall_at_k(ranked, [PG], 1) == 0.0
    assert precision_at_k(ranked, [PG], 4) == 0.5  # two relevant chunks in four slots
    assert precision_at_k(ranked[:2], [PG], 5) == 0.2  # empty slots count as misses
    assert reciprocal_rank(ranked, [PG], 4) == 0.5  # first hit at rank 2
    assert reciprocal_rank(ranked, [MDN], 4) == 0.0


def test_recall_without_targets_is_an_error():
    with pytest.raises(ValueError):
        recall_at_k([ev("pg:0:0")], [], 5)


# --- dataset -------------------------------------------------------------------------------


def test_covered_needs_targets_and_uncovered_must_have_none():
    with pytest.raises(ValidationError):
        Question(id="q", question="?", covered=True)
    with pytest.raises(ValidationError):
        Question(id="q", question="?", covered=False, relevant=[PG])


def test_duplicate_ids_are_rejected(tmp_path):
    row = {"id": "q-001", "question": "?", "covered": False}
    path = tmp_path / "qs.jsonl"
    path.write_text(json.dumps(row) + "\n\n" + json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_questions(path)


def test_the_real_dataset_loads():
    questions = load_questions(DEFAULT_DATASET)
    assert len(questions) == 40
    assert sum(q.covered for q in questions) == 32  # v1.1: q-035 covered; v1.2: q-034 covered


# --- runner --------------------------------------------------------------------------------


class CountingEmbeddings(KeywordEmbeddings):
    """Keyword vectors plus a batched `embed_queries` that counts its calls."""

    def __init__(self):
        self.batch_calls = 0

    def embed_queries(self, texts):
        self.batch_calls += 1
        return [self._vec(t) for t in texts]


@pytest.fixture
def eval_service():
    client = QdrantClient(":memory:")
    rebuild_index(client, "kb", KB_DOCS, KeywordEmbeddings())
    return RetrievalService(client, "kb", CountingEmbeddings(), k=3, min_score=0.5)


QUESTIONS = [
    Question(id="q-1", question="sql index", covered=True, relevant=[PG, SQLITE], tags=["db"]),
    Question(id="q-2", question="http status", covered=True, relevant=[MDN], tags=["http"]),
    Question(id="q-3", question="sourdough bread", covered=False),
]


def test_run_eval_scores_one_batched_search(eval_service):
    summary, sweep, results = run_eval(eval_service, QUESTIONS, ks=(1, 3), report_k=3)

    assert eval_service.embeddings.batch_calls == 1  # one embedding request for the whole set
    assert eval_service.min_score == 0.5  # threshold restored after the raw search
    assert summary.recall == {1: 0.75, 3: 1.0}  # q-1 has two targets; one fits in the top 1
    assert summary.mrr[3] == 1.0
    # q-1's top 3 are all pg/sqlite chunks; q-2 has one mdn chunk then two unrelated ones.
    assert summary.precision[3] == pytest.approx((1.0 + 1 / 3) / 2)
    assert summary.uncovered_rejected == 1.0
    assert summary.covered_kept == 1.0
    assert summary.recall_by_tag == {"db": 1.0, "http": 1.0}
    assert results[2].recall == {}  # uncovered questions get no ranking metrics
    assert len(results[0].ranked) == 3  # raw top max(k), not cut by the threshold


def test_recall_after_threshold_drops_weak_chunks(eval_service):
    eval_service.min_score = 1.5  # above any cosine score: nothing clears it
    summary, _, _ = run_eval(eval_service, QUESTIONS[:1], ks=(3,), report_k=3)
    assert summary.recall[3] == 1.0
    assert summary.recall_after_threshold[3] == 0.0
    assert summary.covered_kept == 0.0


def test_report_k_must_be_measured(eval_service):
    with pytest.raises(ValueError):
        run_eval(eval_service, QUESTIONS, ks=(1, 3), report_k=5)


def test_threshold_sweep_trades_coverage_for_rejection(eval_service):
    _, _, results = run_eval(eval_service, QUESTIONS, ks=(3,), report_k=3)
    rows = threshold_sweep(results, (0.0, 1.01))
    assert (rows[0].covered_kept, rows[0].uncovered_rejected) == (1.0, 0.0)
    assert (rows[1].covered_kept, rows[1].uncovered_rejected) == (0.0, 1.0)


def test_format_report_lists_tables_and_misses(eval_service):
    summary, sweep, results = run_eval(eval_service, QUESTIONS, ks=(1, 3), report_k=3)
    report = EvalReport(
        run_at="now", config={}, summary=summary, threshold_sweep=sweep, questions=results
    )
    text = format_report(report, 3)
    assert "| 3 | 1.000 |" in text
    assert "Covered questions with Recall@3 < 1 (0)" in text
    assert "Uncovered questions above the threshold (0)" in text


def test_label_typos_and_duplicate_targets_are_refused(tmp_path):
    with pytest.raises(ValidationError):
        Target(document_id="pg", page="https://example.org/pg", sections="Cache")
    with pytest.raises(ValidationError):
        Target(document_id="pg", page="https://example.org/pg", section="")
    with pytest.raises(ValidationError):
        Question(id="q", question="?", covered=True, relevant=[PG, PG])
    path = tmp_path / "qs.jsonl"
    path.write_text('{"id": "q-001"}\n{not json', encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        load_questions(path)


def test_run_eval_rejects_empty_input_and_bad_k(eval_service):
    with pytest.raises(ValueError):
        run_eval(eval_service, [], ks=(3,), report_k=3)
    with pytest.raises(ValueError):
        run_eval(eval_service, QUESTIONS, ks=(0, 3), report_k=3)

"""Workflow eval scoring (T-003 step 7): hand-made results, no model or Voyage calls."""

import json

import pytest

from gradpath.evaluation.workflow_eval import (
    DEFAULT_CASES,
    Expectations,
    GapExpectation,
    WorkflowCase,
    load_cases,
    score,
    summarise,
)
from gradpath.rag.answer import Citation
from gradpath.workflows import CareerPrepResult, UserProfile
from gradpath.workflows.schemas import CritiqueIssue, GapItem, RoadmapItem


def gap(id_, skill, status, importance="required", chunks=(), facts=()):
    return GapItem(
        requirement_id=id_,
        skill=skill,
        importance=importance,
        status=status,
        profile_evidence_ids=list(facts),
        knowledge_chunk_ids=list(chunks),
        reasoning="r",
        confidence="medium",
    )


def item(order, reqs, topic, hours=4.0, cites=()):
    return RoadmapItem(
        order=order,
        topic=topic,
        requirement_ids=reqs,
        why_it_matters="w",
        objective="o",
        resources=[
            Citation(chunk_id=c, title="t", section="s", source_url="u", score=0.7) for c in cites
        ],
        exercise="e",
        completion_criteria="c",
        effort_hours_estimate=hours,
    )


def result(gaps, roadmap, status="complete", revisions=0, issues=()):
    return CareerPrepResult(
        status=status,
        job=None,
        gaps=gaps,
        roadmap=roadmap,
        interview_questions=[],
        unresolved_issues=list(issues),
        revisions_used=revisions,
        errors=[],
        node_log=[],
    )


CASE = WorkflowCase(
    id="wf-t",
    job_description="x",
    profile="y",
    expect=Expectations(
        gaps=[
            GapExpectation(skill_any=["docker"], status_in=["not_yet_evidenced"]),
            GapExpectation(
                skill_any=["postgres"], status_in=["partially_evidenced"], cites_correction=True
            ),
        ],
        roadmap_covers=["docker"],
        max_demonstrated_share=0.5,
    ),
)
PROFILE = UserProfile(weekly_hours=5, timeline_weeks=4)  # 20 h


def good():
    return result(
        [
            gap("r-1", "Docker packaging", "not_yet_evidenced", chunks=["d:1"]),
            gap("r-2", "PostgreSQL", "partially_evidenced", chunks=["pg:1"], facts=["c-1"]),
            gap("r-3", "Python", "demonstrated", facts=["p-1"]),
            gap("r-4", "Degree", "not_applicable"),
        ],
        [
            item(1, ["r-1"], "Containers", cites=["d:1"]),
            item(2, ["r-2"], "Postgres", cites=["pg:1"]),
        ],
    )


def test_a_good_result_passes_every_check():
    s = score(CASE, good(), PROFILE, max_rev=1)
    assert s["passed"], s["checks"]
    assert s["counts"]["demonstrated_share"] == 0.33
    assert s["counts"]["uncited_items_with_evidence"] == 0


def test_each_failure_is_caught():
    r = good()
    r.gaps[1].profile_evidence_ids = ["p-2"]  # no correction cited
    r.gaps[0].status = "demonstrated"  # docker wrong
    r.roadmap = [
        item(1, ["r-2"], "Postgres", hours=30, cites=["d:1"])
    ]  # wrong citation, over budget
    r.revisions_used = 2
    checks = score(CASE, r, PROFILE, max_rev=1)["checks"]
    failed = {k for k, v in checks.items() if not v}
    assert failed == {
        "loop_terminated",
        "gap_1:docker",
        "gap_2:postgres",
        "covers:docker",
        "demonstrated_share",
        "citations_retrieved",
        "budget_respected_or_flagged",
    }


def test_flagged_over_budget_counts_as_handled_and_uncited_items_are_counted():
    r = good()
    r.roadmap = [item(1, ["r-1"], "Containers", hours=40), item(2, ["r-2"], "Postgres")]
    r.unresolved_issues = [CritiqueIssue(code="over_budget", message="m", severity="blocking")]
    s = score(CASE, r, PROFILE, max_rev=1)
    assert s["checks"]["budget_respected_or_flagged"]
    assert s["counts"]["uncited_items_with_evidence"] == 2


def test_missing_requirement_fails_its_gap_check_and_partial_fails():
    r = good()
    r.gaps = [g for g in r.gaps if "Docker" not in g.skill]
    r.status = "partial"
    checks = score(CASE, r, PROFILE, max_rev=1)["checks"]
    assert not checks["gap_1:docker"] and not checks["not_partial"]


def test_required_gap_without_an_item_is_caught():
    r = good()
    r.roadmap = r.roadmap[:1]
    assert not score(CASE, r, PROFILE, max_rev=1)["checks"]["required_gaps_covered"]


def test_the_committed_cases_load_and_use_sample_profiles_only():
    cases = load_cases()
    assert [c.id for c in cases] == ["wf-001", "wf-002", "wf-003", "wf-004"]
    for c in cases:
        assert (c.load_profile().profile_id or "").startswith("sample-")


def test_case_file_rejects_unknown_fields_and_duplicates(tmp_path):
    line = DEFAULT_CASES.read_text(encoding="utf-8").splitlines()[0]
    bad = json.loads(line)
    bad["expect"]["typo"] = 1
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        load_cases(path)
    path.write_text(line + "\n" + line, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_cases(path)


def test_summary_table_lists_failed_checks_and_errors():
    s = score(CASE, good(), PROFILE, max_rev=1)
    records = [
        {"id": "wf-a", "seconds": 90.0, "score": s},
        {"id": "wf-b", "seconds": 3.0, "error": "ValidationError"},
    ]
    text = summarise(records)
    assert "| wf-a | yes | - |" in text and "error: ValidationError" in text
    assert "| not_partial | 1/1 |" in text


def test_citations_on_an_item_with_an_unknown_requirement_fail():
    r = good()
    r.roadmap = [item(1, ["r-1", "r-99"], "Containers", cites=["d:1"])]
    assert not score(CASE, r, PROFILE, max_rev=1)["checks"]["citations_retrieved"]


def test_any_matching_gap_can_satisfy_an_expectation_and_case_is_ignored():
    case = CASE.model_copy(
        update={
            "expect": Expectations(
                gaps=[GapExpectation(skill_any=["SQL"], status_in=["partially_evidenced"])],
                roadmap_covers=["POSTGRES"],
            )
        }
    )
    r = good()
    r.gaps.insert(0, gap("r-9", "NoSQL stores", "not_yet_evidenced"))  # matched first, wrong
    r.gaps[2].skill = "PostgreSQL"
    checks = score(case, r, PROFILE, max_rev=1)["checks"]
    assert checks["gap_1:sql"] and checks["covers:postgres"]


def test_cases_must_use_sample_profiles_inside_the_repo(tmp_path):
    case = WorkflowCase.model_validate_json(
        DEFAULT_CASES.read_text(encoding="utf-8").splitlines()[0]
    )
    with pytest.raises(ValueError, match="outside the repo"):
        case.model_copy(update={"profile": "../../somewhere/real.json"}).load_profile()
    real = tmp_path / "real.json"
    real.write_text('{"skills": ["Python"]}', encoding="utf-8")
    from gradpath.config import REPO_ROOT

    inside = REPO_ROOT / "backend" / "data" / "_test_real_profile.json"
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_text('{"skills": ["Python"]}', encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="sample- profile"):
            case.model_copy(
                update={"profile": "backend/data/_test_real_profile.json"}
            ).load_profile()
    finally:
        inside.unlink()


def test_retry_filter_leaves_other_records_alone():
    import logging

    from gradpath.workflows.graph import _NoExceptionText

    try:
        raise ValueError("secret detail")
    except ValueError:
        import sys

        info = sys.exc_info()
    other = logging.LogRecord("x", logging.ERROR, "f", 1, "Timed attempt observer failed", (), info)
    assert _NoExceptionText().filter(other) and other.exc_info is info
    retry = logging.LogRecord(
        "x",
        logging.INFO,
        "f",
        1,
        "Retrying task t after 1.00 seconds (attempt 1) after ValueError secret detail",
        (),
        info,
    )
    _NoExceptionText().filter(retry)
    assert "secret" not in retry.getMessage() and retry.exc_info is None

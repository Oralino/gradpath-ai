"""Routing eval and comparison runners (T-006 step 7): scoring in code, fake models, no calls."""

import pytest

from gradpath.evaluation.routing_compare import COMPARE_IDS, compare_case, load_inputs, served
from gradpath.evaluation.routing_compare import summarise as compare_summary
from gradpath.evaluation.routing_eval import load_cases, metrics, run_case, summarise
from gradpath.providers import FakeChatModel

CASES = {c.id: c for c in load_cases()}

# the kind each label implies, for a perfect fake classifier
KIND = {
    ("traditional_rag", "run"): "knowledge_question",
    ("agentic_workflow", "run"): "job_preparation",
    ("agentic_workflow", "needs_input"): "job_preparation",
}
UNSUPPORTED = {
    "rt-023": "job_comparison",
    "rt-024": "progress_tracking",
    "rt-025": "resume_rewrite",
}


def perfect_kind(case) -> str:
    return UNSUPPORTED.get(case.id) or KIND[(case.expected_route, case.expected_action)]


def test_label_file_is_valid_and_complete():
    assert len(CASES) == 36
    assert all(c.id.startswith("rt-") for c in CASES.values())
    for i in COMPARE_IDS:
        assert CASES[i].expected_action == "run"


def test_rules_only_run_decides_ten_cases_all_correctly():
    records = [run_case(c, None) for c in CASES.values()]
    m = metrics(records, CASES)
    assert (m["decided"], m["undecided"]) == (9, 27)
    assert m["accuracy"] == 1.0 and m["wrong"] == []


def test_a_perfect_classifier_scores_one_everywhere():
    records = [
        run_case(c, FakeChatModel(responses=[{"kind": perfect_kind(c), "reason": "r"}]))
        for c in CASES.values()
    ]
    m = metrics(records, CASES)
    assert m["decided"] == 36 and m["accuracy"] == 1.0
    assert m["workflow_precision"] == 1.0 and m["workflow_recall"] == 1.0
    assert m["over_routed"] == 0.0 and m["under_routed"] == 0.0
    assert m["by_decider"]["rules"]["cases"] == 9 and m["by_decider"]["model"]["cases"] == 27


def test_errors_are_counted_in_the_right_direction():
    always_rag = FakeChatModel(responses=[{"kind": "knowledge_question", "reason": "r"}])
    records = [run_case(c, always_rag) for c in CASES.values()]
    m = metrics(records, CASES)
    assert m["over_routed"] == 0.0  # nothing sent to the workflow by mistake...
    assert m["under_routed"] > 0  # ...but complex requests the rules missed went to RAG
    assert "rt-015" in m["wrong"]  # personalised questions, decided by the model
    assert "| rt-015 |" in summarise(records, CASES)


def test_failed_classification_is_reported_as_default():
    records = [run_case(CASES["rt-029"], FakeChatModel(responses=["not json"]))]
    assert records[0]["decided_by"] == "default"
    assert metrics(records, CASES)["by_decider"]["default"] == {"cases": 1, "correct": 1}


def test_comparison_inputs_are_samples():
    jd, profile = load_inputs(CASES["rt-011"])
    assert jd and profile.profile_id.startswith("sample-")
    assert load_inputs(CASES["rt-001"]) == (None, None)


@pytest.mark.parametrize(
    ("case_id", "path", "outcome", "ok"),
    [
        ("rt-001", "rag", {"status": "answered", "citations": 2}, True),
        ("rt-001", "rag", {"status": "answered", "citations": 0}, False),  # uncited
        ("rt-001", "rag", {"status": "insufficient_evidence"}, True),  # honest abstention
        ("rt-001", "workflow", {"status": "complete"}, False),  # doesn't answer the question
        ("rt-011", "workflow", {"status": "complete"}, True),
        ("rt-011", "workflow", {"status": "fallback"}, False),
        ("rt-011", "rag", {"status": "answered", "citations": 3}, False),  # not personalised
    ],
)
def test_served(case_id, path, outcome, ok):
    assert served(CASES[case_id], path, outcome) is ok


def test_each_path_runs_once_and_adaptive_reuses_it():
    calls = {"rag": 0, "workflow": 0}

    def rag(case):
        calls["rag"] += 1
        return {"status": "answered", "citations": 1, "seconds": 5.0, "calls": 1}

    def workflow(case):
        calls["workflow"] += 1
        return {"status": "complete", "gaps": 4, "items": 6, "seconds": 90.0, "calls": 6}

    row = compare_case(CASES["rt-017"], lambda c: ("rag", 0.0, 0), rag, workflow)
    assert calls == {"rag": 1, "workflow": 1}
    s = row["strategies"]
    assert s["adaptive"]["served"] and s["always_rag"]["served"]
    assert not s["always_workflow"]["served"]  # 90 s and 6 calls for "What is Docker?"
    assert s["adaptive"]["seconds"] == 5.0 and s["always_workflow"]["model_calls"] == 6

    row = compare_case(CASES["rt-001"], lambda c: ("rag", 0.0, 0), rag, None)
    assert row["strategies"]["always_workflow"]["outcome"]["status"] == "not_run: missing input"
    assert "served" in compare_summary([row]) and "1/1 served" in compare_summary([row])


def test_adaptive_includes_the_routing_call():
    def wf(case):
        return {"status": "complete", "seconds": 80.0, "calls": 6}

    def rag(case):
        return {"status": "answered", "citations": 1, "seconds": 4.0, "calls": 1}

    row = compare_case(CASES["rt-016"], lambda c: ("workflow", 2.0, 1), rag, wf)
    a = row["strategies"]["adaptive"]
    assert (a["seconds"], a["model_calls"]) == (82.0, 7)


def test_unknown_ids_are_reported_not_silently_dropped():
    stale = {"id": "rt-999", "route": "traditional_rag", "action": "run", "kind": "other",
             "decided_by": "rules", "seconds": 0.0}  # fmt: skip
    records = [run_case(CASES["rt-001"], None), stale]
    m = metrics(records, CASES)
    assert m["unknown_ids"] == ["rt-999"] and m["decided"] == 1
    assert "| Decided / undecided / unknown ids | 1 / 0 / 1 |" in summarise(records, CASES)


def test_empty_run_prints_n_a_not_none():
    assert "None" not in summarise([], CASES)


def test_abstention_never_serves_a_workflow_request():
    assert not served(CASES["rt-011"], "rag", {"status": "insufficient_evidence"})

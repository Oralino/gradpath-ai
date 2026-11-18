"""Graph-shape tests for the career workflow skeleton (T-003 step 4): the parallel joins, the
bounded revision loop, the recursion backstop and the real pure-code nodes. No models, no Voyage."""

import json
from dataclasses import replace

import pytest
from conftest import placeholder_nodes
from langgraph.errors import GraphRecursionError
from pydantic import ValidationError

from gradpath.config import REPO_ROOT, Settings
from gradpath.workflows import NodeSet, UserProfile, WorkflowContext, build_graph, run_workflow
from gradpath.workflows.graph import recursion_limit_for, route_after_evaluation
from gradpath.workflows.nodes import profile_to_evidence
from gradpath.workflows.schemas import Critique, CritiqueIssue

SAMPLE_PROFILE = REPO_ROOT / "evaluation" / "profiles" / "sample_new_grad.json"
SAMPLE_JD = (
    REPO_ROOT / "evaluation" / "job_descriptions" / "sample_backend_new_grad.txt"
).read_text(encoding="utf-8")
CTX = WorkflowContext()
# The graph with placeholders for the model/Voyage nodes, so these tests need no services.
SKELETON = placeholder_nodes()
FAIL = Critique(
    passed=False, issues=[CritiqueIssue(code="x", message="still wrong", severity="blocking")]
)


def profile() -> UserProfile:
    return UserProfile.model_validate(json.loads(SAMPLE_PROFILE.read_text(encoding="utf-8")))


def run(impl: NodeSet = SKELETON, max_revisions: int = 1):
    return run_workflow(SAMPLE_JD, profile(), context=CTX, max_revisions=max_revisions, impl=impl)


def test_happy_path_runs_every_stage_once_in_order():
    result = run()
    assert result.status == "complete"
    assert result.revisions_used == 0
    log = result.node_log
    assert sorted(log) == sorted(
        [
            "analyze_job",
            "analyze_profile",
            "retrieve_knowledge",
            "analyze_gaps",
            "plan_roadmap",
            "interview_questions",
            "evaluate",
            "finalize",
        ]
    )
    # joins: gaps after both branches, evaluate after both roadmap and questions
    assert log.index("analyze_gaps") > max(
        log.index("retrieve_knowledge"), log.index("analyze_profile")
    )
    assert log.index("evaluate") > max(log.index("plan_roadmap"), log.index("interview_questions"))
    assert log[-1] == "finalize"


def test_join_waits_for_the_longer_branch():
    """analyze_gaps must see both the profile evidence and the knowledge, even though the job
    branch takes one step more than the profile branch."""
    seen = {}

    def gaps(state):
        seen["keys"] = {"profile_evidence", "knowledge"} <= state.keys()
        return {"gaps": []}

    result = run(replace(SKELETON, analyze_gaps=gaps))
    assert seen["keys"] is True
    assert result.node_log.count("analyze_gaps") == 1


@pytest.mark.parametrize("limit", [0, 1, 2, 3])
def test_failing_critic_stops_at_the_revision_limit(limit):
    calls = {"evaluate": 0}

    def always_fail(state):
        calls["evaluate"] += 1
        return {"critique": FAIL}

    result = run(replace(SKELETON, evaluate=always_fail), max_revisions=limit)
    assert result.status == "complete_with_limitations"
    assert result.revisions_used == limit
    assert result.node_log.count("revise") == limit
    assert calls["evaluate"] == limit + 1
    assert [i.code for i in result.unresolved_issues] == ["x"]


def test_critic_passing_after_one_revision_ends_the_loop():
    def fail_then_pass(state):
        return {"critique": Critique(passed=state.get("revision_count", 0) >= 1)}

    result = run(replace(SKELETON, evaluate=fail_then_pass), max_revisions=2)
    assert result.status == "complete"
    assert result.revisions_used == 1


def test_revise_that_returns_only_a_roadmap_still_counts():
    impl = replace(SKELETON, evaluate=lambda s: {"critique": FAIL}, revise=lambda s: {})
    assert run(impl, max_revisions=2).revisions_used == 2


@pytest.mark.parametrize(
    "node,update",
    [
        ("revise", {"revision_count": 0}),
        ("evaluate", {"critique": FAIL, "max_revisions": 99}),
        ("evaluate", {"critique": FAIL, "revision_count": 0}),
        ("analyze_gaps", {"node_log": ["fake"]}),
        ("analyze_job", {"job_description": "replaced"}),
        ("plan_roadmap", {"result": None}),
    ],
)
def test_nodes_may_not_write_protected_keys(node, update):
    """No node can reset the counter, raise the limit, rewrite the input or the log, or write
    the result (only finalize may)."""
    nodes = {"evaluate": lambda s: {"critique": FAIL}, node: lambda s: update}
    impl = replace(SKELETON, **nodes)
    with pytest.raises(ValueError, match="may not write"):
        run(impl, max_revisions=2)


def test_node_returning_nothing_gets_a_clear_error():
    with pytest.raises(TypeError, match="'analyze_gaps' returned NoneType"):
        run(replace(SKELETON, analyze_gaps=lambda s: None))


def test_backstop_stops_a_loop_bug(monkeypatch):
    """If the route function always said "revise", recursion_limit would still stop the loop."""
    monkeypatch.setattr("gradpath.workflows.graph.route_after_evaluation", lambda s: "revise")
    with pytest.raises(GraphRecursionError):
        run(max_revisions=1)


def test_critic_flag_alone_does_not_make_it_complete():
    """passed=True with a blocking issue is not ok: code decides from the issues."""
    contradictory = Critique(
        passed=True, issues=[CritiqueIssue(code="y", message="bad", severity="blocking")]
    )
    result = run(replace(SKELETON, evaluate=lambda s: {"critique": contradictory}), 1)
    assert result.status == "complete_with_limitations"
    assert result.revisions_used == 1
    minor = Critique(passed=True, issues=[CritiqueIssue(code="z", message="m", severity="minor")])
    assert run(replace(SKELETON, evaluate=lambda s: {"critique": minor})).status == "complete"


def test_missing_critique_is_partial():
    result = run(replace(SKELETON, evaluate=lambda s: {}))
    assert result.status == "partial"
    assert "never evaluated" in result.errors[0]


def test_errors_plus_failing_critic_is_partial_and_keeps_the_issues():
    impl = replace(
        SKELETON,
        analyze_job=lambda s: {"errors": ["job failed"]},
        evaluate=lambda s: {"critique": FAIL},
    )
    result = run(impl, max_revisions=0)
    assert result.status == "partial"
    assert [i.code for i in result.unresolved_issues] == ["x"]


@pytest.mark.parametrize("limit", [0, 1, 2, 3])
def test_recursion_limit_matches_the_real_step_count(limit):
    """With no spare steps the worst case still fits, so the formula counts steps correctly..."""
    impl = replace(SKELETON, evaluate=lambda s: {"critique": FAIL})
    state = {"job_description": "j", "profile": profile(), "max_revisions": limit,
             "revision_count": 0, "errors": [], "node_log": []}  # fmt: skip
    exact = recursion_limit_for(limit) - 2
    build_graph(impl).invoke(state, context=CTX, config={"recursion_limit": exact})
    # ...and one step fewer is not enough, so the limit really does stop a runaway graph.
    with pytest.raises(GraphRecursionError):
        build_graph(impl).invoke(state, context=CTX, config={"recursion_limit": exact - 1})


def test_route_after_evaluation():
    assert route_after_evaluation({}) == "finalize"
    assert route_after_evaluation({"critique": Critique(passed=True)}) == "finalize"
    assert route_after_evaluation({"critique": FAIL, "max_revisions": 1}) == "revise"
    assert route_after_evaluation({"critique": FAIL, "max_revisions": 1, "revision_count": 1}) == (
        "finalize"
    )


@pytest.mark.parametrize("bad", [-1, 4])
def test_max_revisions_out_of_range_is_refused(bad):
    with pytest.raises(ValueError):
        run(max_revisions=bad)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, workflow_max_revisions=bad)


@pytest.mark.parametrize("bad", [True, 2.5, "1", None])
def test_max_revisions_must_be_an_int(bad):
    with pytest.raises(ValueError, match="must be an int"):
        run(max_revisions=bad)


def test_input_is_validated_before_the_graph_runs():
    p = profile()
    with pytest.raises(ValidationError):  # too short to be a posting
        run_workflow("job text", p, context=CTX, max_revisions=0)
    with pytest.raises(ValidationError):
        run_workflow("x" * 20_001, p, context=CTX, max_revisions=0)
    with pytest.raises(ValidationError):  # too many corrections
        run_workflow(SAMPLE_JD, p, context=CTX, max_revisions=0, corrections=["c"] * 11)
    with pytest.raises(ValidationError):  # one correction too long
        run_workflow(SAMPLE_JD, p, context=CTX, max_revisions=0, corrections=["c" * 501])


def test_errors_from_parallel_nodes_are_merged_and_mark_the_result_partial():
    impl = replace(
        SKELETON,
        analyze_job=lambda s: {"errors": ["job failed"]},
        analyze_profile=lambda s: {"errors": ["profile failed"]},
    )
    result = run(impl)
    assert result.status == "partial"
    assert sorted(result.errors) == ["job failed", "profile failed"]


def test_nodes_that_ask_for_the_runtime_get_the_context():
    seen = {}

    def job(state, runtime):
        seen["ctx"] = runtime.context
        return {}

    ctx = WorkflowContext()
    run_workflow(
        SAMPLE_JD, profile(), context=ctx, max_revisions=0, impl=replace(SKELETON, analyze_job=job)
    )
    assert seen["ctx"] is ctx


def test_sample_profile_becomes_numbered_evidence():
    evidence = profile_to_evidence(profile())
    assert [e.id for e in evidence] == [f"p-{i}" for i in range(1, len(evidence) + 1)]
    kinds = {e.kind for e in evidence}
    assert kinds == {"education", "skill", "coursework", "project", "experience"}
    project = next(e for e in evidence if e.kind == "project")
    assert "Flask" in project.text


def test_profile_rejects_unknown_fields_and_oversized_input():
    with pytest.raises(ValidationError):
        UserProfile.model_validate({"skills": ["Python"], "salary": 1})
    with pytest.raises(ValidationError):
        UserProfile.model_validate({"skills": ["x" * 201]})
    with pytest.raises(ValidationError):
        UserProfile.model_validate({"skills": ["s"] * 51})


def test_profile_total_size_is_capped():
    """Every field within its own limit, but together too big."""
    project = {"name": "p", "description": "d" * 1200, "technologies": ["t" * 200] * 15}
    with pytest.raises(ValidationError, match="profile is too long"):
        UserProfile.model_validate({"projects": [project] * 4})

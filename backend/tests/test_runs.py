"""Background runs with polling (T-016, always-hard: workflow limits and threads). Placeholder
nodes, a fake clock and gates, so no model, Voyage or network calls and no real waiting."""

import threading
import time
import uuid

import langsmith
import pytest
import voyageai.error
from conftest import placeholder_nodes
from fastapi.testclient import TestClient
from test_tracing import RecordingClient
from test_workflow_graph import SAMPLE_JD, profile

from gradpath.api import limits
from gradpath.api.deps import get_answer_model, get_extraction_model, get_retrieval
from gradpath.api.main import create_app
from gradpath.api.runs import get_run_store
from gradpath.config import Settings
from gradpath.providers import FakeChatModel
from gradpath.workflows import WorkflowContext, build_graph
from gradpath.workflows.runs import (
    CHOSEN_AFTER_EVALUATE,
    FAILED,
    KEY_REFUSED,
    MAX_RUNS,
    PREREQS,
    RUN_TTL_S,
    STAGES,
    RunBusy,
    RunStore,
    stage_states,
)
from gradpath.workflows.schemas import WorkflowInput

SETTINGS = Settings(_env_file=None, workflow_max_revisions=1, workflow_time_budget_s=300)
CTX = WorkflowContext()


def data() -> WorkflowInput:
    return WorkflowInput(job_description=SAMPLE_JD, profile=profile(), corrections=[])


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def wait(store: RunStore, run_id: str, timeout_s: float = 10.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status = store.get(run_id)
        if status is not None and status.status != "running":
            return status
        time.sleep(0.01)
    raise AssertionError("run did not finish")


@pytest.fixture
def slot():
    return threading.BoundedSemaphore(1)


def states(log, **kw):
    return {s.name: s.state for s in stage_states(log, **kw)}


# --- stage states: every point of a run --------------------------------------------------------


def test_the_table_matches_the_compiled_graph():
    edges = {
        (e.source, e.target)
        for e in build_graph(placeholder_nodes()).get_graph().edges
        if e.source != "__start__" and e.target != "__end__"
    }
    expected = {(p, s) for s, ps in PREREQS.items() for p in ps}
    expected |= {("evaluate", n) for n in CHOSEN_AFTER_EVALUATE} | {("revise", "evaluate")}
    assert edges == expected
    assert set(STAGES) == set(PREREQS) | set(CHOSEN_AFTER_EVALUATE)


def test_states_through_a_run():
    assert states([]) == {
        "analyze_job": "running", "analyze_profile": "running",
        "retrieve_knowledge": "waiting", "analyze_gaps": "waiting", "plan_roadmap": "waiting",
        "interview_questions": "waiting", "evaluate": "waiting", "finalize": "waiting",
    }  # fmt: skip
    s = states(["analyze_profile", "analyze_job"])
    assert s["retrieve_knowledge"] == "running" and s["analyze_gaps"] == "waiting"
    s = states(["analyze_job", "analyze_profile", "retrieve_knowledge", "analyze_gaps"])
    assert s["plan_roadmap"] == s["interview_questions"] == "running"
    s = states(["analyze_job", "analyze_profile", "retrieve_knowledge", "analyze_gaps",
                "plan_roadmap", "interview_questions", "evaluate"])  # fmt: skip
    assert s["evaluate"] == "done" and s["finalize"] == "waiting"  # verdict unknown
    assert "revise" not in s


def test_revise_is_listed_once_it_ran_and_evaluate_runs_again():
    log = ["analyze_job", "analyze_profile", "retrieve_knowledge", "analyze_gaps",
           "plan_roadmap", "interview_questions", "evaluate", "revise"]  # fmt: skip
    s = states(log)
    assert s["revise"] == "done" and s["evaluate"] == "running"
    s = states([*log, "evaluate"])
    assert s["evaluate"] == "done"


def test_a_finished_run_shows_nothing_running():
    assert "running" not in states(["analyze_job"], finished=True).values()


# --- the store -----------------------------------------------------------------------------------


def test_start_returns_at_once_and_reports_progress(slot):
    gate = threading.Event()
    reached = threading.Event()

    def slow_gaps(state):
        reached.set()
        gate.wait(5)
        return {"gaps": []}

    store = RunStore(slot)
    run_id = store.start(data(), context=CTX, settings=SETTINGS,
                         impl=placeholder_nodes(analyze_gaps=slow_gaps))  # fmt: skip
    assert uuid.UUID(run_id).version == 4
    assert reached.wait(5)
    status = store.get(run_id)
    assert status.status == "running" and status.result is None
    s = {x.name: x.state for x in status.stages}
    assert s["retrieve_knowledge"] == "done" and s["analyze_gaps"] == "running"
    with pytest.raises(RunBusy):  # one at a time
        store.start(data(), context=CTX, settings=SETTINGS, impl=placeholder_nodes())
    gate.set()
    done = wait(store, run_id)
    assert done.status == "done" and done.result.status == "complete"
    assert slot._value == 1  # released


def test_a_refused_key_fails_with_its_own_fixed_text(slot, caplog):
    # run_workflow re-raises a refused key (NOT_A_FALLBACK) instead of falling back.
    def boom(state):
        raise voyageai.error.AuthenticationError("secret pa-key text")

    store = RunStore(slot)
    with caplog.at_level("DEBUG"):
        run_id = store.start(
            data(), context=CTX, settings=SETTINGS, impl=placeholder_nodes(retrieve_knowledge=boom)
        )
        done = wait(store, run_id)
    assert done.status == "failed" and done.error == KEY_REFUSED and done.result is None
    assert slot._value == 1
    assert "AuthenticationError" in caplog.text and "secret pa-key text" not in caplog.text


def test_a_failure_before_the_graph_is_failed_with_fixed_text(slot):
    bad = Settings(_env_file=None, workflow_max_revisions=1, workflow_time_budget_s=300)
    object.__setattr__(bad, "workflow_max_revisions", "two")  # run_workflow refuses it
    store = RunStore(slot)
    run_id = store.start(data(), context=CTX, settings=bad, impl=placeholder_nodes())
    done = wait(store, run_id)
    assert done.status == "failed" and done.error == FAILED
    assert slot._value == 1


def test_the_slot_is_free_once_the_run_shows_finished(slot):
    # Released before "done" is published, so a client can start the next run at once.
    store = RunStore(slot)
    for _ in range(5):
        run_id = store.start(data(), context=CTX, settings=SETTINGS, impl=placeholder_nodes())
        wait(store, run_id)
        assert slot._value == 1


def test_a_thread_that_cannot_start_leaves_no_record_and_frees_the_slot(slot, monkeypatch):
    def refuse(self):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading.Thread, "start", refuse)
    store = RunStore(slot)
    with pytest.raises(RuntimeError):
        store.start(data(), context=CTX, settings=SETTINGS, impl=placeholder_nodes())
    assert store._runs == {} and slot._value == 1


def test_finishing_logs_status_and_reason_only(slot, caplog):
    store = RunStore(slot)
    with caplog.at_level("INFO"):
        wait(store, store.start(data(), context=CTX, settings=SETTINGS, impl=placeholder_nodes()))
    assert "preparation run finished: complete, -," in caplog.text
    assert "Fernhill" not in caplog.text


def test_a_failing_stage_is_a_fallback_result_not_a_failed_run(slot):
    def boom(state):
        raise RuntimeError("stage broke")

    store = RunStore(slot)
    run_id = store.start(data(), context=CTX, settings=SETTINGS,
                         impl=placeholder_nodes(analyze_job=boom))  # fmt: skip
    done = wait(store, run_id)
    assert done.status == "done" and done.result.status == "fallback"


def test_records_never_hold_the_posting_or_profile(slot):
    store = RunStore(slot)
    run_id = store.start(data(), context=CTX, settings=SETTINGS, impl=placeholder_nodes())
    wait(store, run_id)
    record = store._runs[run_id]
    text = repr(vars(record).get("node_log")) + repr(record.error)
    assert "Fernhill" not in text
    assert not hasattr(record, "data") and not hasattr(record, "profile")


def test_unknown_malformed_and_expired_ids_are_none(slot):
    clock = Clock()
    store = RunStore(slot, clock=clock)
    assert store.get("not-a-uuid") is None
    assert store.get(str(uuid.uuid4())) is None
    run_id = store.start(data(), context=CTX, settings=SETTINGS, impl=placeholder_nodes())
    wait(store, run_id)
    clock.now += RUN_TTL_S + 1
    assert store.get(run_id) is None


def test_at_most_max_runs_are_kept(slot):
    store = RunStore(slot)
    ids = []
    for _ in range(MAX_RUNS + 3):
        ids.append(store.start(data(), context=CTX, settings=SETTINGS, impl=placeholder_nodes()))
        wait(store, ids[-1])
    assert len(store._runs) <= MAX_RUNS
    assert store.get(ids[0]) is None and store.get(ids[-1]) is not None


def test_the_run_thread_keeps_the_callers_tracing_context(slot):
    # copy_context: a run started inside a traced context traces; the default (off) does not.
    store = RunStore(slot)
    client = RecordingClient()
    with langsmith.tracing_context(enabled=True, client=client, project_name="test"):
        run_id = store.start(data(), context=CTX, settings=SETTINGS, impl=placeholder_nodes())
    wait(store, run_id)
    assert client.created  # the context was carried into the thread
    quiet = RecordingClient()
    with langsmith.tracing_context(enabled=False, client=quiet, project_name="test"):
        run_id = store.start(data(), context=CTX, settings=SETTINGS, impl=placeholder_nodes())
    wait(store, run_id)
    assert quiet.created == []


def test_progress_errors_never_break_a_run():
    from gradpath.workflows import run_workflow

    def bad(_log):
        raise RuntimeError("observer broke")

    result = run_workflow(SAMPLE_JD, profile(), context=CTX, max_revisions=0,
                          impl=placeholder_nodes(), on_step=bad)  # fmt: skip
    assert result.status == "complete"


# --- the API -------------------------------------------------------------------------------------


@pytest.fixture
def api(kb_service):
    store = RunStore(limits.CAREER)
    app = create_app(use_lifespan=False)
    app.dependency_overrides[get_retrieval] = lambda: kb_service
    app.dependency_overrides[get_extraction_model] = lambda: FakeChatModel()
    app.dependency_overrides[get_answer_model] = lambda: FakeChatModel()
    app.dependency_overrides[get_run_store] = lambda: store
    yield TestClient(app), store
    assert limits.CAREER._value == 1


def test_api_start_then_poll(api, monkeypatch):
    c, store = api
    real_start = store.start
    monkeypatch.setattr(
        store, "start", lambda d, **kw: real_start(d, **{**kw, "impl": placeholder_nodes()})
    )
    resp = c.post("/api/career/runs", json=data().model_dump())
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]
    wait(store, run_id)
    body = c.get(f"/api/career/runs/{run_id}").json()
    assert body["status"] == "done" and body["result"]["status"] == "complete"
    assert [s["name"] for s in body["stages"]][0] == "analyze_job"


def test_api_busy_and_not_found(api):
    c, _ = api
    assert limits.CAREER.acquire(blocking=False)
    try:
        resp = c.post("/api/career/runs", json=data().model_dump())
    finally:
        limits.CAREER.release()
    assert resp.status_code == 503 and "already in progress" in resp.json()["detail"]
    for bad in (str(uuid.uuid4()), "not-a-uuid"):
        resp = c.get(f"/api/career/runs/{bad}")
        assert resp.status_code == 404 and "expired" in resp.json()["detail"]
    assert c.get("/api/career/runs/../etc").status_code == 404  # never reaches a run lookup


def test_api_rejects_bad_input_before_starting(api):
    c, store = api
    resp = c.post("/api/career/runs", json={"job_description": "short", "profile": {}})
    assert resp.status_code == 422 and store._runs == {}

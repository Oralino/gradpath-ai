"""The demo recorder (T-018 step 2): fake services, a temp folder, no network."""

import json
from datetime import date

import pytest
from test_demo import DECISION, ask, job, plan

from gradpath.demo import load_library, record
from gradpath.demo.library import RECORDING
from gradpath.demo.record import SPECS, Services, Spec, find_secret, record_all, save
from gradpath.jobs import JobAnalysis
from gradpath.router.assist import AssistResponse
from gradpath.router.schemas import RouteDecision
from gradpath.workflows import CareerPrepResult

TODAY = date(2026, 11, 20)


@pytest.fixture
def fakes(monkeypatch):
    """Replace the real paths with canned results and count the calls."""
    calls = {"decide": 0, "respond": 0, "analyze": 0}
    workflow_decision = DECISION | {"route": "agentic_workflow", "kind": "job_preparation"}

    def decide(req, fast):
        calls["decide"] += 1
        if req.job_description and req.profile:
            return RouteDecision.model_validate(workflow_decision)
        if req.job_description:
            return RouteDecision.model_validate(
                workflow_decision | {"action": "needs_input", "missing": ["profile"]}
            )
        return RouteDecision.model_validate(DECISION)

    def respond(req, decision, **_):
        calls["respond"] += 1
        if decision.action == "needs_input":
            return AssistResponse(decision=decision, outcome="needs_input", message="Add it.")
        if decision.route == "agentic_workflow":
            result = CareerPrepResult.model_validate(plan()["result"])
            return AssistResponse(decision=decision, outcome="prepared", result=result)
        return AssistResponse.model_validate(ask()["response"])

    def analyze(*_):
        calls["analyze"] += 1
        return JobAnalysis.model_validate(job()["analysis"])

    monkeypatch.setattr(record, "decide", decide)
    monkeypatch.setattr(record, "respond", respond)
    monkeypatch.setattr(record, "analyze_job", analyze)
    return calls


def services() -> Services:
    return Services(retrieval=None, fast=None, smart=None, settings=None)  # type: ignore[arg-type]


def test_records_every_spec_and_the_library_loads_them(tmp_path, fakes):
    written = record_all(SPECS, services, tmp_path, today=TODAY, echo=lambda _: None)
    assert written == [s.id for s in SPECS]
    lib = load_library(tmp_path)
    assert len(lib) == len(SPECS)
    # One workflow run feeds both the workflow ask and the plan.
    assert fakes["respond"] == sum(s.kind == "ask" for s in SPECS)
    plan_rec = lib.get("plan-sample-backend")
    assert plan_rec.result == lib.get("ask-plan-workflow").response.result
    assert plan_rec.profile is not None and plan_rec.recorded_at == TODAY


def test_existing_files_are_kept_unless_forced(tmp_path, fakes):
    record_all(SPECS, services, tmp_path, today=TODAY, echo=lambda _: None)
    opened = []
    again = record_all(SPECS, lambda: opened.append(1) or services(), tmp_path, echo=lambda _: None)
    assert again == [] and opened == []  # nothing re-run, no services opened
    forced = record_all(SPECS[:1], services, tmp_path, force=True, echo=lambda _: None)
    assert forced == [SPECS[0].id]


def test_a_plan_alone_reuses_the_saved_workflow_ask(tmp_path, fakes):
    by_id = {s.id: s for s in SPECS}
    record_all((by_id["ask-plan-workflow"],), services, tmp_path, echo=lambda _: None)
    assert not (tmp_path / "plan-sample-backend.json").exists()
    before, opened = dict(fakes), []
    record_all(
        (by_id["plan-sample-backend"],), lambda: opened.append(1) or services(), tmp_path,
        echo=lambda _: None,
    )  # fmt: skip
    assert fakes == before and opened == []  # no model call, no services opened
    plan_rec = load_library(tmp_path).get("plan-sample-backend")
    assert plan_rec.result == load_library(tmp_path).get("ask-plan-workflow").response.result


def test_a_wrong_route_is_refused_before_anything_runs(tmp_path, fakes, monkeypatch):
    monkeypatch.setattr(record, "decide", lambda req, fast: RouteDecision.model_validate(DECISION))
    workflow_ask = next(s for s in SPECS if s.id == "ask-plan-workflow")
    with pytest.raises(ValueError, match="expected agentic_workflow/prepared"):
        record_all((workflow_ask,), services, tmp_path, echo=lambda _: None)
    assert fakes["respond"] == 0 and list(tmp_path.iterdir()) == []


def test_a_corrupt_file_is_replaced(tmp_path, fakes):
    (tmp_path / "ask-multicolumn-indexes.json").write_text("{broken", encoding="utf-8")
    written = record_all(SPECS[:1], services, tmp_path, echo=lambda _: None)
    assert written == ["ask-multicolumn-indexes"] and len(load_library(tmp_path)) == 1


def test_forcing_the_workflow_ask_rebuilds_or_flags_its_plan(tmp_path, fakes):
    record_all(SPECS, services, tmp_path, echo=lambda _: None)
    by_id = {s.id: s for s in SPECS}
    pair = (by_id["ask-plan-workflow"], by_id["plan-sample-backend"])
    assert record_all(pair, services, tmp_path, force=False, echo=lambda _: None) == []
    out: list[str] = []
    record_all(pair[:1], services, tmp_path, force=True, echo=out.append)
    assert any("plan-sample-backend reuses ask-plan-workflow" in line for line in out)
    # Forcing the ask with the plan in the same run rebuilds the plan without --force on it.
    pair_ids = record_all(pair, services, tmp_path, force=True, echo=lambda _: None)
    assert pair_ids == ["ask-plan-workflow", "plan-sample-backend"]


def test_a_plan_without_its_workflow_ask_is_refused(tmp_path, fakes):
    lonely = Spec("plan-x", "plan", "x", "x", with_job=True, with_profile=True, uses="ask-none")
    with pytest.raises(ValueError, match="needs a workflow result"):
        record_all((lonely,), services, tmp_path, echo=lambda _: None)


@pytest.mark.parametrize(
    "leak",
    [
        "write to alex.real@example.com",
        "call 555-123-4567",
        "sk-ant-api03-" + "x" * 30,
        "pa-" + "y" * 40,
        "lsv2_pt_" + "0" * 32,
    ],
)
def test_a_recording_with_contact_details_or_keys_is_refused(tmp_path, leak):
    data = ask()
    data["response"]["answer"]["answer"] = f"An index helps. {leak}"
    with pytest.raises(ValueError, match="refused"):
        save(RECORDING.validate_python(data), tmp_path)
    assert list(tmp_path.iterdir()) == []  # nothing written, not even a temp file


def test_a_local_path_is_refused(tmp_path):
    from gradpath.config import REPO_ROOT

    for leak in [str(REPO_ROOT), str(REPO_ROOT).replace("\\", "/"), r"C:\Users\someone\x"]:
        data = ask()
        data["response"]["answer"]["answer"] = f"Failed at {leak}"
        with pytest.raises(ValueError, match="a local path"):
            save(RECORDING.validate_python(data), tmp_path)


@pytest.mark.parametrize(
    "fine",
    [
        "recorded 2026-11-20, chunk postgresql-indexes:3:1, score 0.6123",
        "see https://www.postgresql.org/docs/current/indexes-multicolumn.html",
        "use @app.get('/') and git checkout -b task-1234",
    ],
)
def test_ordinary_content_passes_the_scan(fine):
    assert find_secret(fine) is None


def test_the_committed_recordings_pass_the_scan():
    from gradpath.config import REPO_ROOT

    files = sorted((REPO_ROOT / "demo_runs").glob("*.json"))
    assert files, "demo_runs/ has no recordings"
    for f in files:
        assert find_secret(f.read_text(encoding="utf-8")) is None, f.name


def test_the_sample_inputs_are_clean_and_fictional():
    job_text, profile = record.sample_inputs()
    assert find_secret(job_text) is None
    assert find_secret(profile.model_dump_json()) is None
    assert "Fictional" in (profile.note or "")


def test_spec_ids_are_unique_and_valid():
    ids = [s.id for s in SPECS]
    assert len(ids) == len(set(ids))
    for s in SPECS:
        # Valid as a recording id (same pattern the library enforces).
        RECORDING.validate_python(ask(s.id))
        assert s.uses is None or s.uses in ids[: ids.index(s.id)]


def test_saved_file_is_plain_utf8_json(tmp_path):
    path = save(RECORDING.validate_python(ask()), tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["id"] == "ask-sql-index"
    assert not list(tmp_path.glob("*.tmp"))


# --- T-018 step 11: failed writes and the command-line entry point ---


def test_a_failed_write_leaves_no_temp_file_and_keeps_the_old_one(tmp_path, monkeypatch):
    first = save(RECORDING.validate_python(ask()), tmp_path)
    before = first.read_text(encoding="utf-8")

    def broken_replace(self, target):
        raise OSError("disk full")

    monkeypatch.setattr(type(first), "replace", broken_replace)
    with pytest.raises(OSError):
        save(RECORDING.validate_python(ask()), tmp_path)
    assert not list(tmp_path.glob("*.tmp"))
    assert first.read_text(encoding="utf-8") == before


def test_a_leftover_temp_file_is_ignored_and_overwritten(tmp_path):
    (tmp_path / "ask-sql-index.json.tmp").write_text("{half a fi", encoding="utf-8")
    assert len(load_library(tmp_path)) == 0  # the library reads *.json only
    save(RECORDING.validate_python(ask()), tmp_path)
    assert not list(tmp_path.glob("*.tmp"))
    assert load_library(tmp_path).get("ask-sql-index") is not None


def test_main_refuses_an_unknown_id_before_opening_anything(monkeypatch):
    import gradpath.retrieval

    def no_services():
        raise AssertionError("services opened for a refused command")

    monkeypatch.setattr(gradpath.retrieval, "get_retrieval_service", no_services)
    monkeypatch.setattr("sys.argv", ["record", "--only", "no-such-id"])
    with pytest.raises(SystemExit) as exc:
        record.main()
    assert exc.value.code == 2


def test_main_closes_qdrant_when_recording_fails(monkeypatch):
    import gradpath.providers
    import gradpath.retrieval

    closed = []

    class Client:
        def close(self):
            closed.append(True)

    class Store:
        client = Client()

    class Retrieval:
        store = Store()

    monkeypatch.setattr(gradpath.retrieval, "get_retrieval_service", lambda: Retrieval())
    monkeypatch.setattr(gradpath.providers, "get_chat_model", lambda tier: None)

    def failing_record_all(specs, open_services, folder, force):
        open_services()
        raise RuntimeError("model down")

    monkeypatch.setattr(record, "record_all", failing_record_all)
    monkeypatch.setattr("sys.argv", ["record", "--only", SPECS[0].id])
    with pytest.raises(RuntimeError):
        record.main()
    assert closed == [True]

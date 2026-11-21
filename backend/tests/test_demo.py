"""Demo mode (T-018): recordings, the demo routes, the mode guard, and starting with no keys."""

import json
import logging
from datetime import date

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from gradpath.api import deps
from gradpath.api import main as main_module
from gradpath.api.main import create_app
from gradpath.config import REPO_ROOT, Settings
from gradpath.demo import DemoLibrary, load_library
from gradpath.demo.library import MAX_RECORDING_BYTES, RECORDING

JD = "Backend engineer, new grad. Build REST APIs in Python, write SQL, use Git daily. " * 2
SECRET_TEXT = "a-posting-line-that-must-not-reach-the-logs"
DECISION = {
    "route": "traditional_rag",
    "action": "run",
    "kind": "knowledge_question",
    "missing": [],
    "reason": "A focused question.",
    "requires_user_profile": False,
    "requires_multi_step_workflow": False,
    "decided_by": "rules",
}


def ask(rid="ask-sql-index", **extra) -> dict:
    return {
        "id": rid,
        "kind": "ask",
        "title": "What is a SQL index?",
        "recorded_at": "2026-11-20",
        "message": "What is a SQL index?",
        "response": {
            "decision": DECISION,
            "outcome": "answered",
            "answer": {
                "question": "What is a SQL index?",
                "status": "answered",
                "answer": "An index speeds up lookups [1].",
                "citations": [],
            },
        },
        **extra,
    }


def job(rid="job-sample") -> dict:
    return {
        "id": rid,
        "kind": "job",
        "title": "Sample backend posting",
        "recorded_at": "2026-11-20",
        "job_description": JD,
        "analysis": {
            "title": "Backend engineer",
            "seniority": "new_grad",
            "responsibilities": [],
            "overview": None,
            "requirements": [],
            "stats": {},
        },
    }


def plan(rid="plan-sample") -> dict:
    return {
        "id": rid,
        "kind": "plan",
        "title": "Sample plan",
        "recorded_at": "2026-11-20",
        "job_description": JD,
        "profile": {"skills": ["SQL"], "weekly_hours": 8},
        "result": {
            "status": "complete",
            "job": None,
            "gaps": [],
            "roadmap": [],
            "interview_questions": [],
            "unresolved_issues": [],
            "revisions_used": 0,
            "errors": [],
            "node_log": ["finalize"],
        },
    }


def write(folder, name, data) -> None:
    (folder / name).write_text(json.dumps(data), encoding="utf-8")


def library() -> DemoLibrary:
    return DemoLibrary([RECORDING.validate_python(d) for d in (plan(), job(), ask())])


def use_mode(monkeypatch, mode: str) -> None:
    monkeypatch.setattr(deps, "get_settings", lambda: Settings(_env_file=None, app_mode=mode))


# --- the library ------------------------------------------------------------------------------


def test_loads_each_kind_and_lists_them_in_screen_order(tmp_path):
    write(tmp_path, "b.json", plan())
    write(tmp_path, "a.json", job())
    write(tmp_path, "c.json", ask())
    lib = load_library(tmp_path)
    assert [s.kind for s in lib.summaries()] == ["ask", "job", "plan"]
    assert lib.get("job-sample").analysis.title == "Backend engineer"
    assert lib.summaries()[0].recorded_at == date(2026, 11, 20)


def test_bad_files_are_skipped_and_logged_without_their_content(tmp_path, caplog):
    write(tmp_path, "0-good.json", ask())  # sorts first, so it wins the id
    write(tmp_path, "extra-field.json", ask("other", note=SECRET_TEXT))
    write(tmp_path, "duplicate.json", ask())  # same id as 0-good.json
    write(tmp_path, "started.json", ask("started") | {
        "response": {"decision": DECISION, "outcome": "started", "run_id": "abc"}
    })  # fmt: skip
    write(tmp_path, "bad-id.json", ask("../../etc/passwd"))
    (tmp_path / "broken.json").write_text("{" + SECRET_TEXT, encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    (tmp_path / "huge.json").write_bytes(b" " * (MAX_RECORDING_BYTES + 1))
    with caplog.at_level(logging.INFO, logger="gradpath.demo.library"):
        lib = load_library(tmp_path)
    assert len(lib) == 1 and lib.get("ask-sql-index") is not None
    logged = caplog.text
    for name in ["extra-field", "duplicate", "started", "bad-id", "broken", "huge"]:
        assert f"{name}.json skipped" in logged
    assert SECRET_TEXT not in logged and "notes.txt" not in logged


def test_a_missing_folder_gives_an_empty_library(tmp_path):
    assert len(load_library(tmp_path / "nope")) == 0


def test_duplicate_ids_are_refused_when_built_directly():
    rec = RECORDING.validate_python(ask())
    with pytest.raises(ValueError):
        DemoLibrary([rec, rec])


def test_every_committed_recording_is_valid():
    """Drift check: each file in `demo_runs/` still matches the API's response models."""
    folder = REPO_ROOT / "demo_runs"
    files = sorted(folder.glob("*.json"))
    assert files, "demo_runs/ has no recordings"
    assert len(load_library(folder)) == len(files)


def test_links_are_skipped(tmp_path, caplog):
    outside = tmp_path / "outside.json"
    write(tmp_path, "outside.json", ask())
    folder = tmp_path / "runs"
    folder.mkdir()
    try:
        (folder / "link.json").symlink_to(outside)
    except OSError:
        pytest.skip("this system can't create symlinks without extra rights")
    assert len(load_library(folder)) == 0
    assert "link.json skipped (not a plain file)" in caplog.text


def test_an_unreadable_file_is_skipped_not_fatal(tmp_path, monkeypatch, caplog):
    write(tmp_path, "a.json", ask())
    write(tmp_path, "b.json", job())
    real = type(tmp_path).read_bytes

    def flaky(self):
        if self.name == "a.json":
            raise PermissionError("denied")
        return real(self)

    monkeypatch.setattr(type(tmp_path), "read_bytes", flaky)
    lib = load_library(tmp_path)
    assert len(lib) == 1 and lib.get("job-sample") is not None
    assert "a.json skipped (PermissionError)" in caplog.text


# --- the demo routes --------------------------------------------------------------------------


def demo_client(lib: DemoLibrary | None = None) -> TestClient:
    app = create_app(use_lifespan=False)
    app.state.demo = lib if lib is not None else library()
    return TestClient(app)


@pytest.mark.parametrize("mode", ["local", "demo", "live"])
def test_demo_routes_are_open_in_every_mode(monkeypatch, mode):
    use_mode(monkeypatch, mode)
    c = demo_client()
    listed = c.get("/api/demo").json()
    assert [r["id"] for r in listed] == ["ask-sql-index", "job-sample", "plan-sample"]
    assert set(listed[0]) == {"id", "kind", "title", "summary", "recorded_at"}  # no content
    one = c.get("/api/demo/plan-sample")
    assert one.status_code == 200 and one.json()["result"]["status"] == "complete"


@pytest.mark.parametrize(
    "path",
    ["/api/demo/unknown", "/api/demo/..%2F..%2F.env", "/api/demo/%2e%2e", "/api/demo/a.json"],
)
def test_unknown_ids_are_404_without_touching_files(path):
    resp = demo_client().get(path)
    assert resp.status_code == 404
    assert ".env" not in resp.text and "demo_runs" not in resp.text


# --- the mode guard ---------------------------------------------------------------------------

MODEL_ROUTES = [
    ("post", "/api/chat", "/api/chat"),
    ("post", "/api/jobs/analyze", "/api/jobs/analyze"),
    ("post", "/api/career/prepare", "/api/career/prepare"),
    ("post", "/api/career/runs", "/api/career/runs"),
    ("get", "/api/career/runs/{run_id}", "/api/career/runs/abc"),
    ("post", "/api/assist", "/api/assist"),
    ("post", "/api/profile/from-resume", "/api/profile/from-resume"),
]
OPEN_ROUTES = {
    ("get", "/api/health"),
    ("get", "/api/demo"),
    ("get", "/api/demo/{recording_id}"),
    ("post", "/api/search"),  # no model call (T-018 step 4)
}


def test_every_route_is_either_open_or_in_the_guard_test():
    """Route inventory: a new route fails here until it is listed, so it can't skip the guard
    test below (which proves each listed model route refuses outside local mode)."""
    schema = create_app(use_lifespan=False).openapi()
    found = {(m, p) for p, ops in schema["paths"].items() for m in ops}
    assert found == OPEN_ROUTES | {(m, p) for m, p, _ in MODEL_ROUTES}


@pytest.mark.parametrize("mode", ["demo", "live"])
@pytest.mark.parametrize(("method", "template", "path"), MODEL_ROUTES)
def test_model_routes_are_refused_outside_local_mode(monkeypatch, mode, method, template, path):
    use_mode(monkeypatch, mode)

    def must_not_run():
        raise AssertionError("a refused request must not build models or open retrieval")

    app = create_app(use_lifespan=False)
    for dep in (deps.get_retrieval, deps.get_answer_model, deps.get_extraction_model):
        app.dependency_overrides[dep] = must_not_run
    # An invalid body too: the guard answers before validation, so nothing is echoed back.
    resp = getattr(TestClient(app), method)(path, **({"json": {}} if method == "post" else {}))
    assert resp.status_code == 403
    assert resp.json() == {"detail": deps.MODEL_ROUTES_OFF}


def test_the_default_mode_is_demo(monkeypatch):
    """Deny by default rests on this: a server with no APP_MODE set serves recordings only."""
    monkeypatch.delenv("APP_MODE", raising=False)
    assert Settings(_env_file=None).app_mode == "demo"


@pytest.mark.parametrize("mode", ["demo", "live", "staging", ""])
def test_the_guard_fails_closed_for_anything_but_local(monkeypatch, mode):
    """Even a mode value that validation would reject (a future or mistyped mode) is refused."""
    monkeypatch.setattr(deps, "get_settings", lambda: Settings.model_construct(app_mode=mode))
    with pytest.raises(HTTPException) as err:
        deps.require_model_routes()
    assert err.value.status_code == 403


# --- starting the app -------------------------------------------------------------------------

KEY_VARS = ["ANTHROPIC_API_KEY", "VOYAGE_API_KEY", "LANGSMITH_API_KEY", "QDRANT_API_KEY"]


def no_key_settings(tmp_path, mode: str) -> Settings:
    return Settings(
        _env_file=None,
        app_mode=mode,
        anthropic_api_key=None,
        voyage_api_key=None,
        langsmith_api_key=None,
        qdrant_api_key=None,
        langsmith_tracing=False,
        demo_runs_path=str(tmp_path),
    )


def test_demo_mode_starts_and_serves_with_no_keys(tmp_path, monkeypatch):
    for var in KEY_VARS:
        monkeypatch.delenv(var, raising=False)
    write(tmp_path, "ask.json", ask())
    s = no_key_settings(tmp_path, "demo")
    monkeypatch.setattr(main_module, "get_settings", lambda: s)
    monkeypatch.setattr(deps, "get_settings", lambda: s)

    def must_not_open(*_):
        raise AssertionError("demo mode must not open Voyage or Qdrant")

    monkeypatch.setattr(main_module, "get_retrieval_service", must_not_open)
    with TestClient(create_app()) as c:  # runs the lifespan
        assert c.get("/api/health").json()["app_mode"] == "demo"
        assert [r["id"] for r in c.get("/api/demo").json()] == ["ask-sql-index"]
        assert c.post("/api/chat", json={"question": "What is an index?"}).status_code == 403


def test_local_mode_still_opens_and_closes_retrieval(tmp_path, monkeypatch):
    s = no_key_settings(tmp_path, "local")
    monkeypatch.setattr(main_module, "get_settings", lambda: s)
    closed = []

    class FakeRetrieval:
        def __init__(self, settings=None):
            self.settings = settings

        class store:  # noqa: N801  (mirrors RetrievalService.store.client)
            class client:  # noqa: N801
                @staticmethod
                def close():
                    closed.append(True)

    monkeypatch.setattr(main_module, "get_retrieval_service", FakeRetrieval)
    with TestClient(create_app()) as c:
        assert isinstance(c.app.state.retrieval, FakeRetrieval)
        assert len(c.app.state.demo) == 0
    assert closed == [True]

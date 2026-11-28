"""Relay routes (T-029 step 2): start, poll, reply; the sign-in gate, run ownership and limits.

The browser is a loop over the real HTTP routes that answers each prompt with a canned reply by
schema, as the page will with a local model. No model, Voyage or network call is made.
"""

import json
import re
import threading
import time
from collections.abc import Callable

import pytest
from conftest import placeholder_nodes, plain
from fastapi.testclient import TestClient
from test_visitor_key import LIVE, PASS, session_for
from test_workflow_graph import SAMPLE_JD, profile

from gradpath.api import auth, deps, ratelimit, relay
from gradpath.api.deps import get_retrieval
from gradpath.api.main import create_app
from gradpath.api.relay import get_relay_store
from gradpath.config import Settings
from gradpath.jobs import JobAnalysis
from gradpath.workflows.graph import run_workflow
from gradpath.workflows.runs import RunStore

LOCAL = Settings(_env_file=None, app_mode="local", relay_idle_timeout_s=10)
KB_ID = re.compile(r'<evidence id="([^"]+)"')


def canned(prompt: dict) -> str | None:
    """A local model that answers every schema the app sends with something valid (or not)."""
    title = (prompt.get("json_schema") or {}).get("title")
    text = prompt["messages"][-1]["content"]
    if title == "ModelAnswer":
        ids = KB_ID.findall(text)[:1]
        return json.dumps({"answer": "An index speeds up lookups.", "cited_chunk_ids": ids,
                           "insufficient_evidence": False})  # fmt: skip
    if title == "JobExtraction":
        return json.dumps({"title": "Backend Engineer", "seniority": "new_grad",
                           "responsibilities": ["Build APIs"], "requirements": []})  # fmt: skip
    return "<think>no idea</think>not json"  # e.g. the router's classifier: it falls back


def first_prompt(c: TestClient, run_id: str, headers: dict | None = None) -> str:
    """Poll until the run has a waiting prompt; return its id (fails instead of hanging)."""
    end = time.monotonic() + 5
    while time.monotonic() < end:
        status = c.get(f"/api/relay/runs/{run_id}", headers=headers).json()
        assert status["status"] == "running", status
        if status["prompts"]:
            return status["prompts"][0]["id"]
        time.sleep(0.01)
    raise AssertionError("no prompt arrived")


def finish(store: RunStore, run_id: str, timeout_s: float = 5) -> None:
    """Wait for the run to end without polling it (a poll would count as the browser)."""
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if store._runs[run_id].status != "running":
            return
        time.sleep(0.01)
    raise AssertionError("run did not end")


def drive(c: TestClient, run_id: str, answer: Callable[[dict], str | None] = canned,
          headers: dict | None = None, timeout_s: float = 10) -> dict:  # fmt: skip
    """Poll the run and answer its prompts until it finishes; return the final status."""
    answered: set[str] = set()
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        status = c.get(f"/api/relay/runs/{run_id}", headers=headers).json()
        if status["status"] != "running":
            return status
        for p in status["prompts"]:
            if p["id"] in answered:
                continue
            answered.add(p["id"])
            text = answer(p)
            body = {"prompt_id": p["id"], "failed": True} if text is None else {
                "prompt_id": p["id"], "text": text}  # fmt: skip
            r = c.post(f"/api/relay/runs/{run_id}/replies", json=body, headers=headers)
            assert r.status_code == 204, r.text
        time.sleep(0.01)
    raise AssertionError("relay run did not finish")


@pytest.fixture
def store():
    s = RunStore(threading.BoundedSemaphore(2))
    yield s
    for run in s._runs.values():  # don't leave waiting threads behind
        if run.relay is not None:
            run.relay.close()


def make_app(kb_service, store) -> TestClient:
    app = create_app(use_lifespan=False)
    app.dependency_overrides[get_retrieval] = lambda: kb_service
    app.dependency_overrides[get_relay_store] = lambda: store
    return TestClient(app)


@pytest.fixture
def local(monkeypatch, kb_service, store):
    monkeypatch.setattr(deps, "get_settings", lambda: LOCAL)
    monkeypatch.setattr(relay, "get_settings", lambda: LOCAL)
    return make_app(kb_service, store)


LIVE_RELAY = LIVE.model_copy(update={"relay_idle_timeout_s": 10})


@pytest.fixture
def live(monkeypatch, kb_service, store):
    monkeypatch.setattr(deps, "get_settings", lambda: LIVE_RELAY)
    monkeypatch.setattr(relay, "get_settings", lambda: LIVE_RELAY)
    return make_app(kb_service, store)


JOB_BODY = {"kind": "job", "request": {"job_description": SAMPLE_JD}}
JOB_RESULT = JobAnalysis(
    title="t", seniority="unknown", responsibilities=[], overview=None, requirements=[], stats={}
)


def plan_body() -> dict:
    return {"kind": "plan", "request": {"job_description": SAMPLE_JD,
            "profile": profile().model_dump(mode="json")}}  # fmt: skip


# --- each kind, end to end -------------------------------------------------------------------


def test_an_ask_runs_through_the_browser(local):
    r = local.post("/api/relay/runs", json={"kind": "ask",
                   "request": {"message": "What is an index in sqlite?"}})  # fmt: skip
    assert r.status_code == 202
    done = drive(local, r.json()["run_id"])
    assert done["status"] == "done" and done["kind"] == "ask"
    assert done["ask"]["outcome"] == "answered"
    assert done["ask"]["answer"]["answer"] == "An index speeds up lookups."
    assert done["job"] is None and done["plan"] is None and done["prompts"] == []


def test_a_job_analysis_runs_through_the_browser(local):
    r = local.post("/api/relay/runs", json=JOB_BODY)
    done = drive(local, r.json()["run_id"])
    assert done["status"] == "done" and done["job"]["title"] == "Backend Engineer"


def test_a_plan_reports_stages_and_uses_the_relay_budget(local, monkeypatch):
    seen: dict = {}

    def placeholder_run(*args, **kwargs):
        seen.update(kwargs)
        assert kwargs["context"].fast_llm._llm_type == "browser-relay"
        return run_workflow(*args, **kwargs, impl=placeholder_nodes())

    monkeypatch.setattr(relay, "run_workflow", placeholder_run)
    r = local.post("/api/relay/runs", json=plan_body())
    done = drive(local, r.json()["run_id"])
    assert done["status"] == "done" and done["plan"]["status"] == "complete"
    assert done["stages"] and "running" not in {s["state"] for s in done["stages"]}
    assert seen["time_budget_s"] == LOCAL.relay_time_budget_s  # not the Claude budget


def test_a_model_failure_fails_the_run_with_fixed_text(local):
    r = local.post("/api/relay/runs", json=JOB_BODY)
    done = drive(local, r.json()["run_id"], answer=lambda p: None)
    assert done["status"] == "failed" and done["error"] == relay.RELAY_MODEL_FAILED


# --- the gate, ownership and limits (live mode) ---------------------------------------------


def test_live_needs_a_sign_in_but_no_key(live):
    assert local_start(live, headers={}).status_code == 401
    r = local_start(live, headers=PASS)  # no X-Anthropic-Key at all
    assert r.status_code == 202


def local_start(c: TestClient, headers: dict):
    return c.post("/api/relay/runs", json=plan_body(), headers=headers)


def other_user(github_id: int = 777) -> dict:
    return {"Cookie": f"{auth.SESSION_COOKIE}={session_for(github_id, 'visitor-two')}"}


def test_another_user_cannot_see_or_answer_a_run(live):
    run_id = live.post("/api/relay/runs", json=JOB_BODY, headers=PASS).json()["run_id"]
    prompt_id = first_prompt(live, run_id, PASS)
    poll = live.get(f"/api/relay/runs/{run_id}", headers=other_user())
    assert poll.status_code == 404 and plain(poll.json())["detail"] == relay.NOT_FOUND
    reply = live.post(f"/api/relay/runs/{run_id}/replies", headers=other_user(),
                      json={"prompt_id": prompt_id, "text": "{}"})  # fmt: skip
    assert reply.status_code == 404


def test_one_relay_run_per_user_and_two_on_the_server(live):
    assert local_start(live, PASS).status_code == 202
    second = local_start(live, PASS)
    assert second.status_code == 409 and plain(second.json())["detail"] == relay.OWNER_BUSY
    assert local_start(live, other_user(777)).status_code == 202
    third = local_start(live, other_user(778))
    assert third.status_code == 503 and plain(third.json())["detail"] == relay.RELAY_BUSY


def test_replies_are_checked(local):
    run_id = local.post("/api/relay/runs", json=JOB_BODY).json()["run_id"]
    prompt_id = first_prompt(local, run_id)
    url = f"/api/relay/runs/{run_id}/replies"
    both = local.post(url, json={"prompt_id": prompt_id, "text": "x", "failed": True})
    assert both.status_code == 422
    assert local.post(url, json={"prompt_id": "not-a-uuid", "text": "x"}).status_code == 422
    huge = local.post(url, json={"prompt_id": prompt_id, "text": "x" * 20_001})
    assert huge.status_code == 422
    unknown = local.post(url, json={"prompt_id": "00000000-0000-4000-8000-000000000000",
                                    "text": "x"})  # fmt: skip
    assert unknown.status_code == 404 and plain(unknown.json())["detail"] == relay.PROMPT_GONE
    assert local.post(url, json={"prompt_id": prompt_id, "text": "x"}).status_code == 204
    again = local.post(url, json={"prompt_id": prompt_id, "text": "x"})
    assert again.status_code == 404  # one reply per prompt


def test_unknown_and_malformed_run_ids_look_the_same(local):
    for run_id in ("00000000-0000-4000-8000-000000000000", "abc"):
        r = local.get(f"/api/relay/runs/{run_id}")
        assert r.status_code == 404 and plain(r.json())["detail"] == relay.NOT_FOUND


# --- stopping, the quiet browser, and the error texts -------------------------------------


def test_cancel_stops_the_run_and_frees_the_slot(local, store):
    run_id = local.post("/api/relay/runs", json=JOB_BODY).json()["run_id"]
    first_prompt(local, run_id)
    assert local.delete(f"/api/relay/runs/{run_id}").status_code == 204
    finish(store, run_id)
    done = local.get(f"/api/relay/runs/{run_id}").json()
    assert done["status"] == "failed" and done["error"] == relay.RELAY_STOPPED
    assert store.refusal(None) is None  # the slot is free again
    assert local.delete("/api/relay/runs/00000000-0000-4000-8000-000000000000").status_code == 404


def test_a_quiet_browser_stops_the_run(monkeypatch, kb_service, store):
    quick = LOCAL.model_copy(update={"relay_idle_timeout_s": 0.3})  # below the settings floor
    monkeypatch.setattr(deps, "get_settings", lambda: quick)
    monkeypatch.setattr(relay, "get_settings", lambda: quick)
    c = make_app(kb_service, store)
    run_id = c.post("/api/relay/runs", json=JOB_BODY).json()["run_id"]
    finish(store, run_id)  # nobody polls: a closed tab
    done = c.get(f"/api/relay/runs/{run_id}").json()
    assert done["status"] == "failed" and done["error"] == relay.RELAY_GONE


def test_every_relay_failure_has_fixed_text():
    from gradpath.providers.relay import (
        RelayBadOutput,
        RelayCancelled,
        RelayClosed,
        RelayLimit,
        RelayModelFailed,
        RelayTimeout,
    )

    texts = {
        RelayTimeout: relay.RELAY_TIMED_OUT,
        RelayCancelled: relay.RELAY_STOPPED,
        RelayClosed: relay.RELAY_GONE,
        RelayModelFailed: relay.RELAY_MODEL_FAILED,
        RelayLimit: relay.RELAY_TOO_MANY,
        RelayBadOutput: relay.RELAY_UNREADABLE,
    }
    for cls, text in texts.items():
        assert relay.describe(cls("secret detail")) == text
    assert relay.describe(RuntimeError("x")) is None  # the generic failure text


def test_one_per_owner_refusal_keeps_the_slot(store):
    gate = threading.Event()
    run_id = store.start_task(lambda progress: gate.wait(2) or JOB_RESULT, owner="a",
                              one_per_owner=True)  # fmt: skip
    with pytest.raises(relay.OwnerBusy):
        store.start_task(lambda progress: JOB_RESULT, owner="a", one_per_owner=True)
    other = store.start_task(lambda progress: JOB_RESULT, owner="b", one_per_owner=True)
    gate.set()
    finish(store, run_id)
    finish(store, other)
    assert store.refusal("a", one_per_owner=True) is None


# --- rate limits (on here: live mode for `ratelimit` too) -----------------------------------


@pytest.fixture
def limited(monkeypatch, live):
    monkeypatch.setattr(ratelimit, "get_settings", lambda: LIVE_RELAY)
    return live


def user_events(bucket: str, github_id: int = 4242) -> int:
    return len(ratelimit.LIMITER._events.get((bucket, f"gh:{github_id}"), ()))


def test_a_refused_start_costs_no_quota(limited, store):
    assert local_start(limited, PASS).status_code == 202
    for _ in range(4):  # double clicks while the first run is going
        assert local_start(limited, PASS).status_code == 409
    assert user_events("workflow") == 1


def test_an_ask_that_becomes_a_plan_counts_as_a_plan(limited, monkeypatch):
    def placeholder_run(*args, **kwargs):
        return run_workflow(*args, **kwargs, impl=placeholder_nodes())

    monkeypatch.setattr(relay, "run_workflow", placeholder_run)
    ask = {
        "message": "Build me a study plan for this job",
        "job_description": SAMPLE_JD,
        "profile": profile().model_dump(mode="json"),
    }
    body = {"kind": "ask", "request": ask}
    r = limited.post("/api/relay/runs", json=body, headers=PASS)
    done = drive(limited, r.json()["run_id"], headers=PASS)
    assert done["ask"]["outcome"] == "prepared" and done["stages"]
    assert (user_events("model"), user_events("workflow")) == (1, 1)


def test_polls_have_their_own_limit(limited, monkeypatch):
    monkeypatch.setitem(ratelimit.PER_USER, "relay", (ratelimit.Window(2, ratelimit.MINUTE),))
    run_id = limited.post("/api/relay/runs", json=JOB_BODY, headers=PASS).json()["run_id"]
    url = f"/api/relay/runs/{run_id}"
    assert [limited.get(url, headers=PASS).status_code for _ in range(3)] == [200, 200, 429]

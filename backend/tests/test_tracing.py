"""Tracing rules (always-hard area): when anything may reach LangSmith, and what it may contain.

No network: runs are captured by a recording client that never uploads.
"""

import asyncio
import contextvars

import langsmith
import pytest
from langchain_anthropic import ChatAnthropic
from langsmith import Client
from pydantic import SecretStr

from gradpath.config import Settings
from gradpath.providers import ChatClaudeCode, FakeChatModel, get_chat_model
from gradpath.rag.answer import answer_question
from gradpath.retrieval.service import trace_summary
from gradpath.tracing import configure_tracing, decide, is_tracing, redact

FAKE_LS_KEY = "lsv2_pt_" + "0" * 32 + "_test"


TRACING_DEFAULTS = dict(
    langsmith_tracing=False,
    langsmith_api_key=None,
    langsmith_endpoint="http://127.0.0.1:9",  # never a real service, even if a test slips
    app_mode="local",
)


def settings(**overrides) -> Settings:
    """Settings that ignore both .env and the shell: explicit values beat environment variables."""
    return Settings(_env_file=None, **(TRACING_DEFAULTS | overrides))


# --- the on/off rule --------------------------------------------------------------------------


def test_off_by_default_and_without_a_key():
    assert not decide(settings()).enabled
    assert not decide(settings(langsmith_tracing=True)).enabled
    assert not decide(settings(langsmith_tracing=True, langsmith_api_key=" ")).enabled


@pytest.mark.parametrize("mode", ["live", "demo"])
def test_the_deployed_modes_never_trace(mode):
    status = decide(settings(langsmith_tracing=True, langsmith_api_key=FAKE_LS_KEY, app_mode=mode))
    assert not status.enabled
    assert f"{mode} mode" in status.reason


def test_on_only_when_asked_with_a_key_in_local_mode():
    assert decide(settings(langsmith_tracing=True, langsmith_api_key=FAKE_LS_KEY)).enabled


@pytest.fixture
def fresh_env_cache():
    """langsmith caches env lookups; clear it so monkeypatched variables are seen, and after."""
    langsmith.utils.get_env_var.cache_clear()
    yield
    langsmith.utils.get_env_var.cache_clear()


def test_explicit_off_beats_a_stray_shell_variable(monkeypatch, fresh_env_cache):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    langsmith.configure(enabled=None)  # nothing set in code: the env var alone would win
    assert is_tracing()
    configure_tracing(settings())  # settings say off
    assert not is_tracing()


def test_extra_upload_destinations_refuse_tracing(monkeypatch):
    monkeypatch.setenv("LANGSMITH_RUNS_ENDPOINTS", '{"https://elsewhere.example": "k"}')
    assert not decide(settings(langsmith_tracing=True, langsmith_api_key=FAKE_LS_KEY)).enabled


def test_the_configured_client_redacts_and_uses_the_set_endpoint():
    import gradpath.tracing as tracing

    configure_tracing(settings(langsmith_tracing=True, langsmith_api_key=FAKE_LS_KEY))
    client = tracing._client
    assert client.api_url == "http://127.0.0.1:9"
    hidden = client._hide_run_inputs({"text": "mail jane.doe@example.com"})
    assert "jane.doe" not in str(hidden)


def test_configure_on_then_off():
    assert configure_tracing(
        settings(langsmith_tracing=True, langsmith_api_key=FAKE_LS_KEY)
    ).enabled
    assert is_tracing()
    configure_tracing(
        settings(langsmith_tracing=True, langsmith_api_key=FAKE_LS_KEY, app_mode="live")
    )
    assert not is_tracing()


def test_status_never_contains_the_key():
    status = configure_tracing(settings(langsmith_tracing=True, langsmith_api_key=FAKE_LS_KEY))
    assert FAKE_LS_KEY not in repr(status)


# --- visitor keys -------------------------------------------------------------------------


def test_a_visitor_key_is_refused_while_tracing_is_on():
    s = settings(llm_provider="anthropic_api")
    configure_tracing(settings(langsmith_tracing=True, langsmith_api_key=FAKE_LS_KEY))
    with pytest.raises(ValueError, match="tracing"):
        get_chat_model(settings=s, api_key=SecretStr("sk-ant-visitor"))
    configure_tracing(settings())
    assert isinstance(
        get_chat_model(settings=s, api_key=SecretStr("sk-ant-visitor")), ChatAnthropic
    )


# --- what a trace may contain ---------------------------------------------------------------


def test_redaction_removes_keys_emails_and_phones_but_keeps_scores():
    text = (
        "keys sk-ant-" + "a" * 30 + " pa-" + "b" * 40 + " " + FAKE_LS_KEY + " "
        "mail jane.doe@example.com phone (555) 123-4567 or +1 555.123.4567 or (555)987-6543 "
        "or +44 7911 123456 "
        "score 0.4512 year 2026 id q-001 chunk db-postgres-indexes:2:7"
    )
    out = redact({"inputs": {"text": text}})["inputs"]["text"]
    for secret in (
        "sk-ant-",
        "pa-bbbb",
        "lsv2_",
        "jane.doe",
        "123-4567",
        "123.4567",
        "987-6543",
        "7911",
    ):
        assert secret not in out
    for kept in ("0.4512", "2026", "q-001", "db-postgres-indexes:2:7"):
        assert kept in out


def test_search_trace_output_has_ids_and_scores_not_text(kb_service):
    result = kb_service.search("sql index")
    summary = trace_summary(result)
    chunks = summary["results"][0]["chunks"]
    assert chunks and set(chunks[0]) == {"chunk_id", "score"}
    assert trace_summary({"output": [result, result]})["results"][1]["chunks"] == chunks


class RecordingClient(Client):
    """A LangSmith client that records runs instead of uploading them."""

    def __init__(self):
        super().__init__(
            api_key=FAKE_LS_KEY, api_url="http://localhost:1", auto_batch_tracing=False
        )
        self.created: list[dict] = []

    def create_run(self, name, inputs, run_type, **kwargs):
        self.created.append(
            {
                "name": name,
                "run_type": run_type,
                "id": kwargs.get("id"),
                "parent": kwargs.get("parent_run_id"),
            }
        )

    def update_run(self, run_id, **kwargs):
        pass


def test_answer_question_traces_retrieve_and_model_as_children(kb_service):
    client = RecordingClient()
    llm = FakeChatModel(
        responses=[
            {
                "answer": "Use an index.",
                "cited_chunk_ids": ["pg:0:0"],
                "insufficient_evidence": False,
            }
        ]
    )
    with langsmith.tracing_context(enabled=True, client=client, project_name="test"):
        answer_question("sql index", kb_service, llm)
    by_name = {r["name"]: r for r in client.created}
    root = by_name["answer_question"]
    assert root["parent"] is None
    assert by_name["retrieve"]["parent"] == root["id"]
    model_runs = [r for r in client.created if r["run_type"] == "llm"]
    assert model_runs, client.created
    parents = {r["id"]: r["parent"] for r in client.created}

    def under_root(run_id) -> bool:  # walk up: the model sits inside the structured-output chain
        while run_id is not None:
            if run_id == root["id"]:
                return True
            run_id = parents.get(run_id)
        return False

    assert all(under_root(r["parent"]) for r in model_runs), client.created


def test_claude_code_worker_thread_keeps_the_callers_context():
    var = contextvars.ContextVar("marker", default="missing")
    seen: list[str] = []

    async def query(*, prompt, options):
        from claude_agent_sdk import ResultMessage

        seen.append(var.get())
        yield ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="s",
            result="ok",
        )

    llm = ChatClaudeCode(model="m", query_fn=query)

    async def caller():
        var.set("from-caller")
        llm.invoke("hi")  # sync call inside a running loop -> worker thread

    asyncio.run(caller())
    assert seen == ["from-caller"]


def test_resume_import_is_never_traced_even_with_tracing_on():
    # T-014: resume text is personal data; import_resume forces tracing off for its call.
    from gradpath.profiles import import_resume

    client = RecordingClient()
    llm = FakeChatModel(responses=[{"skills": ["Python"]}])
    with langsmith.tracing_context(enabled=True, client=client, project_name="test"):
        result = import_resume("Python developer resume " * 10, llm)
    assert result.profile.skills == ["Python"]
    assert client.created == []


@pytest.mark.parametrize("fails", [False, True])
def test_resume_import_through_claude_code_is_never_traced(fails):
    # The real provider runs the call in a worker thread with a copied context (T-014 review).
    from claude_agent_sdk import ResultMessage

    from gradpath.profiles import import_resume
    from gradpath.providers import ClaudeCodeError

    reply = ResultMessage(
        subtype="error_during_execution" if fails else "success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=fails,
        num_turns=1,
        session_id="s",
        result="",
        structured_output=None if fails else {"skills": ["Python"]},
        usage={"input_tokens": 1, "output_tokens": 1},
    )

    async def query(*, prompt, options):
        yield reply

    client = RecordingClient()
    llm = ChatClaudeCode(model="m", query_fn=query)
    with langsmith.tracing_context(enabled=True, client=client, project_name="test"):
        if fails:
            with pytest.raises(ClaudeCodeError):
                import_resume("Python developer resume " * 10, llm)
        else:
            assert import_resume("Python developer resume " * 10, llm).profile.skills == ["Python"]
    assert client.created == []


def test_tracing_asked_for_outside_local_mode_warns(caplog):
    """An old `.env` with APP_MODE=demo turns tracing off; the log says how to fix it (T-018)."""
    with caplog.at_level("WARNING", logger="gradpath.tracing"):
        configure_tracing(
            settings(langsmith_tracing=True, langsmith_api_key=FAKE_LS_KEY, app_mode="demo")
        )
    assert not is_tracing()
    assert "set APP_MODE=local" in caplog.text
    assert FAKE_LS_KEY not in caplog.text

"""Provider layer tests: no network, no Claude Code process (the SDK stream is faked)."""

import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, SecretStr

from gradpath.config import Settings
from gradpath.providers import (
    ChatClaudeCode,
    ClaudeCodeError,
    FakeChatModel,
    get_chat_model,
    with_structure,
)
from gradpath.providers.claude_code import render_messages


class Skill(BaseModel):
    name: str
    required: bool


def fake_query(result: ResultMessage, seen: list[ClaudeAgentOptions]):
    """Build a stand-in for `claude_agent_sdk.query` that yields one result message."""

    async def _query(*, prompt: str, options: ClaudeAgentOptions):
        seen.append(options)
        yield result

    return _query


def result(**overrides) -> ResultMessage:
    base = dict(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="s",
        result="hello",
        usage={"input_tokens": 3, "output_tokens": 2},
    )
    return ResultMessage(**(base | overrides))


def test_render_single_human_message_passes_through():
    system, prompt = render_messages([SystemMessage("be brief"), HumanMessage("hi")])
    assert system == "be brief"
    assert prompt == "hi"


def test_render_history_is_labelled():
    _, prompt = render_messages([HumanMessage("q1"), AIMessage("a1"), HumanMessage("q2")])
    assert prompt == "[human]\nq1\n\n[ai]\na1\n\n[human]\nq2"


async def test_claude_code_text_reply_and_isolated_options():
    seen: list[ClaudeAgentOptions] = []
    llm = ChatClaudeCode(model="claude-haiku-5-5", query_fn=fake_query(result(), seen))
    reply = await llm.ainvoke("hi")
    assert reply.content == "hello"
    assert reply.usage_metadata["total_tokens"] == 5
    opts = seen[0]
    assert opts.tools == [] and opts.setting_sources == []  # no Claude Code tools or settings
    assert opts.model == "claude-haiku-5-5"


def test_claude_code_sync_invoke_works():
    llm = ChatClaudeCode(model="m", query_fn=fake_query(result(result="sync"), []))
    assert llm.invoke("hi").content == "sync"


async def test_claude_code_structured_output():
    seen: list[ClaudeAgentOptions] = []
    res = result(result=None, structured_output={"name": "SQL", "required": True})
    llm = ChatClaudeCode(model="m", query_fn=fake_query(res, seen))
    skill = await with_structure(llm, Skill).ainvoke("extract")
    assert skill == Skill(name="SQL", required=True)
    assert seen[0].output_format["type"] == "json_schema"
    assert seen[0].output_format["schema"]["title"] == "Skill"


async def test_claude_code_error_result_raises():
    res = result(is_error=True, subtype="error_max_turns", result=None)
    llm = ChatClaudeCode(model="m", query_fn=fake_query(res, []))
    with pytest.raises(ClaudeCodeError, match="error_max_turns"):
        await llm.ainvoke("hi")


def test_factory_picks_provider_and_tier():
    s = Settings(_env_file=None, llm_provider="claude_code")
    assert get_chat_model("fast", settings=s).model == "claude-haiku-5-5"
    assert get_chat_model("smart", settings=s).model == "claude-sonnet-5-5"

    api = Settings(_env_file=None, llm_provider="anthropic_api", anthropic_api_key="test-key")
    assert isinstance(get_chat_model(settings=api), ChatAnthropic)

    assert isinstance(
        get_chat_model(settings=Settings(_env_file=None, llm_provider="fake")), FakeChatModel
    )


def test_factory_api_mode_needs_a_key():
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        get_chat_model(settings=Settings(_env_file=None, llm_provider="anthropic_api"))


def test_factory_request_key_overrides_server_key():
    s = Settings(_env_file=None, llm_provider="anthropic_api")
    llm = get_chat_model(settings=s, api_key=SecretStr("visitor-key"))
    assert llm.anthropic_api_key.get_secret_value() == "visitor-key"


def test_with_structure_uses_json_schema_for_chat_anthropic():
    llm = ChatAnthropic(model="claude-sonnet-5-5", api_key="test-key")
    bound = with_structure(llm, Skill)
    # json_schema binds output_config, never a forced tool_choice (400 on current models).
    kwargs = bound.first.kwargs
    assert "output_config" in kwargs and "tool_choice" not in kwargs


def test_fake_model_structured():
    llm = FakeChatModel(responses=[{"name": "Git", "required": False}])
    assert with_structure(llm, Skill).invoke("x") == Skill(name="Git", required=False)
    assert len(llm.calls) == 1


def test_settings_hide_secrets():
    s = Settings(_env_file=None, voyage_api_key="super-secret")
    assert "super-secret" not in repr(s)

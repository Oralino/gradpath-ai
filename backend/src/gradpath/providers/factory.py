"""One place that decides which chat model the app uses (`LLM_PROVIDER` in `.env`)."""

from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from pydantic import BaseModel, SecretStr

from gradpath.config import Settings, get_settings
from gradpath.providers.claude_code import ChatClaudeCode
from gradpath.providers.fake import FakeChatModel

Tier = Literal["fast", "smart"]


def get_chat_model(
    tier: Tier = "smart",
    *,
    settings: Settings | None = None,
    api_key: SecretStr | None = None,
) -> BaseChatModel:
    """Return the configured chat model for a tier ("fast" = Haiku, "smart" = Sonnet by default).

    Called by every node and chain that needs an LLM, so swapping provider is a config change.
    `api_key` is a visitor's key for one request (live mode); it is passed straight to the client
    and never stored. A request key never falls back to the server key (even when empty) and is
    refused under providers that can't use it, so a visitor can never run on the owner's account.
    """
    s = settings or get_settings()
    model = s.model_fast if tier == "fast" else s.model_smart
    if api_key is not None:
        if s.llm_provider != "anthropic_api":
            raise ValueError("a request API key needs LLM_PROVIDER=anthropic_api")
        if not api_key.get_secret_value().strip():
            raise ValueError("the request API key is empty")
    if s.llm_provider == "claude_code":
        return ChatClaudeCode(model=model)
    if s.llm_provider == "anthropic_api":
        # `is not None`, not `or`: an empty SecretStr is falsy and must not select the server key.
        key = api_key if api_key is not None else s.anthropic_api_key
        if key is None or not key.get_secret_value().strip():
            raise ValueError("LLM_PROVIDER=anthropic_api needs ANTHROPIC_API_KEY or a request key")
        return ChatAnthropic(model=model, api_key=key, max_tokens=16000, max_retries=2)
    return FakeChatModel()


def with_structure(llm: BaseChatModel, schema: type[BaseModel]) -> Runnable:
    """Bind structured output the way each provider needs.

    `ChatAnthropic` must use `method="json_schema"`: its default forces a tool call, which current
    Claude models (Sonnet 5.5, Opus 5.5) reject with a 400. The other providers have one method.
    """
    if isinstance(llm, ChatAnthropic):
        return llm.with_structured_output(schema, method="json_schema")
    return llm.with_structured_output(schema)

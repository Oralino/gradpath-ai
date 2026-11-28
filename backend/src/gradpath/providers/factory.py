"""One place that decides which chat model the app uses (`LLM_PROVIDER` in `.env`)."""

from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from pydantic import BaseModel, SecretStr

from gradpath.config import Settings, get_settings
from gradpath.providers.claude_code import ChatClaudeCode
from gradpath.providers.fake import FakeChatModel
from gradpath.tracing import is_tracing

Tier = Literal["fast", "smart"]
# Providers served by a model server on this PC (T-029); their clients live in `local_servers`.
LOCAL_SERVERS = ("ollama", "lmstudio")


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
    It is also refused while tracing is on, so a visitor's request is never traced.
    Under `ollama` / `lmstudio` the tier's name is a local model's (a `claude-*` name is refused),
    and the client module is imported only then, as the API image leaves its libraries out.
    """
    s = settings or get_settings()
    model = s.model_fast if tier == "fast" else s.model_smart
    if api_key is not None:
        if s.llm_provider != "anthropic_api":
            raise ValueError("a request API key needs LLM_PROVIDER=anthropic_api")
        if not api_key.get_secret_value().strip():
            raise ValueError("the request API key is empty")
        if is_tracing():
            # A visitor's prompt must never reach LangSmith (live mode forces tracing off too).
            raise ValueError("refusing a request API key while LangSmith tracing is on")
    if s.llm_provider in LOCAL_SERVERS:
        if model.startswith("claude-"):
            raise ValueError(
                f"LLM_PROVIDER={s.llm_provider} needs MODEL_FAST and MODEL_SMART set to local "
                f"model names (got {model!r})"
            )
        from gradpath.providers.local_servers import local_server_model

        return local_server_model(model, s)
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
    Claude models (Sonnet 5.5, Opus 5.5) reject with a 400. Local-server clients (Ollama, LM
    Studio) use JSON-schema mode too (`local_servers.structured_method`); the module is imported
    only for those clients, so the API never loads their libraries. The others have one method.
    """
    if isinstance(llm, ChatAnthropic):
        return llm.with_structured_output(schema, method="json_schema")
    if type(llm).__module__.startswith(("langchain_ollama", "langchain_openai")):
        from gradpath.providers.local_servers import structured_method

        method = structured_method(llm)
        if method is not None:
            return llm.with_structured_output(schema, method=method)
    return llm.with_structured_output(schema)

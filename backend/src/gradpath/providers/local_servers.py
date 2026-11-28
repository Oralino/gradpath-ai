"""Server-side clients for local model servers on the owner's PC (local mode only, T-029).

Kept apart from `factory.py` because these libraries are in the `local` dependency group, which
the API image leaves out: the factory imports this module only when `LLM_PROVIDER` is `ollama`,
`lmstudio` or `llamacpp`, which live and demo mode never allow. Visitors' local models on the
deployed site go through the browser relay instead (the server can't reach a visitor's localhost).
"""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from gradpath.config import Settings

# LM Studio's OpenAI-compatible server ignores the key, but the OpenAI client requires one. A
# fixed placeholder also keeps an OPENAI_API_KEY in the environment from being sent to it.
LMSTUDIO_PLACEHOLDER_KEY = SecretStr("lm-studio")
# llama-server (llama.cpp) needs a key only when started with --api-key; same reasoning.
LLAMACPP_PLACEHOLDER_KEY = SecretStr("llama-cpp")
# Turns off a thinking model's hidden reasoning pass per request (Qwen3 family), like Ollama's
# `think: false` in the page client; llama-server accepted it on 2026-11-28 (build 12835). Starting
# the server with `--reasoning off` does the same for every request.
LLAMACPP_NO_THINKING = {"chat_template_kwargs": {"enable_thinking": False}}


def local_server_model(model: str, s: Settings) -> BaseChatModel:
    """Return the chat model for a local-server `s.llm_provider` serving `model`.

    Called by `factory.get_chat_model`. The address, key and proxy are passed explicitly, so
    OPENAI_BASE_URL, OPENAI_API_KEY and OPENAI_PROXY in the environment never apply (an
    OPENAI_ORG_ID still would: langchain-openai reads it whatever is passed; it is not a secret).
    """
    if s.llm_provider == "ollama":
        return ChatOllama(
            model=model,
            base_url=s.ollama_base_url,
            client_kwargs={"timeout": s.local_llm_timeout_s},
        )
    if s.llm_provider == "lmstudio":
        return ChatOpenAI(
            model=model,
            base_url=s.lmstudio_base_url,
            api_key=LMSTUDIO_PLACEHOLDER_KEY,
            openai_proxy=None,
            timeout=s.local_llm_timeout_s,
            max_retries=1,
        )
    if s.llm_provider == "llamacpp":
        # One llama-server serves the model it was started with (-m) whatever name is sent, so
        # MODEL_FAST / MODEL_SMART are labels for the logs here.
        return ChatOpenAI(
            model=model,
            base_url=s.llamacpp_base_url,
            api_key=LLAMACPP_PLACEHOLDER_KEY,
            openai_proxy=None,
            timeout=s.local_llm_timeout_s,
            max_retries=1,
            extra_body=LLAMACPP_NO_THINKING,
        )
    raise ValueError(f"not a local model server provider: {s.llm_provider}")


def structured_method(llm: BaseChatModel) -> str | None:
    """The `with_structured_output` method a local-server client needs, or None if `llm` isn't one.

    Called by `factory.with_structure`. LM Studio and llama-server enforce a JSON schema through
    `response_format` (`json_schema`); `ChatOpenAI` defaults to tool calling, which small local
    models handle poorly. `ChatOllama` sends the schema as Ollama's `format` field.
    """
    if isinstance(llm, ChatOpenAI | ChatOllama):
        return "json_schema"
    return None

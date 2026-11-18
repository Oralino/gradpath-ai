"""Deterministic chat model for tests: canned replies, no network, no cost."""

import json
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, Field


class FakeChatModel(BaseChatModel):
    """Returns `responses` in order (cycling). A dict response is JSON for structured output.

    Used by the test suite through `get_chat_model` with `LLM_PROVIDER=fake`, or directly.
    Records every prompt it receives in `calls` so tests can assert on what was sent.
    """

    responses: list[str | dict[str, Any]] = Field(default_factory=lambda: ["fake answer"])
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        reply = self.responses[len(self.calls) % len(self.responses)]
        self.calls.append(list(messages))
        text = json.dumps(reply) if isinstance(reply, dict) else reply
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def with_structured_output(
        self, schema: type[BaseModel], *, include_raw: bool = False, **kwargs: Any
    ) -> Runnable:
        """Parse the canned JSON reply into `schema`, like the real providers do."""
        return self | RunnableLambda(lambda m: schema.model_validate_json(m.text))

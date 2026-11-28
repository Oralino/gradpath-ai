"""`ChatClaudeCode`: a LangChain chat model that runs Claude through Claude Code (owner's plan)."""

import asyncio
import contextvars
import json
import logging
import os
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

if TYPE_CHECKING:  # the SDK itself is imported only when a Claude Code call runs (T-025)
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage

QueryFn = Callable[..., Any]
log = logging.getLogger(__name__)


class ClaudeCodeError(RuntimeError):
    """Claude Code finished with an error result (rate limit, auth, invalid output, ...)."""


def render_messages(messages: list[BaseMessage]) -> tuple[str | None, str]:
    """Split LangChain messages into (system prompt, user prompt) for the Agent SDK.

    Called by `ChatClaudeCode._agenerate`. The SDK takes one prompt string, so a multi-message
    history is rendered as a labelled transcript; a single human message is passed as-is.
    """
    system = "\n\n".join(m.text for m in messages if isinstance(m, SystemMessage)) or None
    rest = [m for m in messages if not isinstance(m, SystemMessage)]
    if len(rest) == 1:
        return system, rest[0].text
    lines = [f"[{m.type}]\n{m.text}" for m in rest]
    return system, "\n\n".join(lines)


class ChatClaudeCode(BaseChatModel):
    """Chat model backed by the Claude Agent SDK, so local runs use the owner's Claude plan.

    Created by `providers.factory.get_chat_model` when `LLM_PROVIDER=claude_code`. Built-in Claude
    Code tools and the owner's Claude Code settings are switched off: this is a plain
    prompt-in, text-or-JSON-out model, not a coding agent. Structured output uses the SDK's
    `output_format` JSON schema (see `with_structured_output`).
    """

    model: str
    max_turns: int = 3
    effort: str | None = None
    timeout_s: float = 300.0
    # Injected in tests so no real Claude Code process is started; None means the SDK's `query`.
    query_fn: QueryFn | None = None

    @property
    def _llm_type(self) -> str:
        return "claude-code"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model": self.model, "effort": self.effort}

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Imported here, not at the top: the SDK bundles the Claude Code program (~360 MB) and
        # only local mode uses it, so the deployed image leaves it out (T-025, `local` group).
        try:
            from claude_agent_sdk import ClaudeAgentOptions
        except ModuleNotFoundError as exc:  # e.g. LLM_PROVIDER=claude_code inside the image
            raise ClaudeCodeError(
                "LLM_PROVIDER=claude_code needs the `local` dependency group (uv sync)"
            ) from exc

        system, prompt = render_messages(messages)
        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt=system,
            tools=[],
            setting_sources=[],
            max_turns=self.max_turns,
            effort=self.effort,
            output_format=kwargs.get("output_format"),
        )
        if os.environ.get("ANTHROPIC_API_KEY"):
            # Claude Code would bill this key instead of the owner's plan (zero-cost rule).
            log.warning("ANTHROPIC_API_KEY is set in the environment; Claude Code may use the API")
        try:
            result = await asyncio.wait_for(self._run(prompt, options), timeout=self.timeout_s)
        except TimeoutError as exc:
            raise ClaudeCodeError(f"Claude Code timed out after {self.timeout_s:.0f}s") from exc
        # Some failures (e.g. "error_max_turns") arrive with is_error false, so check the subtype.
        if result.is_error or result.subtype != "success":
            detail = result.errors or result.result or result.subtype
            raise ClaudeCodeError(f"Claude Code returned an error: {detail}")

        structured = result.structured_output
        text = result.result or (json.dumps(structured) if structured is not None else "")
        message = AIMessage(
            content=text,
            additional_kwargs={"structured_output": structured} if structured is not None else {},
            response_metadata={"model": self.model, "stop_reason": result.stop_reason},
        )
        usage = result.usage or {}
        if "input_tokens" in usage and "output_tokens" in usage:
            message.usage_metadata = {
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
                "total_tokens": usage["input_tokens"] + usage["output_tokens"],
            }
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _run(self, prompt: str, options: "ClaudeAgentOptions") -> "ResultMessage":
        """Drain the SDK's message stream and return its final `ResultMessage`.

        The stream is always closed (also on timeout/cancellation), so the SDK can shut down its
        Claude Code subprocess instead of leaving it running.
        """
        from claude_agent_sdk import ResultMessage, query

        final: ResultMessage | None = None
        stream = (self.query_fn or query)(prompt=prompt, options=options)
        try:
            async for msg in stream:
                if isinstance(msg, ResultMessage):
                    final = msg
        finally:
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                await aclose()
        if final is None:
            raise ClaudeCodeError("Claude Code ended without a result message")
        return final

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Sync entry point: runs `_agenerate` on a fresh event loop (in a thread if one runs).

        The worker thread runs in a copy of the caller's context, so tracing and other context
        variables set by the caller (e.g. LangSmith's parent run) are still visible inside it.
        """
        coro_factory = lambda: self._agenerate(messages, stop, None, **kwargs)  # noqa: E731
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro_factory())
        box: dict[str, Any] = {}

        def worker() -> None:
            try:
                box["result"] = asyncio.run(coro_factory())
            except BaseException as exc:  # re-raised in the calling thread
                box["error"] = exc

        thread = threading.Thread(target=contextvars.copy_context().run, args=(worker,))
        thread.start()
        thread.join()
        if "error" in box:
            raise box["error"]
        return box["result"]

    def with_structured_output(
        self, schema: type[BaseModel], *, include_raw: bool = False, **kwargs: Any
    ) -> Runnable:
        """Return a runnable that yields a validated `schema` instance.

        Binds the SDK's `output_format` (JSON schema from the Pydantic model) and validates
        `structured_output` from the result, so callers get the same behaviour as
        `ChatAnthropic.with_structured_output(..., method="json_schema")`.
        """
        if include_raw:
            raise NotImplementedError("include_raw is not supported by ChatClaudeCode")
        output_format = {"type": "json_schema", "schema": schema.model_json_schema()}

        def parse(message: AIMessage) -> BaseModel:
            data = message.additional_kwargs.get("structured_output")
            if data is None:
                data = json.loads(message.text)
            return schema.model_validate(data)

        return self.bind(output_format=output_format) | RunnableLambda(parse)

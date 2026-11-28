"""Browser relay chat model: model calls answered by the visitor's browser (T-029 step 2).

The deployed API can't reach a visitor's `localhost` (Ollama, LM Studio), and transformers.js
runs only in a browser. So for those providers each model call in a run becomes a prompt in the
run's `RelayChannel`: the node's thread waits, the browser polls the run (`api/relay.py`), runs
the prompt on its local model and posts the reply, and the node goes on with it. The workflow,
router and RAG chain don't change: they receive a `BrowserRelayChatModel` like any chat model.

Replies are untrusted model output: bounded in size, stripped of a `<think>` block, and for
structured steps parsed and validated here on the server (one retry, then the caller's labelled
fallback). Every wait is bounded (reply timeout, the browser going quiet, a run deadline), so a
closed tab or a slow model can't hold a server thread for long.
"""

import json
import re
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_REPLY_CHARS = 20_000  # one reply from the browser; also the API's body limit
MAX_PROMPTS = 40  # prompts per run, retries included (a full plan with a revision is ~10)
MAX_PENDING = 4  # prompts waiting at once (the workflow runs some stages in parallel)
WAIT_STEP_S = 0.25  # how often a waiting call re-checks its deadlines

Tier = Literal["fast", "smart"]
Role = Literal["system", "user", "assistant"]

RETRY_NOTE = (
    "Your previous reply could not be read as JSON matching the schema. Reply again with only "
    "the JSON object, no other text."
)


class RelayError(ConnectionError):
    """The relay could not get an answer. A ConnectionError, so the workflow's fallback labels
    it "dependency_unavailable" (the visitor's model is the dependency)."""


class RelayTimeout(RelayError, TimeoutError):
    """No reply within the reply timeout, or the run's deadline passed."""


class RelayClosed(RelayError):
    """The run ended, or the browser stopped polling (a closed tab), while a call waited."""


class RelayCancelled(RelayClosed):
    """The visitor stopped the run (`DELETE /api/relay/runs/{id}`) while a call waited."""


class RelayModelFailed(RelayError):
    """The browser reported that its local model failed on this prompt."""


class RelayLimit(RuntimeError):
    """Too many prompts in this run, or too many waiting at once. A RuntimeError, so the
    workflow's fallback labels it "stage_failed" (the run misbehaved, no service was down)."""


class RelayBadOutput(ValueError):
    """A structured reply was still not valid JSON for the schema after one retry. A ValueError,
    so the workflow's fallback labels it "stage_failed"."""


class RelayMessage(BaseModel):
    role: Role
    content: str


class RelayPrompt(BaseModel):
    """What the browser receives for one model call (OpenAI-style messages, which Ollama,
    LM Studio and transformers.js chat templates all accept). `json_schema` is set for
    structured steps; `tier` picks the visitor's fast or smart model."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    tier: Tier
    messages: list[RelayMessage]
    json_schema: dict[str, Any] | None = None


@dataclass
class _Pending:
    prompt: RelayPrompt
    created: float
    done: bool = False
    text: str | None = None
    failed: bool = False


@dataclass
class RelayChannel:
    """The outbox and inbox of one run, shared by the run's worker threads (`ask`) and the API
    (`pending`, `reply`). One lock and condition guard everything; `clock` is injectable."""

    reply_timeout_s: float
    idle_timeout_s: float
    deadline_s: float
    max_prompts: int = MAX_PROMPTS
    max_pending: int = MAX_PENDING
    clock: Callable[[], float] = time.monotonic
    _cond: threading.Condition = field(default_factory=threading.Condition, init=False)
    _pending: dict[str, _Pending] = field(default_factory=dict, init=False)
    _count: int = field(default=0, init=False)
    _closed: bool = field(default=False, init=False)
    _cancelled: bool = field(default=False, init=False)
    _started: float = field(default=0.0, init=False)
    _last_poll: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self._started = self._last_poll = self.clock()

    def ask(self, tier: Tier, messages: list[RelayMessage], schema: dict | None = None) -> str:
        """Queue one prompt and block until the browser answers it. Called by
        `BrowserRelayChatModel` in the run's worker threads. Raises a `RelayError` on a timeout,
        a closed run, a quiet browser, a reported failure or a limit; never waits unbounded."""
        with self._cond:
            self._check_open()
            if self._count >= self.max_prompts:
                raise RelayLimit("prompt limit for this run reached")
            if len(self._pending) >= self.max_pending:
                raise RelayLimit("too many prompts waiting")
            self._count += 1
            prompt = RelayPrompt(
                id=str(uuid.uuid4()), tier=tier, messages=messages, json_schema=schema
            )
            item = _Pending(prompt=prompt, created=self.clock())
            self._pending[prompt.id] = item
            try:
                while not item.done:
                    now = self.clock()
                    if self._closed:
                        raise self._closed_error()
                    if now - self._last_poll > self.idle_timeout_s:
                        self._close_locked()
                        raise RelayClosed("the browser stopped polling")
                    if now - item.created > self.reply_timeout_s:
                        raise RelayTimeout("no reply in time")
                    if now - self._started > self.deadline_s:
                        raise RelayTimeout("the run's deadline passed")
                    self._cond.wait(WAIT_STEP_S)
            finally:
                self._pending.pop(prompt.id, None)
            if item.failed or item.text is None:
                raise RelayModelFailed("the local model failed")
            return item.text

    def pending(self) -> list[RelayPrompt]:
        """The prompts waiting for a reply, oldest first; also records that the browser is still
        there. Called by the run status poll."""
        with self._cond:
            self._last_poll = self.clock()
            if self._closed:
                return []
            return [p.prompt for p in sorted(self._pending.values(), key=lambda p: p.created)]

    def touch(self) -> None:
        """Record that the browser is still there (a reply counts as a poll)."""
        with self._cond:
            self._last_poll = self.clock()

    def reply(self, prompt_id: str, text: str | None, failed: bool = False) -> bool:
        """Deliver the browser's answer (or its failure) to the waiting call. False if the
        prompt is unknown, already answered, timed out or the run is closed: one reply each."""
        if text is not None and len(text) > MAX_REPLY_CHARS:
            raise ValueError("reply too long")
        with self._cond:
            self._last_poll = self.clock()
            item = self._pending.get(prompt_id)
            if self._closed or item is None or item.done:
                return False
            item.done, item.text, item.failed = True, text, failed or text is None
            self._cond.notify_all()
            return True

    def close(self, *, cancelled: bool = False) -> None:
        """End the run's relay: waiting calls raise `RelayClosed` (`RelayCancelled` when the
        visitor stopped the run), later replies are refused. Called by the run store when the run
        finishes, whatever its outcome, and by `RunStore.cancel`."""
        with self._cond:
            if not self._closed:
                self._cancelled = cancelled
            self._close_locked()

    @property
    def closed(self) -> bool:
        with self._cond:
            return self._closed

    def _close_locked(self) -> None:
        self._closed = True
        self._cond.notify_all()

    def _closed_error(self) -> RelayClosed:
        return RelayCancelled("the run was stopped") if self._cancelled else RelayClosed("closed")

    def _check_open(self) -> None:
        if self._closed:
            raise self._closed_error()
        if self.clock() - self._last_poll > self.idle_timeout_s:
            self._close_locked()
            raise RelayClosed("the browser stopped polling")


# ---------- reply clean-up (untrusted text) ----------

THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def strip_reasoning(text: str) -> str:
    """Drop a reasoning model's `<think>...</think>` block (DeepSeek-R1 distills write one before
    the answer). Some chat templates open the block in the prompt, so the reply holds only the
    closing tag: everything up to the last `</think>` goes then. An unclosed block is left."""
    text = THINK_BLOCK.sub("", text)
    end = text.lower().rfind("</think>")
    if end != -1:
        text = text[end + len("</think>") :]
    return text.strip()


def parse_json_reply[T: BaseModel](text: str, schema: type[T]) -> T:
    """The reply as a validated `schema` instance: reasoning and code fences stripped, then the
    outermost JSON object. Raises ValueError (or ValidationError) when there is none."""
    body = FENCE.sub("", strip_reasoning(text)).strip()
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object in the reply")
    return schema.model_validate(json.loads(body[start : end + 1]))


def to_relay_messages(messages: list[BaseMessage]) -> list[RelayMessage]:
    """LangChain messages as role/content pairs. Only system, human and AI text is relayed: our
    chains use nothing else, and tool calls can't run in the browser."""
    out: list[RelayMessage] = []
    for m in messages:
        if isinstance(m, SystemMessage):
            role: Role = "system"
        elif isinstance(m, HumanMessage):
            role = "user"
        elif isinstance(m, AIMessage):
            role = "assistant"
        else:
            raise ValueError(f"the relay can't send a {type(m).__name__}")
        out.append(RelayMessage(role=role, content=m.text))
    return out


class BrowserRelayChatModel(BaseChatModel):
    """A chat model whose calls are answered by the visitor's browser through `channel`.

    Created by `providers.factory.get_chat_model(relay=...)` for relay runs (`api/relay.py`).
    Plain calls return the reply text with any `<think>` block removed; `with_structured_output`
    sends the JSON schema along and validates the reply here, retrying once.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    channel: RelayChannel = Field(exclude=True)
    tier: Tier = "smart"

    @property
    def _llm_type(self) -> str:
        return "browser-relay"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        text = self.channel.ask(self.tier, to_relay_messages(messages))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(strip_reasoning(text)))])

    def with_structured_output(  # type: ignore[override]
        self, schema: type[BaseModel], *, include_raw: bool = False, **kwargs: Any
    ) -> Runnable:
        """A runnable returning a validated `schema` instance (Pydantic schemas only, as every
        caller in the app uses). `include_raw` is not supported."""
        if include_raw or not (isinstance(schema, type) and issubclass(schema, BaseModel)):
            raise ValueError("the relay supports Pydantic schemas without include_raw only")
        json_schema = schema.model_json_schema()

        def run(value: LanguageModelInput) -> BaseModel:
            messages = to_relay_messages(self._convert_input(value).to_messages())
            text = self.channel.ask(self.tier, messages, json_schema)
            try:
                return parse_json_reply(text, schema)
            except (ValueError, ValidationError, RecursionError):
                pass  # one retry with the reply and a correction, then give up
            retry = [
                *messages,
                RelayMessage(role="assistant", content=text[:4000]),
                RelayMessage(role="user", content=RETRY_NOTE),
            ]
            text = self.channel.ask(self.tier, retry, json_schema)
            try:
                return parse_json_reply(text, schema)
            except (ValueError, ValidationError, RecursionError) as exc:
                # RecursionError: json.loads on a deeply nested reply.
                raise RelayBadOutput("the local model's reply was not valid JSON") from exc

        return RunnableLambda(run, name=f"relay_structured_{schema.__name__}")

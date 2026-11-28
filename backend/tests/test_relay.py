"""Browser relay channel and chat model (T-029 step 2): no network, no browser.

A "browser" here is a thread that polls the channel and answers its prompts, as the page will.
Timeouts are real but tiny, so a hung wait would fail the test instead of hanging it.
"""

import threading
import time
from collections.abc import Callable

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, SecretStr

from gradpath.providers import get_chat_model, with_structure
from gradpath.providers.relay import (
    MAX_REPLY_CHARS,
    BrowserRelayChatModel,
    RelayBadOutput,
    RelayChannel,
    RelayClosed,
    RelayLimit,
    RelayMessage,
    RelayModelFailed,
    RelayPrompt,
    RelayTimeout,
    parse_json_reply,
    strip_reasoning,
    to_relay_messages,
)


class Skill(BaseModel):
    name: str
    required: bool


def channel(**overrides) -> RelayChannel:
    base = dict(reply_timeout_s=2.0, idle_timeout_s=2.0, deadline_s=10.0)
    return RelayChannel(**(base | overrides))


class Browser:
    """Polls `ch` in a thread and answers each new prompt with `answer(prompt)` (None = report a
    failure). Records every prompt it saw."""

    def __init__(self, ch: RelayChannel, answer: Callable[[RelayPrompt], str | None]) -> None:
        self.ch, self.answer, self.seen = ch, answer, []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def __enter__(self) -> "Browser":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join(2)

    def _loop(self) -> None:
        answered: set[str] = set()
        while not self._stop.is_set():
            for p in self.ch.pending():
                if p.id in answered:
                    continue
                answered.add(p.id)
                self.seen.append(p)
                text = self.answer(p)
                self.ch.reply(p.id, text, failed=text is None)
            time.sleep(0.005)


def ask_in_thread(ch: RelayChannel, **kw) -> tuple[threading.Thread, dict]:
    out: dict = {}

    def run() -> None:
        try:
            out["text"] = ch.ask("fast", [RelayMessage(role="user", content="hi")], **kw)
        except Exception as exc:  # recorded for the assertion
            out["error"] = exc

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t, out


# --- the channel -------------------------------------------------------------------------------


def test_a_prompt_goes_out_and_the_reply_comes_back():
    ch = channel()
    with Browser(ch, lambda p: f"echo {p.messages[-1].content}") as browser:
        assert ch.ask("smart", [RelayMessage(role="user", content="hello")]) == "echo hello"
    prompt = browser.seen[0]
    assert prompt.tier == "smart" and prompt.json_schema is None
    assert ch.pending() == []  # nothing left waiting


def test_parallel_prompts_each_get_their_own_reply():
    """The workflow runs some stages in parallel: two calls wait at once on one channel."""
    ch = channel()
    with Browser(ch, lambda p: p.messages[0].content.upper()):
        results: dict[str, str] = {}

        def call(word: str) -> None:
            results[word] = ch.ask("fast", [RelayMessage(role="user", content=word)])

        threads = [threading.Thread(target=call, args=(w,)) for w in ("alpha", "beta", "gamma")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(3)
    assert results == {"alpha": "ALPHA", "beta": "BETA", "gamma": "GAMMA"}


def test_no_reply_in_time_raises_a_timeout():
    ch = channel(reply_timeout_s=0.1)
    t, out = ask_in_thread(ch)
    end = time.monotonic() + 1
    while t.is_alive() and time.monotonic() < end:
        ch.pending()  # the browser is there, it just never answers
        time.sleep(0.01)
    t.join(1)
    assert isinstance(out["error"], RelayTimeout)
    assert isinstance(out["error"], TimeoutError)  # the fallback labels it dependency_unavailable


def test_a_quiet_browser_closes_the_run():
    """A closed tab: nobody polls, so the waiting call stops after the idle timeout."""
    ch = channel(idle_timeout_s=0.1)
    t, out = ask_in_thread(ch)
    t.join(2)
    assert isinstance(out["error"], RelayClosed)
    assert ch.closed
    with pytest.raises(RelayClosed):  # and the run takes no new prompts
        ch.ask("fast", [RelayMessage(role="user", content="again")])


def test_the_run_deadline_bounds_every_wait():
    ch = channel(deadline_s=0.1, reply_timeout_s=5)
    t, out = ask_in_thread(ch)
    end = time.monotonic() + 2
    while t.is_alive() and time.monotonic() < end:
        ch.pending()
        time.sleep(0.01)
    assert isinstance(out["error"], RelayTimeout)


def test_closing_wakes_a_waiting_call_and_refuses_late_replies():
    ch = channel()
    t, out = ask_in_thread(ch)
    while not ch.pending():
        time.sleep(0.005)
    prompt_id = ch.pending()[0].id
    ch.close()
    t.join(1)
    assert isinstance(out["error"], RelayClosed)
    assert ch.reply(prompt_id, "too late") is False
    assert ch.pending() == []


def test_a_reported_failure_raises():
    ch = channel()
    with Browser(ch, lambda p: None), pytest.raises(RelayModelFailed):
        ch.ask("fast", [RelayMessage(role="user", content="hi")])


def test_one_reply_per_prompt_and_unknown_ids_are_refused():
    ch = channel()
    t, _ = ask_in_thread(ch)
    while not ch.pending():
        time.sleep(0.005)
    prompt_id = ch.pending()[0].id
    assert ch.reply("00000000-0000-4000-8000-000000000000", "x") is False
    assert ch.reply(prompt_id, "first") is True
    assert ch.reply(prompt_id, "second") is False
    t.join(1)


def test_an_oversized_reply_is_refused():
    ch = channel()
    with pytest.raises(ValueError, match="too long"):
        ch.reply("any", "x" * (MAX_REPLY_CHARS + 1))


def test_prompt_limits():
    ch = channel(max_prompts=2)
    with Browser(ch, lambda p: "ok"):
        ch.ask("fast", [RelayMessage(role="user", content="1")])
        ch.ask("fast", [RelayMessage(role="user", content="2")])
        with pytest.raises(RelayLimit):
            ch.ask("fast", [RelayMessage(role="user", content="3")])
    waiting = channel(max_pending=1)
    t, _ = ask_in_thread(waiting)
    while not waiting.pending():
        time.sleep(0.005)
    with pytest.raises(RelayLimit, match="waiting"):
        waiting.ask("fast", [RelayMessage(role="user", content="second")])
    waiting.close()
    t.join(1)


# --- reply clean-up ----------------------------------------------------------------------------


def test_strip_reasoning():
    assert strip_reasoning("<think>\nhmm, SQL?\n</think>\n\nThe answer.") == "The answer."
    # The template opened the block in the prompt: only the closing tag is in the reply.
    assert strip_reasoning("still thinking...</think> Done.") == "Done."
    assert strip_reasoning("No reasoning here.") == "No reasoning here."


def test_parse_json_reply_handles_fences_prose_and_think_blocks():
    text = (
        "<think>the schema wants a name</think>Sure!\n```json\n"
        '{"name": "SQL", "required": true}\n```'
    )
    assert parse_json_reply(text, Skill) == Skill(name="SQL", required=True)
    with pytest.raises(ValueError):
        parse_json_reply("no json at all", Skill)


def test_messages_are_relayed_as_roles():
    msgs = to_relay_messages([SystemMessage("be brief"), HumanMessage("q"), AIMessage("a")])
    assert [(m.role, m.content) for m in msgs] == [
        ("system", "be brief"),
        ("user", "q"),
        ("assistant", "a"),
    ]
    with pytest.raises(ValueError, match="ToolMessage"):
        to_relay_messages([ToolMessage("x", tool_call_id="1")])


# --- the chat model ----------------------------------------------------------------------------


def test_the_factory_returns_the_relay_model_and_refuses_a_key():
    ch = channel()
    llm = get_chat_model("fast", relay=ch)
    assert isinstance(llm, BrowserRelayChatModel) and llm.tier == "fast"
    with pytest.raises(ValueError, match="no API key"):
        get_chat_model("fast", relay=ch, api_key=SecretStr("sk-ant-x"))


def test_plain_invoke_strips_reasoning():
    ch = channel()
    with Browser(ch, lambda p: "<think>let me see</think>Indexes speed up reads."):
        reply = get_chat_model("smart", relay=ch).invoke([HumanMessage("What is an index?")])
    assert reply.content == "Indexes speed up reads."


def test_structured_output_sends_the_schema_and_validates():
    ch = channel()
    with Browser(ch, lambda p: '{"name": "SQL", "required": true}') as browser:
        skill = with_structure(get_chat_model("fast", relay=ch), Skill).invoke("extract")
    assert skill == Skill(name="SQL", required=True)
    assert browser.seen[0].json_schema == Skill.model_json_schema()


def test_structured_output_retries_once_then_succeeds():
    replies = iter(["I think the skill is SQL.", '{"name": "SQL", "required": false}'])
    ch = channel()
    with Browser(ch, lambda p: next(replies)) as browser:
        skill = with_structure(get_chat_model("fast", relay=ch), Skill).invoke("extract")
    assert skill.required is False
    retry = browser.seen[1].messages
    assert retry[-2].role == "assistant" and retry[-1].role == "user"  # the reply, then the note


def test_structured_output_gives_up_after_one_retry():
    ch = channel()
    with Browser(ch, lambda p: "still not json") as browser, pytest.raises(RelayBadOutput):
        with_structure(get_chat_model("fast", relay=ch), Skill).invoke("extract")
    assert len(browser.seen) == 2
    assert isinstance(RelayBadOutput("x"), ValueError)  # the fallback labels it stage_failed


def test_a_deeply_nested_reply_is_unreadable_not_a_crash():
    """json.loads raises RecursionError on deep nesting: it must still get the retry and the
    RelayBadOutput label, not escape as an unlabelled error."""
    ch = channel()
    nested = "{" + '"a":' + "[" * 5000 + "]" * 5000 + "}"
    with Browser(ch, lambda p: nested) as browser, pytest.raises(RelayBadOutput):
        with_structure(get_chat_model("fast", relay=ch), Skill).invoke("extract")
    assert len(browser.seen) == 2


def test_the_prompt_cap_is_a_stage_failure_not_an_outage():
    from gradpath.workflows.fallback import classify

    assert classify(RelayLimit("cap")) == "stage_failed"
    assert classify(RelayTimeout("slow")) == "dependency_unavailable"


def test_a_cancelled_run_says_so():
    from gradpath.providers.relay import RelayCancelled

    ch = channel()
    t, out = ask_in_thread(ch)
    while not ch.pending():
        time.sleep(0.005)
    ch.close(cancelled=True)
    ch.close()  # the store's own close afterwards doesn't change why it ended
    t.join(1)
    assert isinstance(out["error"], RelayCancelled)

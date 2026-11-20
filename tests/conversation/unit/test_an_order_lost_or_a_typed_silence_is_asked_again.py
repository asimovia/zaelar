"""An order the client could not read is asked for again, a run never ends with his request open, and a line typed to
the agent is answered (node 13.103, V2-941, v3.1 B7l — the B7k text re-run and the final personas).

The text re-run's stall, step by step: a read; a reply whose derived figure was refused, so a restate round; then a
`reply` the client DROPPED (its arguments were not valid JSON) — a step with no order. That step went to the no_reply
path, which asked for a repair and was then ignored: the run returned with its request open and nothing said, and the
liveness closed it 30 s later, with no run, so the door read an empty reply. Now:

  · a step with no order — text instead, or one the client could not read — is asked for its order once per run,
    whatever other repair it had; if the next has none either, he hears «I lost that» (never a no_reply);
  · a run that ends with a request of his still open, and its batch not handed back, fails with its line (`unended`);
  · the host's model port says which orders it dropped (`Done.usage["dropped"]`: names and reasons, never their words);
  · a `no_reply` on a batch he only TYPED is asked once for the reply, as one after reads is (a typed line is
    addressed to the agent); a second stands, silent and counted;
  · a disposable engine can hold the titular and shorten the first-event deadline, so the stand-in is driven live.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading

import pytest

from conversation.manager import run as R
from conversation.ports import Command, Done, ToolCall, ToolResult
from conversation.testing.scripted_model import reply
from conversation.types import Evidence
from nucleo.conversation_host import entry
from tests.conversation.unit.convkit import Harness

LOST = "w_lost"


class _Words:
    def line(self, key, near=""):
        return {"mute_lines": LOST, "unverified_fact": "w_honest"}.get(key, "")


@pytest.fixture
def door(monkeypatch):
    """The host's text door on the harness: what was said for the request when it closed."""
    w = {"iv": None, "future": concurrent.futures.Future(), "said": [], "reads": [], "ended": threading.Event()}
    monkeypatch.setattr(entry, "_waits", {"c1": w})
    at_close: list = []
    w["future"].add_done_callback(lambda f: at_close.append(" ".join(w["said"])))
    return w, at_close


def _h(store, rounds):
    h = Harness(store, grace=False)
    h.conv.words = _Words()
    emit, say = h.tel.emit, h.mouth.say

    def tel(kind, label, payload):
        emit(kind, label, payload)
        entry._listen(kind, label, payload)

    async def mouth(order):
        entry._said(order.request_id, order.text)
        await say(order)
    h.tel.emit, h.mouth.say = tel, mouth
    h.tools.answers["web_search"] = ToolResult("ok", {}, (Evidence("ev_t", "search", numbers=(1.3, 1.4)),))
    h.model.default = lambda ids: rounds[min(len(h.model.calls) - 1, len(rounds) - 1)]
    return h


def _commands(h):
    return [p.get("command") for k, lab, p in h.tel.events if k == "conv_run" and lab == "command"]


READ = [ToolCall("c1", "web_search", {"query": "w2"}), Done()]
#: a derived figure whose operands are one figure twice: refused (TF-3), so the run asks for the answer again
BLOCKED = [reply("w9 1.4", [{"entity": "", "period": "", "metric": "", "direction": "", "value": 1.4,
                             "evidence_id": "ev_t", "derived": True, "op": "mean", "operands": [1.4, 1.4]}]), Done()]
#: the client dropped the model's `reply`: the step ends with no order and no text
DROPPED = [Done({"finish_reason": "tool_calls", "dropped": [{"name": "reply", "reason": "w", "chars": 300}]})]


def test_the_re_runs_stall_an_order_dropped_after_a_restate_is_asked_again_and_answered(store, door):
    w, at_close = door
    h = _h(store, [READ, BLOCKED, DROPPED, [reply("w8"), Done()]])
    h.typed("w1", 0, cid="c1")
    h.settle(2000)
    cmds = _commands(h)
    assert "reply_blocked" in cmds and "no_order" in cmds and "unended" not in cmds, cmds
    assert h.model.calls[3].prompt.steps[-1][1].data["reason"] == R.UNREAD       # told why: its order was unreadable
    assert w["future"].result() == "answered" and at_close == ["w8"]


def test_a_second_step_with_no_order_tells_him_never_silence(store, door):
    w, at_close = door
    h = _h(store, [READ, BLOCKED, DROPPED])
    h.typed("w1", 0, cid="c1")
    h.settle(2000)
    assert _commands(h).count("no_order") == 3 and len(h.model.calls) == 4    # two steps, and the line said for it
    assert at_close == [LOST] and [(lab, p["reason"]) for lab, p in h.closes()] == [("recovered", "no_order")]
    assert not [lab for lab, _ in h.closes() if lab == "stalled"]


def test_a_run_that_ends_with_his_request_open_fails_with_its_line(store, door, monkeypatch):
    w, at_close = door

    async def forgets(conv, r, batch):           # any path that returns without closing what it ran for
        return None
    monkeypatch.setattr(R, "_steps", forgets)
    h = _h(store, [READ])
    h.typed("w1", 0, cid="c1")
    h.settle(2000)
    assert "unended" in _commands(h)
    assert w["future"].result() == "recovered" and at_close == [LOST]
    assert [(lab, p["reason"]) for lab, p in h.closes()] == [("recovered", "unended")]


def test_a_no_reply_to_a_typed_line_is_asked_once_for_the_reply(store, door):
    w, at_close = door
    h = _h(store, [[Command("no_reply", {"reason": "w0"}), Done()], [reply("w7"), Done()]])
    h.typed("w1", 0, cid="c1")
    h.settle(2000)
    assert "no_reply_typed" in _commands(h)
    assert h.model.calls[1].prompt.steps[-1][1].data["reason"] == R.TYPED_TO_YOU
    assert at_close == ["w7"]


def test_a_second_no_reply_to_a_typed_line_stands_silent_and_counted(store, door):
    w, at_close = door
    h = _h(store, [[Command("no_reply", {"reason": "w0"}), Done()]])
    h.typed("w1", 0, cid="c1")
    h.settle(2000)
    assert len(h.model.calls) == 2 and [lab for lab, _ in h.closes()] == ["silent"]
    ended = [p for k, lab, p in h.tel.events if k == "conv_run" and lab == "ended"]
    assert [(p["outcome"], p["typed_only"], p["after_reads"]) for p in ended] == [("no_reply", True, True)]


def test_the_model_port_says_which_orders_it_dropped_never_their_words():
    from conversation.ports import PromptParts
    from nucleo.conversation_host import model

    class _Client:
        async def stream(self, messages, *, metrics, on_tool_call, **kw):
            metrics["dropped_tool_calls"] = [{"name": "reply", "reason": "w_bad", "chars": 40, "args_head": "w_secret"}]
            yield ""

    async def events():
        port = model.FastModel(client=_Client(), spec="s1")
        return [ev async for ev in port.stream(PromptParts("P", "", "", "[iv_1] w1"), [], run_id="r", model_id="")]
    done = asyncio.run(events())[-1]
    assert done.usage["dropped"] == [{"name": "reply", "reason": "w_bad", "chars": 40}]
    assert "w_secret" not in repr(done.usage)


def test_a_disposable_engine_can_hold_the_titular_and_shorten_the_deadline(monkeypatch):
    from nucleo.conversation_host import config, model, sandbox
    monkeypatch.setenv(config.FIRST_MS_ENV, "3000")
    monkeypatch.setenv(model.HANG_TITULAR, "1")
    monkeypatch.setattr(sandbox, "is_sandbox", lambda: False)
    assert config.build({})[0].model_first_ms == 20_000 and not model._hangs()     # a real account: never
    monkeypatch.setattr(sandbox, "is_sandbox", lambda: True)
    assert config.build({})[0].model_first_ms == 3000 and model._hangs()

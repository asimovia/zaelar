"""A failed run of typed entries answers its door with the line, and a provider that sends nothing goes to its stand-in
(node 13.102, V2-941, the final text suite).

The text channel's door (`entry.typed_and_wait`) returns what was said for the request by the time it CLOSED. A failed
run said its line after closing, so the door read an empty reply on every `recovered` close: the line went out on the
wall, the answer at the door was nothing. Now the line is said before the close, and a request the liveness closed
while its run was still in course waits at the door for that run's end, where its line comes.

A provider timeout with nothing from the model yet is not a failure of the request: the same step goes once to the
stand-in (`ports.RELAY`; the host's model port asks the routing's relay for a provider other than the titular). A
deadline that passes after the model began is a failed run, with its line in place.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time

import pytest

from conversation.config import Config
from conversation.manager import run as R
from conversation.ports import RELAY, Done, Failed, TextDelta, ToolCall, ToolResult
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
    """The host's door on a harness: its telemetry and its mouth feed `entry._listen`/`entry._said` as the boot does,
    and the reply is read the moment the close resolves the door — the earliest the waiting caller can read it."""
    w = {"iv": None, "future": concurrent.futures.Future(), "said": [], "reads": [], "ended": threading.Event()}
    monkeypatch.setattr(entry, "_waits", {"c1": w})
    at_close: list = []
    w["future"].add_done_callback(lambda f: at_close.append(" ".join(w["said"])))
    return w, at_close


def _wire(h):
    emit, say = h.tel.emit, h.mouth.say

    def tel(kind, label, payload):
        emit(kind, label, payload)
        entry._listen(kind, label, payload)

    async def mouth(order):
        entry._said(order.request_id, order.text)        # the host's mouth reports what it says, then says it
        await say(order)
    h.tel.emit, h.mouth.say = tel, mouth
    return h


def _h(store, config=None):
    h = Harness(store, grace=False, config=config)
    h.conv.words = _Words()
    return _wire(h)


def _bad():
    return [{"entity": "", "period": "", "metric": "", "direction": "", "value": 999.0, "evidence_id": "ev_t"}]


def _figures_twice(h):
    """The honest line once, then a forced restate that fails too: the run fails `figures_unverified_again`."""
    h.tools.answers["market_data"] = ToolResult("ok", {}, (Evidence("ev_t", "search", numbers=(145.98,)),))
    rounds = [[ToolCall("c1", "market_data", {}), Done()], [reply("w9 999", _bad()), Done()]]
    h.model.default = lambda ids: rounds[min(len(h.model.calls) - 1 - h.n0, 1)]


def test_a_typed_run_that_fails_on_its_figures_answers_its_door_with_the_line(store, door):
    w, at_close = door
    h = _h(store)
    h.n0 = 0
    _figures_twice(h)
    h.typed("w1", 0, cid="c0")                           # the honest line is our last answer…
    h.settle(2000)
    h.n0 = len(h.model.calls)
    h.typed("w2", 20_000, cid="c1")                      # …so this one, failing again, fails the run
    h.settle(30_000)
    closes = [(lab, p.get("reason")) for lab, p in h.closes()]
    assert closes[-1] == ("recovered", "figures_unverified_again"), closes
    assert w["future"].result() == "recovered" and at_close == [LOST]


def test_a_typed_run_the_provider_fails_answers_its_door_with_the_line(store, door):
    w, at_close = door
    h = _h(store)
    h.model.default = lambda ids: [Failed("ReadError: ", "provider")]
    h.typed("w1", 0, cid="c1")
    h.settle(2000)
    assert w["future"].result() == "recovered" and at_close == [LOST]


class _Titular:
    """A provider that holds its stream and sends nothing (`hang`), unless asked for the stand-in."""

    def __init__(self, hang_after_text=False):
        self.calls: list[str] = []
        self.after_text = hang_after_text

    async def stream(self, prompt, tools, *, run_id, model_id):
        self.calls.append(model_id)
        if model_id == RELAY:
            yield reply("w-relayed")
            yield Done()
            return
        if self.after_text:
            yield TextDelta("w8")
        await asyncio.sleep(10)
        yield reply("w-late")


def test_a_timeout_before_the_model_said_anything_goes_once_to_the_stand_in(store, door):
    w, at_close = door
    h = _h(store, Config(model_first_ms=30))
    h.conv.model = _Titular()
    h.typed("w1", 0, cid="c1")
    h.settle(2000)
    assert h.conv.model.calls == ["", RELAY]
    assert w["future"].result() == "answered" and at_close == ["w-relayed"]
    assert [p.get("reason") for k, lab, p in h.tel.events if p.get("command") == "relay"] == ["provider:timeout"]


def test_a_timeout_after_the_model_began_fails_the_run_with_the_line_in_place(store, door):
    w, at_close = door
    h = _h(store, Config(model_gap_ms=30))
    h.conv.model = _Titular(hang_after_text=True)
    h.typed("w1", 0, cid="c1")
    h.settle(2000)
    assert h.conv.model.calls == [""]                    # never re-sent: the model had begun
    assert w["future"].result() == "recovered" and at_close == [LOST]
    assert [(lab, p["reason"]) for lab, p in h.closes()] == [("recovered", "provider:timeout")]


def test_a_request_the_liveness_closes_during_its_run_waits_at_the_door_for_the_line(store, door):
    w, _at_close = door
    h = _h(store)

    def stall():
        h.at(h.clock.mono + h.conv.cfg.liveness_ms + 100)
        R.sweep_liveness(h.conv, h.clock.now_ms())
    h.model.default = lambda ids: [stall, reply("w9"), Done()]
    h.typed("w1", 10, cid="c1")
    h.settle(2000)
    assert w["future"].result() == "stalled" and w["run"] and w["ended"].is_set() and w["said"] == [LOST]


def test_the_door_waits_for_the_runs_end_and_never_past_its_deadline():
    w = {"iv": "iv_1", "future": concurrent.futures.Future(), "said": [], "reads": [], "ended": threading.Event(),
         "run": "run_1"}
    w["future"].set_result("stalled")

    def later():
        time.sleep(0.2)
        w["said"].append(LOST)
        w["ended"].set()
    threading.Thread(target=later).start()
    assert asyncio.run(entry._closed(w, 5)) == "stalled" and w["said"] == [LOST]
    alone = dict(w, said=[], ended=threading.Event(), run=None)          # closed with no run: nothing to wait for
    t0 = time.monotonic()
    assert asyncio.run(entry._closed(alone, 5)) == "stalled" and time.monotonic() - t0 < 1
    never = dict(w, said=[], ended=threading.Event())                    # its run never ends: the deadline holds
    t0 = time.monotonic()
    assert asyncio.run(entry._closed(never, 0.3)) == "stalled" and time.monotonic() - t0 < 1


def test_the_model_port_asks_the_routing_for_the_stand_in(monkeypatch):
    from nucleo.conversation_host import model
    from nucleo.llm import fast_client
    seen = []

    class _Client:
        async def stream(self, messages, *, spec, **kw):
            seen.append(spec)
            yield ""
    monkeypatch.setattr(fast_client, "relay_spec_for", lambda spec, role: f"relay-of-{spec}" if spec == "s1" else None)
    port = model.FastModel(client=_Client(), spec="s1")

    async def events(model_id, p):
        from conversation.ports import PromptParts
        return [ev async for ev in p.stream(PromptParts("P", "", "", "[iv_1] w1"), [], run_id="r", model_id=model_id)]
    asyncio.run(events(RELAY, port))
    asyncio.run(events("", port))
    assert seen == ["relay-of-s1", "s1"]
    alone = model.FastModel(client=_Client(), spec="s2")                 # nobody else to ask: a provider failure
    got = asyncio.run(events(RELAY, alone))
    assert [type(e).__name__ for e in got] == ["Failed"] and got[0].reason == "no stand-in"

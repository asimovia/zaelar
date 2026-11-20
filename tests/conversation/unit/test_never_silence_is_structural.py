"""«Never silence» is structural, not a sentence of the prompt (node 13.88, V2-941, the audit of B4c–B7e).

  · a run the liveness closes `stalled` still owes him its line: said in place on a typed batch, owed on his voice —
    never a request closed with nothing heard (TF-1); a mouth that raises while saying the failure line is a line
    owed, never an exception out of the pump, and the batch is accounted first;
  · if the conversation cannot open, the opener tries again with an alert each time; then a typed line takes its old
    way at its door, never left waiting for the next line (TF-2);
  · a derived figure's operands are DISTINCT figures of its evidence: `count` of one figure repeated counts nothing,
    and a value refused in this run cannot come back by counting (TF-3);
  · a figure as a person says it matches: rounded to fewer significant digits, a percent and its fraction — and nothing
    else;
  · an order written as the reply's words is never said (a repair, then the failure line), and a no_reply after an act
    the gateway refused is asked once to say it; what is left is counted on `ended`.
"""
from __future__ import annotations

import asyncio

import pytest

from conversation.manager import run as R
from conversation.manager.claims import Claim, check
from conversation.store.memory import MemoryStore
from conversation.ports import Command, Done, ToolCall
from conversation.testing.scripted_model import reply
from conversation.types import Evidence
from tests.conversation.unit.convkit import Harness


class _Words:
    def line(self, key):
        return {"mute_lines": "w_lost", "unverified_fact": "w_honest"}.get(key, "")


def _h(store):
    h = Harness(store, grace=False)
    h.conv.words = _Words()
    return h


def _stalling(h):
    def stall():
        h.at(h.clock.mono + h.conv.cfg.liveness_ms + 100)
        R.sweep_liveness(h.conv, h.clock.now_ms())
    h.model.default = lambda ids: [stall, reply("w9"), Done()]


def test_a_typed_request_the_liveness_closes_hears_the_line_in_place(store):
    h = _h(store)
    _stalling(h)
    h.typed("w1", 10)
    h.settle(2000)
    assert [(lab, p["reason"]) for lab, p in h.closes()] == [("stalled", "stalled")]
    assert [(o.text, tuple(sorted(o.channels))) for o in h.mouth.orders] == [("w_lost", ("text",))]
    assert h.owed.rows == {}


def test_his_voice_the_liveness_closes_is_owed_the_line(store):
    h = _h(store)
    _stalling(h)
    h.utter([(["w1"], 0)])
    assert "conv:failed:r_iv_000001" in h.owed.rows and "w9" not in [o.text for o in h.mouth.orders]


def test_a_mouth_that_raises_on_the_failure_line_owes_it_and_escapes_nothing(store):
    from conversation.ports import Failed
    h = _h(store)
    h.model.default = lambda ids: [Failed("w_boom", "provider")]

    whole = h.conv.speaker.say

    async def broken(**kw):                                                    # the failure line cannot be said
        if kw.get("origin") == "failure":
            raise RuntimeError("w_mouth")
        return await whole(**kw)
    h.conv.speaker.say = broken
    h.typed("w1", 10)
    h.settle(2000)                                                            # nothing raised out of the pump
    assert "conv:failed:r_iv_000001" in h.owed.rows
    ended = [p for k, lab, p in h.tel.events if k == "conv_run" and lab == "ended"]
    assert [(p["outcome"], p["said"]) for p in ended] == [("failed", False)]
    assert "mouth_failed" in [p.get("command") for k, lab, p in h.tel.events if k == "conv_run"]


PAGE = Evidence("e", "search", numbers=(18.0, 2026.0, 3.0, 1.234, 1234.0, 186.52))


@pytest.mark.parametrize("claim", [dict(value=12, op="count", operands=[18] * 12),
                                   dict(value=30, op="sum", operands=[3] * 10),
                                   dict(value=13, op="count", operands=[18, 3] * 6 + [186.52])])
def test_a_derived_figure_counts_distinct_figures_of_its_evidence(claim):
    got = check([Claim.from_args({**claim, "evidence_id": "e", "derived": True})], {"e": PAGE}, frozenset({"e"}))
    assert [w for _c, w in got] == ["operand"]
    ok = Claim.from_args({"value": 3, "op": "count", "operands": [18, 3, 186.52], "evidence_id": "e", "derived": True})
    assert check([ok], {"e": PAGE}, frozenset({"e"})) == []


@pytest.mark.parametrize("value, figure, passes", [(18, 18.3, True), (18, 19.6, False), (5e6, 4_987_210, True),
                                                   (5, 4.98, True), (6, 4.98, False), (5, 0.0498, True),
                                                   (999, 1105.34, False)])
def test_a_figure_as_a_person_says_it(value, figure, passes):
    ev = Evidence("t", "search", numbers=(figure,))
    assert (check([Claim.from_args({"value": value, "evidence_id": "t"})], {"t": ev}) == []) is passes


def _commands(h):
    return [p.get("command") for k, lab, p in h.tel.events if k == "conv_run" and lab == "command"]


def test_an_order_written_as_the_reply_is_never_said(store):
    h = _h(store)
    rounds = [[reply('no_reply(reason="w1")'), Done()], [reply("<reply>w2"), Done()]]
    h.model.default = lambda ids: rounds[min(len(h.model.calls) - 1, len(rounds) - 1)]
    h.typed("w1", 10)
    h.settle(2000)
    assert [o.text for o in h.mouth.orders] == ["w_lost"] and _commands(h).count("order_as_text") >= 2
    rounds[1] = [reply("w8"), Done()]
    h2 = _h(MemoryStore())                                                    # a second conversation of its own
    h2.model.default = lambda ids: rounds[min(len(h2.model.calls) - 1, len(rounds) - 1)]
    h2.typed("w1", 10)
    h2.settle(2000)
    assert [o.text for o in h2.mouth.orders] == ["w8"]                       # repaired: the answer itself


def test_a_no_reply_after_a_refused_act_is_asked_once_to_say_it(store):
    h = _h(store)
    send = [ToolCall("c1", "send_message", {"to": "w2", "text": "w3"}), Done()]
    rounds = [send, [Command("no_reply", {"reason": "w4"}), Done()], [reply("w_cannot"), Done()]]
    h.model.default = lambda ids: rounds[min(len(h.model.calls) - 1, len(rounds) - 1)]
    h.typed("w1", 10)
    h.settle(2000)
    assert [o.text for o in h.mouth.orders] == ["w_cannot"] and "no_reply_after_refused_act" in _commands(h)
    asked = h.model.calls[2].prompt.steps[-1][1].data                     # the round that asked it
    assert asked["refused_act"] == ["send_message"]
    h2 = _h(MemoryStore())                                                    # a second conversation of its own
    rounds2 = [send, [Command("no_reply", {"reason": "w4"}), Done()]]
    h2.model.default = lambda ids: rounds2[min(len(h2.model.calls) - 1, len(rounds2) - 1)]
    h2.typed("w1", 10)
    h2.settle(2000)
    ended = [p for k, lab, p in h2.tel.events if k == "conv_run" and lab == "ended"]
    assert ended[-1]["outcome"] == "no_reply" and ended[-1]["after_refused_act"] and ended[-1]["typed_only"]


@pytest.fixture
def opener(monkeypatch):
    from nucleo.conversation_host import entry
    from voice import observer
    alerts = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: alerts.append(label) if kind == "alert" else None)
    monkeypatch.setattr(entry, "OPEN_BACKOFF_S", 0.0)
    entry.reset()
    yield entry, alerts
    entry.reset()


def test_a_conversation_that_opens_late_still_takes_the_line(opener, monkeypatch):
    entry, alerts = opener
    got, tries = [], {"n": 0}

    class _Rt:
        def alive(self):
            return True

        def submit(self, fn):
            fn(type("C", (), {"hear": lambda self, sig: got.append(sig.text)})())

    def runtime():
        tries["n"] += 1
        if tries["n"] < 3:
            raise TimeoutError("w_lease")
        return _Rt()
    monkeypatch.setattr(entry, "runtime", runtime)
    entry.typed("w1", "d1", checked=True)
    entry._opener["t"].join(5)
    assert got == ["w1"] and alerts.count("the conversation could not open") == 2


def test_a_conversation_that_never_opens_sends_the_typed_line_back_to_its_door(opener, monkeypatch):
    entry, alerts = opener

    def runtime():
        raise TimeoutError("w_lease")
    monkeypatch.setattr(entry, "runtime", runtime)

    async def go():
        return await entry.typed_and_wait("w1", "text:s1", timeout_s=5)
    monkeypatch.setattr(entry, "_guards", lambda text, dev: None)
    out = asyncio.run(go())
    assert out["conv"]["close"] == entry.NOT_OPENED and not entry._queue
    assert "a typed line went the old way: the conversation could not open" in alerts

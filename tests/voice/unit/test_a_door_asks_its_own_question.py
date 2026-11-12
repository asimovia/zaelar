"""Node 3.197 — a question only one door reads is asked AT that door, into the turn's brief (V2-887 step 8).

The turn's one trip no longer carries the acts he asked, the errand's class / kind / capability gap, the channel he
named or a rename (`nucleo/turn/brief_doors`). Each is asked when its door is reached — and what reaches a door is
something the engine DID (a model call, a launch, an act that leaves, a parked directive), never his words. Pinned:

  · admission asks none of them (one trip, the turn's own questions);
  · a door fires on its trigger only, once per handle, and its verdicts are MERGED into the same handle, so every
    reader keeps `verdicts.read(brief, key, …)`; a door verdict still flying reads as the fallback, said `in_flight`;
  · nothing waits on the voice loop: an async door awaits off the loop, a sync door on the loop only fires.
"""
from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from nucleo import jev
from nucleo.turn import brief as tb, brief_doors, verdicts


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setattr(jev, "_read_key", lambda: "k-for-tests")
    monkeypatch.delenv("ZAELAR_JEV", raising=False)
    jev.reset_breaker()

    class _Wire:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.answers: dict = {"escalate_or_inline": ("handle_inline", 0.95)}
            self.slow: dict = {}          # key -> seconds the trip that asks it takes

        def __call__(self, state, questions, timeout_s):
            time.sleep(max([self.slow.get(k, 0.0) for k in questions] or [0.0]))
            self.calls.append({"state": state, "questions": set(questions)})
            out = {}
            for key, q in questions.items():
                choice, conf = self.answers.get(key, (next(iter(q["criteria"])), 0.95))
                out[key] = {"choice": choice, "confidence": conf, "probabilities": {choice: conf}}
            return {"answers": out}

    w = _Wire()
    monkeypatch.setattr(jev, "_post_many", w)
    return w


def _admitted(text="mándale un whatsapp a Raquel y márcala como favorita", **kw):
    h = tb.ask(text, open_ids=kw.pop("open_ids", []), **kw)
    h["event"].wait(2.0)
    return h


def _door(h, door, t=2.0):
    ev = (h.get("_doors") or {}).get(door)
    assert ev is not None, f"the {door} door never fired"
    assert ev.wait(t)
    return ev


def test_admission_asks_no_door_question(wire):
    _admitted()
    assert len(wire.calls) == 1
    assert not wire.calls[0]["questions"] & set(brief_doors.keys()), wire.calls[0]["questions"]


def test_a_model_call_fires_the_call_door_once_and_merges_into_the_brief(wire):
    from nucleo.turn import route_by_verdict as route
    from nucleo.turn import acts_asked
    h = _admitted()
    wire.answers[acts_asked.KEY] = ("several", 0.96)
    ran = []
    call = route.gate_calls(lambda n, a: ran.append(n), brief=h, escalate_req={"v": None}, operator_text="x",
                            emit=lambda *a, **k: None, t0=time.monotonic(), wait=0.0)
    call("set_timer", {})
    call("set_timer", {})            # a second call of the same turn: the door already fired
    _door(h, "call")
    assert ran == ["set_timer", "set_timer"]
    assert [c["questions"] for c in wire.calls[1:]] == [{acts_asked.KEY}], wire.calls
    assert acts_asked.several(h), "the door's verdict reads through the same handle"
    assert wire.calls[1]["state"] == h["judged"], "the door asks about the sentence the brief judged"


def test_an_escalation_call_fires_the_portal_with_its_three_questions(wire):
    from nucleo.acts import errand
    from nucleo.request import kind
    from nucleo.turn import route_by_verdict as route
    h = _admitted("búscame un piso en Madrid y resérvame una visita")
    wire.answers[errand.CLASS_KEY] = ("sends_for_him", 0.9)
    wire.answers[kind.KEY] = ("web", 0.9)
    call = route.gate_calls(lambda n, a: None, brief=h, escalate_req={"v": None}, operator_text="x",
                            emit=lambda *a, **k: None, t0=time.monotonic(), wait=0.0)
    call("escalate_to_slowbrain", {"request": "x"})
    _door(h, "portal")
    asked = wire.calls[1]["questions"]
    assert {errand.CLASS_KEY, kind.KEY} <= asked and asked <= {errand.CLASS_KEY, kind.KEY, "capability_gap"}
    assert errand.class_verdict(h)["choice"] == "sends_for_him" and kind.verdict(h)["choice"] == "web"
    assert "call" not in h["_doors"], "an escalation is the portal's trigger, not the acts door's"


def test_a_door_verdict_still_flying_reads_as_the_fallback_and_says_in_flight(wire, monkeypatch):
    from nucleo.turn import acts_asked
    seen = []
    monkeypatch.setattr(jev, "_emit_read", lambda handle, key, **kw: seen.append((key, kw["why"])))
    h = _admitted()
    wire.slow[acts_asked.KEY] = 0.4
    brief_doors.fire(h, "call")
    assert verdicts.read(h, acts_asked.KEY, "fallback") == ("fallback", None)
    assert (acts_asked.KEY, "in_flight") in seen
    _door(h, "call")
    assert verdicts.read(h, acts_asked.KEY, "fallback")[0] != "fallback"


def test_the_rename_door_is_the_directive_call(wire, monkeypatch):
    from nucleo.acts import tools
    from nucleo.flash import style_directive
    from nucleo.turn import identity
    monkeypatch.setattr(style_directive, "handle", lambda *a, **k: False)
    h = _admitted("llámate Johnny")
    c = SimpleNamespace(_brief=h, _spawn=None, brain=SimpleNamespace(), emit=lambda *a, **k: None,
                        style_fired={"v": False}, text="llámate Johnny")
    tools.set_style_directive({"directive": "call yourself Johnny", "name": "Johnny"}, c)
    _door(h, "rename")
    assert wire.calls[1]["questions"] == {identity.KEY}


def test_the_exit_asks_his_channel_into_the_carried_reading(wire):
    from nucleo.acts import message_channel as mc
    h = _admitted()
    reading = tb.carried(h)
    assert mc.KEY not in reading["result"] and reading["judged"]
    plats = list(mc.question()["criteria"])
    wire.answers[mc.KEY] = (plats[0], 0.95)
    turn = tb.revived(reading)                # the exit's revived handle (`exit_gate.cross`): its landing is kept
    assert asyncio.run(brief_doors.landed(turn, "send"))
    assert reading["result"][mc.KEY]["choice"] == plats[0], "kept for the task's next exit"
    n = len(wire.calls)
    assert asyncio.run(brief_doors.landed(tb.revived(reading), "send")) is False and len(wire.calls) == n, \
        "answered once: never re-asked"


def test_no_door_waits_on_the_voice_loop(wire):
    from nucleo.turn import acts_asked
    h = _admitted()
    wire.slow[acts_asked.KEY] = 0.5

    async def _turn():
        ticks = 0

        async def _ticker():
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0.01)
        task = asyncio.get_running_loop().create_task(_ticker())
        got = await brief_doors.landed(h, "call", 2.0)          # an async door awaits OFF the loop
        task.cancel()
        return got, ticks

    got, ticks = asyncio.run(_turn())
    assert got and ticks > 20, f"the loop stalled while the door was awaited ({ticks} ticks)"


def test_no_brief_or_no_sentence_fires_nothing(wire):
    assert brief_doors.fire(None, "call") is None
    ev = threading.Event()
    ev.set()
    assert brief_doors.fire({"event": ev, "result": {}, "judged": ""}, "portal") is None
    assert wire.calls == []

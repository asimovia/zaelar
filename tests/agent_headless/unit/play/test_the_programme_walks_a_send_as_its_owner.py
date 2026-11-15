"""With the stage `own` on, the programme walks a send as the owner of its row (V2-909 P7-P8, `nucleo/play/send.py`).

The walk passes the same doors as the path without the stage: the card's run (the exit door inside it), then — only
once the card returned — the look at the row's declared end state, then the one writer settles the row, then ONE
report by the circuit's out-of-turn mouth. When the exit door asks him, the walk parks and his yes walks it on from
the same step. A card that refuses or raises ends `failed` and is never looked at; an echo that does not land in the
look's time — which outlasts the window the circuit owes an end state — ends `unverified` and leaves the row to the circuit; a row someone else settled is not told twice. While a
walk is out, no line of a turn may claim an outcome for its act (`live`, read by `unserved.outcomes`). One walk per
row at a time; a walk that breaks leaves nothing live. `send_task._schedule` hands the row to the walk only with the
stage on. The driver parks on `{"parked": True}` and resumes at that step.

Disarm: the unserved line ignores live walks; the look settles without the end state; the look's time back under the
circuit's window; `_schedule` ignores the stage → four reds.
"""
from __future__ import annotations

import asyncio
import importlib
import pathlib
import shutil
import time

import pytest

from nucleo.play import run as driver
from nucleo.play import send, switch
from nucleo.play import state as st

ROOT = pathlib.Path(__file__).resolve().parents[4]
UID = "T1"


def _art(wid="mensajeria", action="send_to"):
    return {"widget": wid, "action": action, "payload": {"contact": "R", "channel": "whatsapp", "text": "hello"},
            "slots": {"recipient": {"key": "contact", "source": "his"},
                      "channel": {"key": "channel", "source": "his"},
                      "text": {"key": "text", "source": "his"}}}


class Engine:
    """The engine pieces the walk touches, faked: every call is recorded in `log`, in order."""

    def __init__(self, monkeypatch):
        from nucleo import circuit
        from nucleo.circuit import ledger, spec
        from nucleo.request import send_task, send_task_run
        from voice import observer
        self.log: list = []
        self.entry = {"row": UID, "done_when": {}}
        self.owed = True
        self.attests = [True]
        self.result: object = {"ok": True}
        self.during = None                   # async callable run while the card is out
        self.verdict = {"verdict": "met"}
        self.art = _art()
        monkeypatch.setattr(switch, "stage", lambda name: name == "own")
        monkeypatch.setattr(send, "LOOK_EVERY_S", 0.001)
        monkeypatch.setattr(send_task, "artefact", self._artefact)
        monkeypatch.setattr(send_task_run, "run", self._run)
        monkeypatch.setattr(spec, "open_specs", lambda now=None: [self.entry] if self.owed else [])
        monkeypatch.setattr(spec, "attest", self._attest)
        monkeypatch.setattr(circuit, "settle", lambda e=None, **kw: self.log.append(("settle", kw.get("verdict"))))
        monkeypatch.setattr(circuit, "_say_now", lambda e, missing, **kw: self.log.append(("say", kw.get("fact"))))
        monkeypatch.setattr(ledger, "get", lambda uid: self.verdict)
        monkeypatch.setattr(observer, "emit", lambda *a, **k: None)

    def _artefact(self, uid):
        if isinstance(self.art, Exception):
            raise self.art
        return self.art

    async def _run(self, uid):
        self.log.append(("run", uid))
        if self.during is not None:
            await self.during()
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def _attest(self, e, now=None):
        self.log.append(("attest",))
        return self.attests.pop(0) if self.attests else False

    def names(self):
        return [x[0] for x in self.log]


@pytest.fixture
def eng(monkeypatch):
    send._walks.clear()
    send._running.clear()
    yield Engine(monkeypatch)
    send._walks.clear()
    send._running.clear()


def _walk():
    return asyncio.run(send.walk(UID))


def test_a_send_walks_the_card_then_the_look_then_one_settle_and_one_report(eng):
    from nucleo import circuit
    eng.attests = [False, False, True]
    end = _walk()
    assert eng.names() == ["run", "attest", "attest", "attest", "settle", "say"]
    assert ("settle", "met") in eng.log and [x for x in eng.log if x[0] == "say"] == [("say", circuit.SENT)]
    assert (end["step"], end["outcome"]) == ("reported", "done")
    assert eng.entry["reported"] is True


def test_the_end_state_is_never_read_before_the_card_returned(eng):
    seen = []

    async def slow():
        await asyncio.sleep(0.05)
        seen.append(eng.names().count("attest"))
    eng.during = slow
    end = _walk()
    assert seen == [0] and end["outcome"] == "done"


def test_the_exit_door_asking_parks_the_walk_and_his_yes_walks_it_on(eng):
    eng.result = {"ok": False, "asked": "q1", "row": UID}
    parked = _walk()
    assert (parked["step"], parked["outcome"]) == ("executing", "")
    assert eng.names() == ["run"]
    eng.result = {"ok": True}
    end = _walk()
    assert (end["step"], end["outcome"]) == ("reported", "done")
    assert eng.names() == ["run", "run", "attest", "settle", "say"]
    assert end["said"]["announce"] == [""]                  # the announce line is not said twice


@pytest.mark.parametrize("result", [{"ok": False, "error": "channel_down"}, RuntimeError("connector")])
def test_a_card_that_refuses_or_raises_fails_and_is_never_looked_at(eng, result):
    eng.result = result
    end = _walk()
    assert end["outcome"] == "failed"
    assert eng.names() == ["run"]


def test_an_echo_that_does_not_land_in_the_look_time_ends_unverified_and_the_circuit_keeps_the_row(eng, monkeypatch):
    monkeypatch.setitem(st._TABLE, "deadline_s", {**st._TABLE["deadline_s"], "verifying": 0.05})
    monkeypatch.setattr(send, "LOOK_EVERY_S", 0.005)
    eng.attests = []
    end = _walk()
    assert end["outcome"] == "unverified"
    assert "settle" not in eng.names() and "say" not in eng.names()
    assert not eng.entry.get("reported")


def test_the_look_outlasts_the_window_the_circuit_owes_an_end_state():
    """The card returns when the send is queued; the circuit owes its end state for `INLINE_GRACE_S` and reads it every
    `CHECK_EVERY_S`. A shorter look ends `unverified` on a send that lands, and the sent line is left to nobody."""
    from nucleo import circuit
    assert float(st._TABLE["deadline_s"]["verifying"]) >= circuit.INLINE_GRACE_S + circuit.CHECK_EVERY_S


def test_a_row_someone_else_settled_is_done_and_the_walk_says_nothing(eng):
    eng.owed = False
    eng.verdict = {"verdict": "met"}
    end = _walk()
    assert end["outcome"] == "done"
    assert "say" not in eng.names() and "settle" not in eng.names()


def test_live_holds_only_while_a_walk_is_out_and_within_its_deadline(eng):
    seen = []

    async def check():
        seen.append((send.live("mensajeria", "send_to"), send.live("mensajeria::x", "send_to"),
                     send.live("mensajeria", "read")))
    eng.during = check
    _walk()
    assert seen == [(True, True, False)]
    assert send.live("mensajeria", "send_to") is False
    old = st.new("mensajeria", "send_to", now=time.monotonic() - 1000)
    old["step"] = "executing"
    send._walks["T2"] = old
    assert send.live("mensajeria", "send_to") is False


def _outcomes():
    from nucleo.turn import unserved
    return unserved.outcomes([], [{"name": "widget_data"}], said="I write to her now", quiet=False)


def test_no_line_of_the_turn_claims_an_outcome_for_a_live_walk(eng, monkeypatch):
    from nucleo.turn import unserved
    monkeypatch.setattr(unserved, "calls_not_run", lambda calls, tasks: [("mensajeria", "send_to")])
    got = {}

    async def during():
        got["on"] = _outcomes()
        monkeypatch.setattr(switch, "stage", lambda name: False)
        got["off"] = _outcomes()
        monkeypatch.setattr(switch, "stage", lambda name: name == "own")
    eng.during = during
    _walk()
    assert got["on"] == []
    assert len(got["off"]) == 1
    assert len(_outcomes()) == 1                             # stage on, no walk out


def test_one_walk_per_row_at_a_time(eng):
    second = []

    async def again():
        second.append(await send.walk(UID))
    eng.during = again
    end = _walk()
    assert second == [None] and end["outcome"] == "done"
    assert eng.names().count("run") == 1


def test_schedule_hands_the_row_to_the_walk_only_with_the_stage_on(eng, monkeypatch):
    from nucleo.request import send_task
    started = []
    monkeypatch.setattr(send, "start", lambda uid: started.append(uid))
    send_task._schedule(UID)
    assert started == [UID] and "run" not in eng.names()

    monkeypatch.setattr(switch, "stage", lambda name: False)

    async def go():
        send_task._schedule(UID)
        await asyncio.sleep(0.01)
    asyncio.run(go())
    assert started == [UID] and eng.names() == ["run"]


def test_a_walk_that_breaks_returns_none_and_leaves_nothing_live(eng):
    eng.art = RuntimeError("store")
    assert _walk() is None
    assert send.live("mensajeria", "send_to") is False and UID not in send._walks


class Parking:
    def __init__(self):
        self.calls, self.said, self.result = [], [], {"parked": True}

    async def resolve(self, state):
        self.calls.append("resolve")
        return {"slots": {"text": {"value": "hello", "source": "his"}}}

    async def answer(self, state, slot):
        return None

    async def consent(self, state):
        return "yes"

    async def execute(self, state):
        self.calls.append("execute")
        return self.result

    async def look(self, state):
        self.calls.append("look")
        return True

    def say(self, kind, value, state):
        self.said.append((kind, value))


def test_the_driver_parks_on_a_waiting_executor_and_resumes_at_that_step():
    h = Parking()
    s = st.new("mensajeria", "send_to", {"confirm": False, "leaves": True, "verify": "check"})
    parked = asyncio.run(driver.run(s, h))
    assert parked["step"] == "executing" and parked["outcome"] == ""
    assert not [x for x in h.said if x[0] == "report"]
    h.result = {"ok": True}
    end = asyncio.run(driver.run(parked, h))
    assert h.calls == ["resolve", "execute", "execute", "look"]
    assert end["outcome"] == "done" and h.said == [("announce", ""), ("report", "done")]


def _disarm(path, old, new, module, *tests):
    src = ROOT / path
    orig = src.read_text(encoding="utf-8")
    assert old in orig, f"the disarm no longer matches {path}"
    try:
        src.write_text(orig.replace(old, new), encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        assert old not in src.read_text(encoding="utf-8")
        importlib.reload(module)
        for t in tests:
            with pytest.raises(AssertionError):
                t()
    finally:
        src.write_text(orig, encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        importlib.reload(module)


def test_disarmed_the_walk_and_its_doors_turn_red():
    """Disarm: (a) `_own_rows_out` keeps every missed act; (b) the look settles without the end state;
    (c) the look's time back to 4 s; (d) `_schedule` ignores the stage."""
    from nucleo.request import send_task
    from nucleo.turn import unserved

    def fresh():
        mp = pytest.MonkeyPatch()
        send._walks.clear()
        send._running.clear()
        return mp, Engine(mp)

    def case(fn):
        def go():
            mp, e = fresh()
            try:
                fn(e, mp) if fn.__code__.co_argcount > 1 else fn(e)
            finally:
                mp.undo()
        return go

    _disarm("nucleo/turn/unserved.py",
            "        return [(c, a) for c, a in missed or () if not (_own.enabled() and _own.live(c, a))]\n",
            "        return list(missed or ())\n", unserved,
            case(test_no_line_of_the_turn_claims_an_outcome_for_a_live_walk))
    _disarm("nucleo/play/send.py", "            if spec.attest(e) is True:\n", "            if True:\n", send,
            case(test_an_echo_that_does_not_land_in_the_look_time_ends_unverified_and_the_circuit_keeps_the_row))
    _disarm("nucleo/play/table.json", '"verifying": 26}', '"verifying": 4}', st,
            test_the_look_outlasts_the_window_the_circuit_owes_an_end_state)
    _disarm("nucleo/request/send_task.py",
            "    if _own.enabled():           # V2-909: the programme walks the row — same door, same card, one report\n"
            "        return _own.start(uid)\n", "", send_task,
            case(test_schedule_hands_the_row_to_the_walk_only_with_the_stage_on))

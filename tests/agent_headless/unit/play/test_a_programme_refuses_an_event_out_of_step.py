"""The programme of a declared action is linear, and its order is the table's (V2-909, `nucleo/play/state.py`).

Every step × every event: a move the table declares is taken, any other is refused and changes nothing. The end state
is looked at only after the executor returned; an outcome exists only after that look; a line is said in its own steps
and once; an action that asks is never executed before his yes; every waiting step has a deadline that ends it.

Disarm: `advance` accepts an event the step does not declare → red.
"""
from __future__ import annotations

import importlib
import pathlib
import shutil

import pytest

from nucleo.play import state as st

ROOT = pathlib.Path(__file__).resolve().parents[4]
PAIRS = [(s, e) for s in st.STEPS for e in sorted(st.EVENTS)]
HIS = {"recipient": {"value": "R", "source": "his"}, "text": {"value": "hello", "source": "his"}}


def _at(step: str, **prog) -> dict:
    s = st.new("mensajeria", "send_to", {"confirm": False, "leaves": True, "verify": "check", **prog})
    s["step"] = step
    return s


def _run(events, **prog) -> dict:
    s = st.new("mensajeria", "send_to", {"confirm": False, "leaves": True, "verify": "check", **prog})
    for ev in events:
        ev, slots = ev if isinstance(ev, tuple) else (ev, None)
        m = st.advance(s, ev, slots=slots)
        assert m.ok, f"{ev} refused at {s['step']}: {m.why}"
        s = m.state
    return s


@pytest.mark.parametrize("step,event", PAIRS)
def test_an_event_moves_only_where_the_table_says(step, event):
    before = _at(step, confirm=True)
    m = st.advance(before, event)
    declared = event in st.MOVES[step]
    assert m.ok is declared
    if not declared:
        assert m.state["step"] == step and m.why          # refused: the step did not move
        assert m.state["refused"] == 1
    assert before["step"] == step                         # the caller's state is never written in place


def test_a_dictated_action_runs_to_its_report():
    s = _run(["start", ("resolved", HIS), "returned", "check", "landed"])
    assert (s["step"], s["outcome"]) == ("done", "done")
    said = st.say(s, "report", "sent")
    assert said.ok and said.state["step"] == st.LAST and said.state["outcome"] == "done"


def test_the_end_state_is_never_read_before_the_executor_returned():
    """No chain of legal events reaches `verifying` or `done` without passing `executed`."""
    seen, frontier = {st.FIRST}, [st.FIRST]
    while frontier:
        step = frontier.pop()
        for target in st.MOVES[step].values():
            if target not in seen and target != "executed":
                seen.add(target)
                frontier.append(target)
    assert "verifying" not in seen and "done" not in seen
    assert set(st.MOVES["executing"].values()) >= {"executed"}
    for step in st.STEPS:                                  # `executed` is entered by the return, nothing else
        for event, target in st.MOVES[step].items():
            assert (target == "executed") is (step == "executing" and event == "returned")


@pytest.mark.parametrize("source,asks", [("his", False), ("reading", False), ("held", False), ("card", False),
                                         ("agent", True), ("stranger", True), ("unknown", True)])
def test_a_leaving_action_asks_when_the_agent_chose_a_slot(source, asks):
    slots = {**HIS, "channel": {"value": "email", "source": source}}
    s = _run(["start", ("resolved", slots)])
    assert s["step"] == ("confirming" if asks else "executing")


def test_an_action_that_declares_confirm_is_never_executed_before_his_yes():
    s = _run(["start", ("resolved", HIS)], confirm=True)
    assert s["step"] == "confirming"
    assert not st.advance(s, "returned").ok and not st.advance(s, "landed").ok
    assert st.advance(s, "no").state["outcome"] == "cancelled"
    assert st.advance(s, "yes").state["step"] == "executing"
    assert st.advance(s, "change").state["step"] == "resolving"


def test_a_home_action_with_an_agent_slot_does_not_ask():
    s = st.new("agenda", "add", {"confirm": False, "leaves": False, "verify": "check"})
    s = st.advance(st.advance(s, "start").state, "resolved",
                   slots={"title": {"value": "x", "source": "agent"}}).state
    assert s["step"] == "executing"


def test_an_absent_end_state_is_looked_at_once_more_then_fails():
    s = _run(["start", ("resolved", HIS), "returned", "check"])
    again = st.advance(s, "absent")
    assert again.ok and again.state["step"] == "verifying" and again.state["tries"] == 1
    assert st.advance(again.state, "absent").state["outcome"] == "failed"


@pytest.mark.parametrize("step", [s for s in st.STEPS if s not in st.ENDS and s != st.LAST])
def test_every_step_that_waits_has_a_deadline_that_ends_it(step):
    if step in ("understood", "executed"):                 # entered and left in the same breath: nothing waits
        assert st.due(_at(step), 10 ** 9) == ""
        return
    s = _at(step)
    assert st.due(s, 0.0) == "" and st.due(s, 10 ** 6) == "timeout"
    ended = st.advance(s, "timeout")
    assert ended.ok and ended.state["step"] in st.ENDS


@pytest.mark.parametrize("step", st.STEPS)
def test_an_outcome_is_said_only_once_it_exists(step):
    m = st.say(_at(step), "report", "sent")
    assert m.ok is (step in st.ENDS)


def test_each_line_is_said_once_and_in_its_own_step():
    s = _run(["start", "missing"])
    first = st.say(s, "ask", "recipient")
    assert first.ok and not st.say(first.state, "ask", "recipient").ok       # asked once per slot
    assert st.say(first.state, "ask", "channel").ok                          # another slot is another question
    assert not st.say(s, "announce").ok and not st.say(s, "confirm").ok
    done = _run(["start", ("resolved", HIS), "returned", "check", "landed"])
    told = st.say(done, "report", "sent")
    assert told.ok and not st.say(told.state, "report", "sent").ok           # reported: nothing is said again


def test_disarmed_a_programme_that_accepts_any_event_turns_red():
    """Disarm: an undeclared event falls through to `executing` instead of being refused."""
    src = ROOT / "nucleo" / "play" / "state.py"
    orig = src.read_text(encoding="utf-8")
    guard = "    if target is None:\n        return _refuse(state, event, f\"{event!r} is not an event of step {step!r}\")\n"
    assert guard in orig, "the disarm no longer matches nucleo/play/state.py"
    try:
        src.write_text(orig.replace(guard, "    if target is None:\n        target = \"executing\"\n"), encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        assert "        target = \"executing\"\n" in src.read_text(encoding="utf-8")
        importlib.reload(st)
        with pytest.raises(AssertionError):
            test_an_event_moves_only_where_the_table_says("confirming", "returned")
        with pytest.raises(AssertionError):
            test_an_action_that_declares_confirm_is_never_executed_before_his_yes()
    finally:
        src.write_text(orig, encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        importlib.reload(st)

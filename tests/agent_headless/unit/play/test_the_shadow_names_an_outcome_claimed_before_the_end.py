"""The shadow records the programme beside the send path and names what the path did out of order (V2-909 P5,
`nucleo/play/shadow.py`).

The order of one measured send — commissioned, «not done» composed, THEN the exit door, the card's return and the
row's ending — yields exactly one `play/drift`: the outcome claimed before the end. The same send in the table's order
yields none. Every declared leaving action runs to `done` in the shadow; the exit door asking where the programme
owed no question is a drift; with the stage off nothing is recorded and no entry point raises. The path's own calls
are there: the real `send_task_run.run` and the real `unserved.outcomes` feed the shadow.

Disarm: `line` no longer names the early claim, and the run no longer reports the card's return → red.
"""
from __future__ import annotations

import asyncio
import importlib
import pathlib
import shutil
from types import SimpleNamespace

import pytest

from nucleo.play import shadow, switch
from widgets import effects, runtime

ROOT = pathlib.Path(__file__).resolve().parents[4]
LEAVING = sorted((m["id"], a) for m in runtime.catalog() for a in (m.get("actions") or {}) if effects.leaves(m["id"], a))


def _art(wid="mensajeria", action="send_to", channel="his", text="his", recipient="his"):
    return {"widget": wid, "action": action, "payload": {"contact": "R", "channel": "whatsapp", "text": "hello"},
            "slots": {"recipient": {"key": "contact", "source": recipient},
                      "channel": {"key": "channel", "source": channel},
                      "text": {"key": "text", "source": text}}}


@pytest.fixture
def events(monkeypatch):
    seen: list = []
    monkeypatch.setattr(switch, "stage", lambda name: name == "shadow")
    monkeypatch.setattr(shadow, "_emit", lambda label, state, uid, **x: seen.append((label, state["step"], x)))
    monkeypatch.setattr(shadow, "_keep", lambda uid, state: shadow._live.__setitem__(uid, state))
    monkeypatch.setattr(shadow, "_arm", lambda: None)
    shadow._live.clear()
    yield seen
    shadow._live.clear()


def _drifts(seen):
    return [(step, x.get("legacy")) for label, step, x in seen if label == "drift"]


def test_an_outcome_claimed_before_the_send_returned_is_one_drift(events):
    shadow.commissioned("T1", _art())
    shadow.line("mensajeria", "send_to", "unmet")          # «that was not done», composed while the send is out
    shadow.door("T1", "passed", _art())
    shadow.returned("T1", {"ok": True, "queued": True})
    shadow.ended("T1", "done", "met")
    assert _drifts(events) == [("executing", "line.unmet")]
    assert shadow.of("T1")["outcome"] == "done"
    assert [s for label, s, _ in events if label == "step"] == ["resolving", "executing", "executed", "verifying", "done"]


def test_the_same_send_in_order_drifts_nothing(events):
    shadow.commissioned("T1", _art())
    shadow.door("T1", "passed", _art())
    shadow.returned("T1", {"ok": True})
    shadow.ended("T1", "done", "met")
    shadow.line("mensajeria", "send_to", "met")
    assert _drifts(events) == [] and shadow.of("T1")["outcome"] == "done"


@pytest.mark.parametrize("wid,action", LEAVING, ids=[f"{w}:{a}" for w, a in LEAVING])
def test_every_declared_leaving_action_runs_to_done_in_the_shadow(events, wid, action):
    shadow.commissioned("T1", _art(wid, action))
    shadow.door("T1", "passed", _art(wid, action))
    shadow.returned("T1", {"ok": True})
    unread = shadow.of("T1")["programme"]["verify"] == "unreadable"      # nobody can see it land: never «met»
    shadow.ended("T1", "done", "unverifiable" if unread else "met")
    assert _drifts(events) == []
    assert shadow.of("T1")["outcome"] == ("unverified" if unread else "done")


def test_a_slot_the_agent_chose_waits_for_his_yes_and_the_door_asking_there_is_no_drift(events):
    shadow.commissioned("T1", _art(channel="agent"))
    assert shadow.of("T1")["step"] == "confirming"
    shadow.door("T1", "asked", _art(channel="agent"))
    shadow.door("T1", "passed", _art(channel="agent"))
    assert _drifts(events) == [] and shadow.of("T1")["step"] == "executing"


def test_the_door_asking_where_the_programme_owed_no_question_is_a_drift(events):
    shadow.commissioned("T1", _art())
    shadow.door("T1", "asked", _art())
    assert _drifts(events) == [("executing", "door.asked")]


def test_a_missing_slot_is_asked_and_his_answer_goes_on_with_the_same_programme(events):
    shadow.commissioned("T1", _art(text="none"), "text")
    assert shadow.of("T1")["step"] == "asking"
    shadow.door("T1", "passed", _art())
    assert _drifts(events) == [] and shadow.of("T1")["step"] == "executing"


@pytest.mark.parametrize("res,state,verdict,outcome", [
    ({"ok": False, "error": "channel_down"}, "failed", "cannot", "failed"),
    ({"ok": True}, "failed", "unmet", "failed"),
    ({"ok": True}, "done", "unverifiable", "unverified"),
])
def test_the_ending_is_what_the_path_found(events, res, state, verdict, outcome):
    shadow.commissioned("T1", _art())
    shadow.door("T1", "passed", _art())
    shadow.returned("T1", res)
    shadow.ended("T1", state, verdict)
    assert _drifts(events) == [] and shadow.of("T1")["outcome"] == outcome


def test_with_the_stage_off_nothing_is_recorded_and_nothing_raises(monkeypatch):
    seen: list = []
    monkeypatch.setattr(switch, "stage", lambda name: False)
    monkeypatch.setattr(shadow, "_emit", lambda *a, **k: seen.append(a))
    shadow._live.clear()
    shadow.commissioned("T1", _art())
    shadow.door("T1", "passed")
    shadow.returned("T1", None)
    shadow.ended("T1", "done")
    shadow.line("mensajeria", "send_to", "unmet")
    assert seen == [] and shadow.of("T1") is None


def test_a_broken_report_never_fails_the_path(events):
    shadow.commissioned("T1", None)                        # not an artefact
    shadow.returned("nobody", object())
    shadow.door("nobody", "passed")
    shadow.ended("", "")
    shadow.line(None, None, None)


def _run_the_real_task(monkeypatch, res):
    from nucleo.circuit import ledger
    from nucleo.flash import data_ops
    from nucleo.request import send_task_run
    from nucleo.workers import exit_gate

    async def cross(rec, name, call):
        return SimpleNamespace(refused="", question="", slots={}, payload=call)

    async def dispatch(wid, action, inner, **kw):
        return res
    monkeypatch.setattr(send_task_run, "artefact", lambda uid: _art())
    monkeypatch.setattr(send_task_run, "_rec", lambda uid, art: SimpleNamespace(task_id=uid))
    monkeypatch.setattr(send_task_run, "_words_of", lambda uid: "")
    monkeypatch.setattr(exit_gate, "cross", cross)
    monkeypatch.setattr(ledger, "resumed", lambda uid: None)
    monkeypatch.setattr(data_ops, "dispatch_and_report", dispatch)
    return asyncio.run(send_task_run.run("T1"))


def test_the_real_send_task_reports_its_door_and_its_return(events, monkeypatch):
    shadow.commissioned("T1", _art(channel="agent"))
    assert _run_the_real_task(monkeypatch, {"ok": True, "queued": True}) == {"ok": True, "queued": True}
    assert shadow.of("T1")["step"] == "verifying" and _drifts(events) == []


def test_the_real_unserved_line_reports_its_claim(events, monkeypatch):
    from nucleo.turn import unserved
    shadow.commissioned("T1", _art())
    monkeypatch.setattr(unserved, "calls_not_run", lambda calls, tasks: [("mensajeria", "send_to")])
    out = unserved.outcomes([], [{"name": "widget_data"}], said="I write to her now", quiet=False)
    assert len(out) == 1 and _drifts(events) == [("executing", "line.unmet")]


def test_disarmed_a_shadow_that_does_not_name_the_early_claim_turns_red(events, monkeypatch):
    """Disarm: `line` drops its drift; and `send_task_run.run` drops the report of the card's return."""
    from nucleo.request import send_task_run
    src, run = ROOT / "nucleo" / "play" / "shadow.py", ROOT / "nucleo" / "request" / "send_task_run.py"
    orig, orig_run = src.read_text(encoding="utf-8"), run.read_text(encoding="utf-8")
    guard, call = '            if not _st.say(state, "report", str(verdict)).ok:\n', "    _play.returned(uid, res)\n"
    assert guard in orig and call in orig_run, "the disarm no longer matches the product"
    try:
        src.write_text(orig.replace(guard, "            if False:\n"), encoding="utf-8")
        run.write_text(orig_run.replace(call, ""), encoding="utf-8")
        for p in (src, run):
            shutil.rmtree(p.parent / "__pycache__", ignore_errors=True)
        assert "            if False:\n" in src.read_text(encoding="utf-8") and call not in run.read_text(encoding="utf-8")
        importlib.reload(shadow)
        importlib.reload(send_task_run)
        monkeypatch.setattr(shadow, "_emit", lambda label, state, uid, **x: events.append((label, state["step"], x)))
        monkeypatch.setattr(shadow, "_keep", lambda uid, state: shadow._live.__setitem__(uid, state))
        monkeypatch.setattr(shadow, "_arm", lambda: None)
        with pytest.raises(AssertionError):
            test_an_outcome_claimed_before_the_send_returned_is_one_drift(events)
        shadow._live.clear()
        events.clear()
        with pytest.raises(AssertionError):
            test_the_real_send_task_reports_its_door_and_its_return(events, monkeypatch)
    finally:
        src.write_text(orig, encoding="utf-8")
        run.write_text(orig_run, encoding="utf-8")
        for p in (src, run):
            shutil.rmtree(p.parent / "__pycache__", ignore_errors=True)
        importlib.reload(shadow)
        importlib.reload(send_task_run)

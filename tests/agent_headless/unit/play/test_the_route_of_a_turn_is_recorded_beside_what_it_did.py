"""The route of a turn is recorded beside what it did (V2-909 P6, `nucleo/play/route_shadow.py`, stage `shadow`).

At the close of a turn one `play/route` event carries where the request should go (`route.destination` over the
model's calls and the turn's readings) and where the path took it (an errand, a declared action run, or words). When
they differ it is a `play/route_drift`; a sure order that names no canvas verb and ended with nothing run, no errand
and no question is unserved — also a drift. Parametrized over every action every shipped widget declares: a call the
doors also ran agrees exactly when its class is not the worker's. With the stage off nothing is recorded, garbage
never raises, and `pipeline_close` calls it.

Disarm: `unserved` is always False, and `pipeline_close` drops the call → red; `opened` and the reply's own question
ignored (`asked=reply.asked()`) → red.
"""
from __future__ import annotations

import importlib
import pathlib
import shutil

import pytest

from nucleo.play import route, route_shadow, switch
from widgets import actions, runtime

ROOT = pathlib.Path(__file__).resolve().parents[4]
ACTS = sorted((m["id"], a) for m in runtime.catalog() for a, s in (m.get("actions") or {}).items()
              if isinstance(s, dict))
IDS = [f"{w}:{a}" for w, a in ACTS]
SEND = {"name": "widget_data", "args": {"widget_id": "mensajeria", "action": "send_to"}}
CLOSE_CALL = ("    _play_route.closed(brief=_brief, calls=getattr(brain, \"_turn_calls\", None), ops=data_done.get(\"ops\"),\n"
              "                       escalate_req=escalate_req, acted_elsewhere=_acted_elsewhere,\n"
              "                       opened=bool((_blk or {}).get(\"opened\")), said=spoken_text, emit=emit)\n")


def _spec(wid, action):
    return (runtime.get(wid).get("actions") or {})[action]


@pytest.fixture
def turn(monkeypatch):
    """Readings all off by default; `turn.set(...)` turns one on. Events land in `turn.seen`."""
    from nucleo.acts import direct_action
    from nucleo.turn import acts_asked, reply, route_by_verdict
    from voice import observer

    class T:
        seen: list = []

        def set(self, *, several=False, sure_escalate=False, sure_order=False, asked=False):
            monkeypatch.setattr(acts_asked, "several", lambda brief: several)
            monkeypatch.setattr(route_by_verdict, "sure_escalate", lambda brief, floor=None: sure_escalate)
            monkeypatch.setattr(route_shadow, "_sure_order", lambda brief: sure_order)
            monkeypatch.setattr(reply, "asked", lambda: asked)

    t = T()
    t.seen = []
    monkeypatch.setattr(switch, "stage", lambda name: name == "shadow")
    monkeypatch.setattr(direct_action, "from_brief", lambda brief: ("", ""))
    monkeypatch.setattr(observer, "emit", lambda kind, label, *a, **k: t.seen.append((kind, label, k.get("extra"))))
    t.set()
    return t


def _close(calls=(), ops=(), escalate_req=None, acted_elsewhere=False, **kw):
    return route_shadow.closed(brief={"x": 1}, calls=list(calls), ops=list(ops), escalate_req=escalate_req,
                               acted_elsewhere=acted_elsewhere, **kw)


def test_a_card_call_the_path_commissioned_as_a_send_task_agrees_on_the_programme(turn):
    send = {"widget": "mensajeria", "action": "send_to", "payload": {}, "text": "x"}
    rec = _close(calls=[SEND], escalate_req={"v": "x", "leaves": True, "send": send})     # `send_errand.hand_over`
    assert (rec["dest"], rec["legacy"], rec["agree"], rec["unserved"]) == ("errand", "errand", True, False)
    assert rec["named"] == ["mensajeria:send_to"]
    assert [(k, label) for k, label, _ in turn.seen] == [("play", "route")]


def test_an_escalation_the_path_escalated_agrees_on_the_worker(turn):
    rec = _close(calls=[{"name": "escalate_to_slowbrain", "args": {}}], escalate_req={"v": "x"})
    assert (rec["dest"], rec["legacy"], rec["agree"]) == ("errand", "errand", True)
    assert [label for _, label, _ in turn.seen] == ["route"]


def test_nothing_named_and_nothing_run_agrees_on_the_conversation(turn):
    rec = _close()
    assert (rec["dest"], rec["legacy"], rec["agree"], rec["unserved"]) == ("talk", "talk", True, False)
    assert [label for _, label, _ in turn.seen] == ["route"]


def test_one_declared_call_that_stays_home_sent_to_a_worker_is_a_drift(turn):
    home = {"name": "widget_data", "args": {"widget_id": "agenda", "action": "show_day"}}
    rec = _close(calls=[home], escalate_req={"v": "x"})
    assert (rec["dest"], rec["legacy"], rec["agree"]) == ("play", "errand", False)
    assert [label for _, label, _ in turn.seen] == ["route_drift"]
    assert turn.seen[0][2]["dest"] == "play" and turn.seen[0][2]["legacy"] == "errand"


def test_a_declared_action_run_while_several_acts_were_asked_is_a_drift(turn):
    turn.set(several=True)
    rec = _close(ops=[("mensajeria", "send_to")])
    assert (rec["dest"], rec["legacy"], rec["agree"]) == ("errand", "play", False)
    assert rec["ran"] == ["mensajeria:send_to"]
    assert [label for _, label, _ in turn.seen] == ["route_drift"]


def test_a_sure_order_that_ended_with_nothing_run_and_no_question_is_unserved(turn):
    turn.set(sure_order=True)
    rec = _close(calls=[{"name": "show_panel", "args": {}}])
    assert (rec["dest"], rec["legacy"], rec["agree"], rec["unserved"]) == ("talk", "talk", True, True)
    assert [label for _, label, _ in turn.seen] == ["route_drift"]


def test_the_same_order_answered_with_a_question_or_acted_elsewhere_is_served(turn):
    turn.set(sure_order=True, asked=True)
    assert _close(calls=[{"name": "show_panel", "args": {}}])["unserved"] is False
    turn.set(sure_order=True)
    assert _close(calls=[{"name": "show_panel", "args": {}}], acted_elsewhere=True)["unserved"] is False
    assert [label for _, label, _ in turn.seen] == ["route", "route"]


def test_a_sure_order_whose_close_opened_its_row_is_served(turn):
    turn.set(sure_order=True)
    assert _close(calls=[{"name": "show_panel", "args": {}}], opened=True)["unserved"] is False
    assert _close(calls=[{"name": "show_panel", "args": {}}], opened=False)["unserved"] is True
    assert [label for _, label, _ in turn.seen] == ["route", "route_drift"]


@pytest.mark.parametrize("said", ["¿A qué número se lo mando?", "Which Quinn do you mean?»", "Which one? "])
def test_a_sure_order_whose_reply_ends_asking_is_served(turn, said):
    turn.set(sure_order=True)
    assert _close(calls=[{"name": "show_panel", "args": {}}], said=said)["unserved"] is False


@pytest.mark.parametrize("said", ["Done.", "Hecho, ¿vale? Ya está.", ""])
def test_a_sure_order_whose_reply_does_not_end_asking_stays_unserved(turn, said):
    turn.set(sure_order=True)
    assert _close(calls=[{"name": "show_panel", "args": {}}], said=said)["unserved"] is True


@pytest.mark.parametrize("wid,action", ACTS, ids=IDS)
def test_every_declared_action_called_and_run_agrees_unless_its_class_is_the_worker(turn, wid, action):
    rec = _close(calls=[{"name": "widget_data", "args": {"widget_id": wid, "action": action}}], ops=[(wid, action)])
    assert rec["dest"] == route.destination([(wid, action)])
    assert rec["legacy"] == "play"
    from widgets import effects   # a worker's by its class, or because the act leaves the machine (V2-931)
    assert rec["agree"] is (actions.classify(_spec(wid, action), action) != actions.ESCALATE
                            and not effects.leaves(wid, action))


def test_with_the_stage_off_nothing_is_recorded(turn, monkeypatch):
    monkeypatch.setattr(switch, "stage", lambda name: False)
    assert _close(calls=[SEND], escalate_req={"v": "x"}) is None
    assert turn.seen == []


def test_garbage_never_raises(turn):
    route_shadow.closed(brief=object(), calls=None, ops="x", escalate_req=None, acted_elsewhere=False)
    route_shadow.closed(brief=None, calls=[None, 3, {"name": "widget_data", "args": "x"}], ops=[(None, None)],
                        escalate_req={}, acted_elsewhere=None)


def test_the_close_of_the_turn_records_its_route():
    src = (ROOT / "nucleo" / "turn" / "pipeline_close.py").read_text(encoding="utf-8")
    assert "from nucleo.play import route_shadow as _play_route" in src
    assert "_play_route.closed(" in src


def test_the_route_is_read_after_the_close_opened_its_rows_and_carries_what_it_said():
    """After `launch_the_errands` (a send it hands over is an escalation, so the record reads `errand`), with `opened`
    and `said` — and `launch_the_errands` reports the row it opened."""
    src = (ROOT / "nucleo" / "turn" / "pipeline_close.py").read_text(encoding="utf-8")
    assert CLOSE_CALL in src
    assert src.index("_errands.launch_the_errands(") < src.index("_play_route.closed(")
    errands = (ROOT / "nucleo" / "turn" / "pipeline_errands.py").read_text(encoding="utf-8")
    assert 'return {"opened": bool(_opened)}' in errands


def test_disarmed_a_record_that_never_names_an_unserved_order_and_a_close_that_drops_it_turn_red(turn):
    """Disarm: `unserved = False` in `read`; and `pipeline_close` drops the `_play_route.closed(` call."""
    src, close = ROOT / "nucleo" / "play" / "route_shadow.py", ROOT / "nucleo" / "turn" / "pipeline_close.py"
    orig, orig_close = src.read_text(encoding="utf-8"), close.read_text(encoding="utf-8")
    line = "    unserved = (legacy == _route.TALK and not acted_elsewhere and not asked and _sure_order(brief))\n"
    assert line in orig and CLOSE_CALL in orig_close, "the disarm no longer matches the product"
    try:
        src.write_text(orig.replace(line, "    unserved = False\n"), encoding="utf-8")
        close.write_text(orig_close.replace(CLOSE_CALL, ""), encoding="utf-8")
        for p in (src, close):
            shutil.rmtree(p.parent / "__pycache__", ignore_errors=True)
        assert "    unserved = False\n" in src.read_text(encoding="utf-8")
        assert "_play_route.closed(" not in close.read_text(encoding="utf-8")
        importlib.reload(route_shadow)
        turn.set(sure_order=True)        # the fixture patched the old module object; patch the reloaded one
        with pytest.raises(AssertionError):
            test_a_sure_order_that_ended_with_nothing_run_and_no_question_is_unserved(turn)
        with pytest.raises(AssertionError):
            test_the_close_of_the_turn_records_its_route()
    finally:
        src.write_text(orig, encoding="utf-8")
        close.write_text(orig_close, encoding="utf-8")
        for p in (src, close):
            shutil.rmtree(p.parent / "__pycache__", ignore_errors=True)
        importlib.reload(route_shadow)


def test_disarmed_a_record_that_ignores_the_row_opened_and_the_reply_that_asked_turns_red(turn):
    """Disarm: `asked` reads only the doors' question (`reply.asked()`), not `opened` nor the reply's own question."""
    src = ROOT / "nucleo" / "play" / "route_shadow.py"
    orig = src.read_text(encoding="utf-8")
    line = "asked=bool(opened) or reply.asked() or ends_asking(said))"
    assert line in orig, "the disarm no longer matches the product"
    try:
        src.write_text(orig.replace(line, "asked=reply.asked())"), encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        assert line not in src.read_text(encoding="utf-8")
        importlib.reload(route_shadow)
        turn.set(sure_order=True)        # the fixture patched the old module object; patch the reloaded one
        with pytest.raises(AssertionError):
            test_a_sure_order_whose_close_opened_its_row_is_served(turn)
        with pytest.raises(AssertionError):
            test_a_sure_order_whose_reply_ends_asking_is_served(turn, "Which Quinn do you mean?")
    finally:
        src.write_text(orig, encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        importlib.reload(route_shadow)

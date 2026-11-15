"""Every request has ONE destination — the conversation, the programme or a worker — and for every declared action it
is the one today's router gives (V2-909, `nucleo/play/route.py`, `nucleo/play/programme.py`).

Parametrized over every action every shipped widget declares: each has a programme read from its manifest; a leaving
one has an end state or says why it has none; one declared action goes to the programme unless its class declares the
worker; under a sure errand reading the action stays home exactly when `route_by_verdict.stays_home` says so.

Disarm: `destination` answers the programme for everything → red.
"""
from __future__ import annotations

import importlib
import pathlib
import shutil

import pytest

from nucleo.play import programme, route
from nucleo.turn import route_by_verdict
from widgets import actions, effects, runtime

ROOT = pathlib.Path(__file__).resolve().parents[4]
ACTS = sorted((m["id"], a) for m in runtime.catalog() for a, s in (m.get("actions") or {}).items()
              if isinstance(s, dict))
IDS = [f"{w}:{a}" for w, a in ACTS]


def _spec(wid, action):
    return (runtime.get(wid).get("actions") or {})[action]


def test_the_catalogue_is_read():
    assert len(ACTS) > 100 and any(effects.leaves(w, a) for w, a in ACTS)


@pytest.mark.parametrize("wid,action", ACTS, ids=IDS)
def test_every_declared_action_has_a_programme(wid, action):
    prog = programme.of(wid, action)
    assert prog is not None and set(prog) == {"confirm", "leaves", "verify"}
    assert prog["leaves"] is effects.leaves(wid, action)
    assert prog["confirm"] is (actions.classify(_spec(wid, action), action) == actions.CONFIRM)
    if prog["leaves"]:                                     # what leaves is never «done» on its return alone
        assert prog["verify"] in (programme.CHECK, programme.UNREADABLE)


@pytest.mark.parametrize("wid,action", ACTS, ids=IDS)
def test_one_declared_action_goes_where_the_router_sends_it_today(wid, action):
    worker = actions.classify(_spec(wid, action), action) == actions.ESCALATE
    assert route.destination([(wid, action)]) == (route.ERRAND if worker else route.PLAY)
    # under a sure errand reading: home acts stay with their widget, a leaving one follows the reading
    home = route_by_verdict.stays_home("widget_data", {"widget_id": wid, "action": action})
    assert home is not effects.leaves(wid, action)
    expected = route.PLAY if home and not worker else route.ERRAND
    assert route.destination([(wid, action)], errand=True) == expected


def test_the_ladder_in_order():
    send, add = ("mensajeria", "send_to"), ("agenda", ACTS_OF["agenda"])
    assert route.destination() == route.TALK                                  # nothing asked of a widget
    assert route.destination([("mensajeria", "no_such_action")]) == route.TALK
    assert route.destination([("no_such_widget", "open")]) == route.TALK
    assert route.destination(errand=True) == route.ERRAND                     # work outside our widgets
    assert route.destination([send]) == route.PLAY                            # one declared action
    assert route.destination([send, send]) == route.PLAY                      # the same action named twice is one
    assert route.destination([("mensajeria::2", "send_to")]) == route.PLAY    # an instance is its widget
    assert route.destination([send], several=True) == route.ERRAND            # several steps: a worker
    assert route.destination([send, add]) == route.ERRAND
    assert route.destination([send, ("mensajeria", "no_such_action")]) == route.PLAY   # the undeclared one is nothing


ACTS_OF = {w: a for w, a in ACTS if not effects.leaves(w, a)
           and actions.classify(_spec(w, a), a) != actions.ESCALATE}


@pytest.mark.parametrize("landed,how,event", [
    (True, "check", "landed"), (False, "check", "absent"), (None, "check", "unreadable"),
    (True, "unreadable", "unreadable"), (False, "unreadable", "unreadable"), (None, "unreadable", "unreadable"),
    (True, "return", "landed"), (None, "return", "landed")])
def test_the_look_at_the_end_state_never_claims_more_than_it_has(landed, how, event):
    assert programme.verdict_event({"verify": how}, landed) == event


def test_an_undeclared_action_has_no_programme():
    assert programme.of("mensajeria", "no_such_action") is None and programme.of("no_such_widget", "open") is None


def test_disarmed_a_router_that_always_answers_the_programme_turns_red():
    """Disarm: `destination` returns PLAY at its head."""
    src = ROOT / "nucleo" / "play" / "route.py"
    orig = src.read_text(encoding="utf-8")
    head = "def destination(acts=(), *, several: bool = False, errand: bool = False) -> str:\n"
    assert head in orig, "the disarm no longer matches nucleo/play/route.py"
    try:
        src.write_text(orig.replace(head, head + "    return PLAY\n"), encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        assert "    return PLAY\n" in src.read_text(encoding="utf-8")
        importlib.reload(route)
        with pytest.raises(AssertionError):
            test_the_ladder_in_order()
        with pytest.raises(AssertionError):
            test_one_declared_action_goes_where_the_router_sends_it_today("navegador", "automate")
    finally:
        src.write_text(orig, encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        importlib.reload(route)

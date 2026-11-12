"""A turn whose words claim a leaving act no door reached hands that act to its task (V2-851, measured 2026-11-05).

On the operator's engine «manda un mensaje a pablo diciendo hola» was read surely (`screen_action =
mensajeria:send_to` 0.98) and answered «Sending "hola" to Pablo now…» with ZERO calls: the line claimed a send that
would never happen. The class: an identified leaving act the turn did not make is an identified task — a Brain Worker
on its own row with the `message` playbook — so the start the line announced is real. A question, an unsure verdict
or an act that does not leave the machine is never routed.

Disarm: make `claimed` return 0 before it escalates and the first test goes red.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.request import ask_outside_door as aod


@pytest.fixture
def wired(monkeypatch):
    seen = {"escalated": [], "patched": [], "events": []}
    from nucleo.turn import verdicts
    from widgets import effects
    from nucleo.request import model
    from nucleo.circuit import ledger
    from nucleo.acts import errand

    state = {"target": ("mensajeria:send_to", {"used": True, "confidence": 0.98}), "leaves": True,
             "kind": ("order", {"used": True, "confidence": 0.7}), "backs": True}   # an order under the veto

    def _read(h, k, fb, min_confidence=None):
        got = {"screen_action": state["target"], "request_type": state["kind"],
               "errand_class": ("sends_for_him", {"used": True, "confidence": 0.9}) if state["backs"] else None}.get(k)
        return got if got and got[1]["confidence"] >= (min_confidence or 0) else (fb, None)
    monkeypatch.setattr(verdicts, "read", _read)
    monkeypatch.setattr(effects, "leaves", lambda card, act: state["leaves"])
    monkeypatch.setattr(model, "opened", lambda wid, act, text="": "row-1")

    class _Store:
        def task_patch(self, uid, **kw):
            seen["patched"].append((uid, kw))
    monkeypatch.setattr(ledger, "store", lambda: _Store())
    monkeypatch.setattr(errand, "escalate_to_slowbrain",
                        lambda text, context=None: seen["escalated"].append((text, context)) or 7)
    emit = lambda *a, **k: seen["events"].append((a, k))   # noqa: E731
    return seen, state, emit


def test_a_claimed_send_with_no_call_becomes_a_message_task(wired):
    seen, _state, emit = wired
    tid = asyncio.run(aod.claimed({}, 'Sending "hola" to Pablo now.', "manda un mensaje a pablo diciendo hola", emit=emit))
    assert tid == 7
    (text, ctx), = seen["escalated"]
    assert text == "manda un mensaje a pablo diciendo hola"
    assert ctx["task_uid"] == "row-1" and ctx["playbook"] == "message"
    assert ("row-1", {"playbook": "message"}) in seen["patched"]


def test_a_question_is_never_a_claim(wired):
    seen, _state, emit = wired
    assert asyncio.run(aod.claimed({}, "¿A qué Pablo se lo mando?", "manda un mensaje a pablo", emit=emit)) == 0
    assert not seen["escalated"]


def test_an_unsure_verdict_or_an_act_that_stays_routes_nothing(wired):
    seen, state, emit = wired
    state["target"] = ("mensajeria:send_to", {"used": True, "confidence": 0.55})   # A7: under the act floor (0.6)
    assert asyncio.run(aod.claimed({}, "Sending it now.", "manda un mensaje a pablo", emit=emit)) == 0
    state["target"] = ("mensajeria:send_to", {"used": True, "confidence": 0.98})
    state["leaves"] = False
    assert asyncio.run(aod.claimed({}, "Done.", "abre mensajería", emit=emit)) == 0
    assert not seen["escalated"]


@pytest.fixture
def order(wired, monkeypatch):
    seen, state, emit = wired
    from nucleo.turn import verdicts
    v = {"screen_action": ("mensajeria:send_to", {"used": False, "confidence": 0.43}),
         "request_type": ("order", {"used": True, "confidence": 0.94}),
         "wants_words": ("tell", {"used": False, "confidence": 0.08}),
         # V2-886 D4: the reading asks for a send — «ask Raquel» is a message in his name
         "errand_class": ("sends_for_him", {"used": True, "confidence": 0.8})}

    def read(h, k, fb, min_confidence=None):
        floor = verdicts.LICENCE if min_confidence is None else min_confidence
        t = v.get(k)
        return (t[0], t[1]) if t and t[1]["confidence"] >= floor else (fb, None)
    monkeypatch.setattr(verdicts, "read", read)
    v["_state"] = state
    return seen, v, emit


@pytest.mark.parametrize("said", ["Pregúntale a Raquel cuándo vuelve.", "Ask Tom when he is back."])
def test_a_sure_order_no_door_served_becomes_its_task(order, said):
    """V2-852 — «I'll try again — let me get a message to Raquel now» with zero calls and no task."""
    seen, _v, emit = order
    assert asyncio.run(aod.claimed({}, "I'll try again — let me get a message to her now.", said, emit=emit)) == 7
    (text, ctx), = seen["escalated"]
    assert text == said and ctx["playbook"] == "message" and ctx["kind"] == "generic"


def test_an_order_answered_by_words_or_a_question_is_not_routed(order):
    seen, v, emit = order
    v["wants_words"] = ("tell", {"used": True, "confidence": 0.9})
    assert asyncio.run(aod.claimed({}, "It is 5 pm.", "dime la hora", emit=emit)) == 0
    v["wants_words"] = ("act", {"used": False, "confidence": 0.1})
    assert asyncio.run(aod.claimed({}, "¿A cuál de las dos?", "pregúntale a Raquel", emit=emit)) == 0
    v["request_type"] = ("question", {"used": True, "confidence": 0.95})
    assert asyncio.run(aod.claimed({}, "Sure.", "¿qué tiempo hace?", emit=emit)) == 0
    v["request_type"] = ("order", {"used": True, "confidence": 0.94})
    v["screen_action"] = ("agenda:close", {"used": False, "confidence": 0.4})
    v["_state"]["leaves"] = False          # an order about the screen stays the turn's
    assert asyncio.run(aod.claimed({}, "Done.", "close the weekend", emit=emit)) == 0
    assert not seen["escalated"]


@pytest.mark.parametrize("said", ["Cierra absolutamente todo.", "Close absolutely everything."])
def test_a_lean_to_a_send_without_a_reading_that_sends_starts_no_worker(order, said):
    """V2-886 D4 (2026-11-11): a sure order whose lean names a leaving act, while nothing in the reading asks for a
    send (no `sends_for_him`, no channel named), is not a send: no message worker is born."""
    seen, v, emit = order
    v.pop("errand_class")
    v["errand_class"] = ("none", {"used": True, "confidence": 0.9})
    v["message_channel"] = ("none", {"used": True, "confidence": 0.9})
    assert asyncio.run(aod.claimed({}, "Done.", said, emit=emit)) == 0
    assert not seen["escalated"]


def test_a_question_about_a_send_launches_no_send(wired):
    """A7 audit P1: «¿Le mandaste el mensaje a Pablo?» → `send_to` 0.62 and the reply «Sí, ayer» with no call. A
    launched send needs the ORDER at the floor and a reading that backs a send, not one lean at 0.6."""
    seen, state, emit = wired
    state["target"] = ("mensajeria:send_to", {"used": True, "confidence": 0.62})
    state["kind"] = ("question", {"used": True, "confidence": 0.9})
    assert asyncio.run(aod.claimed({}, "Sí, ayer.", "¿le mandaste el mensaje a pablo?", emit=emit)) == 0
    state["kind"] = ("order", {"used": True, "confidence": 0.7})
    state["backs"] = False
    assert asyncio.run(aod.claimed({}, "Sending it now.", "manda un mensaje a pablo", emit=emit)) == 0, "an unbacked lean sent"
    assert not seen["escalated"]


def test_a_claimed_send_is_read_at_the_act_floor_not_the_veto(wired):
    """A7: the same send asked 0.85 with no call and 0.6 with a view — one floor for an act the turn launches."""
    seen, state, emit = wired
    state["target"] = ("mensajeria:send_to", {"used": True, "confidence": 0.7})
    assert asyncio.run(aod.claimed({}, "Sending it now.", "manda un mensaje a pablo", emit=emit)) == 7

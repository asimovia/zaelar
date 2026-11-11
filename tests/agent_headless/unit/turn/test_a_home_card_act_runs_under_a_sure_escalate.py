"""A declared act of one of OUR cards that does not leave the machine runs under a sure «escalate» (V2-887).

Measured on the kindergarten bench (2026-11-11, 3 of 3): «Tengo conectado Google, impórtame todos los contactos» with
Contacts open and Google linked — the model called `contactos:sync_contacts`, the brief said `escalate`, `gate_calls`
held the call and a Brain Worker was sent to do what one call does. The class is the player's (V2-860 T1.1): the
routing gate protects SENDS; a card act that stays home is its card's to run. A leaving act is still routed. Disarm:
`stays_home` answering False → the import is held and routed again (red).
"""
from __future__ import annotations

import threading
import time

import pytest

from nucleo.turn import brief as tb
from nucleo.turn import route_by_verdict as R

ORDER = {"es": "Tengo conectado Google, impórtame todos los contactos", "en": "Google is connected, import all my contacts"}


def _gate(lang):
    ev = threading.Event()
    ev.set()
    brief = {"event": ev, "turn_id": "t",
             "result": {"_call_id": "t", tb.ESCALATE_KEY: {"choice": "escalate", "confidence": 0.9, "probs": {}}}}
    ran, req = [], {"v": None, "more": [], "surface": {}}
    call = R.gate_calls(lambda n, a: ran.append((n, a.get("action"))) or "ran", brief=brief, escalate_req=req,
                        operator_text=ORDER[lang], emit=lambda *a, **k: None, t0=time.monotonic(), wait=0.0)
    return call, ran, req


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_card_act_that_stays_home_runs_and_opens_no_errand(lang):
    call, ran, req = _gate(lang)
    assert call("widget_data", {"widget_id": "contactos", "action": "sync_contacts", "payload": {}}) == "ran"
    assert ran == [("widget_data", "sync_contacts")] and not req.get("routed") and req["v"] is None


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_leaving_act_is_still_routed_under_the_same_verdict(lang):
    call, ran, req = _gate(lang)
    assert call("widget_data", {"widget_id": "mensajeria", "action": "send_to",
                                "payload": {"contact": "Raquel", "text": "x"}}) is None
    assert ran == [] and req["routed"]


def test_disarmed_the_import_is_routed_again(monkeypatch):
    monkeypatch.setattr(R, "stays_home", lambda *a, **k: False)
    call, ran, req = _gate("es")
    assert call("widget_data", {"widget_id": "contactos", "action": "sync_contacts", "payload": {}}) is None
    assert ran == [] and req["routed"], "the disarm did not take"

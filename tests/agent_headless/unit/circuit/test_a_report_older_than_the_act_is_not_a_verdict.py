"""A surface report made BEFORE an act is no verdict on it (`reported.unheard`, 2026-11-18).

«Open the chat of …»: the chat already sat in the store, so no order key changed revision and nothing opened the
`pending` window. One second after the order the end state `report.thread_open has {name}` was read against the card's
last report — made before the act — read contrary, and the mouth said «It isn't on the widget yet». The app confirmed
at +12 s. Now, inside `INLINE_GRACE_S`, a contrary reading from surfaces silent since the act's birth is «asked»; a
report made after the birth is judged as before; past the grace the circuit's own ending applies. Invented people.
"""
from __future__ import annotations

import time

import pytest

from nucleo import circuit
from nucleo.circuit import reported, spec
from nucleo.turn import reply_receipts
from voice import screens
from widgets import state, store

A = "desktop:aaa"
NAME = "Odile Varga"
OPEN = f"{NAME} (whatsapp)"


@pytest.fixture
def world(monkeypatch, tmp_path):
    from server import canvas_api
    from widgets.mensajeria import data
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    state._reset_for_tests()
    screens._reset_for_tests()
    spec.reset()
    db = data.load_db()
    db["platforms"] = {"whatsapp": {"status": "connected"}}
    db["active_chat"] = {"platform": "whatsapp", "chatId": "odile"}   # the order already holds it: no key will move
    store.save("mensajeria", db)
    screens.attach(A)
    monkeypatch.setattr(canvas_api, "_BY_DEV", {A: {"open": ["mensajeria"]}})
    emitted = []
    real = spec._emit
    monkeypatch.setattr(spec, "_emit", lambda label, e, **k: emitted.append(label) or real(label, e, **k))
    yield emitted
    spec.reset()
    state._reset_for_tests()
    screens._reset_for_tests()


def _say(n, thread_open):
    code, got = state.report("mensajeria", {"dev": A, "mount": "m1", "n": n, "full": True,
                                            "patch": {"thread_open": thread_open}, "ack": state.stamp("mensajeria")})
    assert code == 200, got


def _act():
    e = spec.open_for_action("mensajeria", "open", {"name": NAME})
    e["born"] = time.time() + 0.001                         # strictly after every report made so far
    return e


def _ack(e):
    return reply_receipts.bare_ack("Done.", {"mensajeria"}, turn=e["trace"])


@pytest.mark.parametrize("before", ["", "Rowan Ilic (telegram)"])
def test_a_report_from_before_the_act_is_asked_not_a_failure(world, before):
    _say(1, before)
    e = _act()
    assert spec.attest(e) is None and e["awaiting"] == reported.PENDING
    assert "❌ spec: sin cumplir todavía" not in world
    assert world.count("⏳ spec: ordered — the app has not confirmed it yet") == 1
    spec.attest(e)
    assert world.count("⏳ spec: ordered — the app has not confirmed it yet") == 1, "said once, not at every read"
    lang = reply_receipts._lang()
    assert _ack(e) == str(lang.done_asked) != str(lang.done_not_on_card)


def test_the_surface_then_reports_the_chat_and_it_is_met(world):
    _say(1, "")
    e = _act()
    assert spec.attest(e) is None
    _say(2, OPEN)
    assert spec.attest(e) is True
    assert _ack(e) == "Done."


def test_a_report_made_after_the_act_still_judges_it(world):
    _say(1, "")
    e = _act()
    e["born"] = time.time() - 1.0                           # the surface speaks AFTER the birth, still elsewhere
    _say(2, "Rowan Ilic (telegram)")
    assert spec.attest(e) is False
    assert _ack(e) == str(reply_receipts._lang().done_not_on_card)


def test_past_the_grace_a_silent_surface_is_no_longer_unheard(world):
    _say(1, "")
    e = _act()
    later = e["born"] + circuit.INLINE_GRACE_S
    assert reported.unheard(e) and not reported.unheard(e, later)
    assert spec.attest(e, now=later) is False, "the circuit's own ending (unmet at the grace) applies"


def test_the_mouth_does_not_turn_an_unheard_card_into_done(world):
    from nucleo.circuit import verdict
    from nucleo.turn import reply
    _say(1, "")
    e = _act()
    got = reply_receipts.unconfirmed([reply.Outcome(verdict.MET.name, "mensajeria", "open", object=NAME)], e["trace"])
    assert reply._value(got[0].verdict) == verdict.STARTED.name


# ── disarm ───────────────────────────────────────────────────────────────────────────────────────────────────

def test_disarm_without_unheard_the_old_report_is_a_verdict(world, monkeypatch):
    """Disarm: `reported.unheard` blind → the defect of 2026-11-18 comes back: «not on the card» over an open chat."""
    monkeypatch.setattr(reported, "unheard", lambda e, now=None: False)
    _say(1, "")
    e = _act()
    assert spec.attest(e) is False
    assert _ack(e) == str(reply_receipts._lang().done_not_on_card)

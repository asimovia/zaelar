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


def test_past_the_grace_a_silent_surface_is_no_longer_unheard(world):
    _say(1, "")
    e = _act()
    later = e["born"] + circuit.INLINE_GRACE_S
    assert reported.unheard(e) and not reported.unheard(e, later)
    assert spec.attest(e, now=later) is False, "the circuit's own ending (unmet at the grace) applies"


# ── disarm ───────────────────────────────────────────────────────────────────────────────────────────────────

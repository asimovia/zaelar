"""Whose turn is it — the card on screen or the errand his words name — by CONSEQUENCE, in SHADOW (V2-878 §5, 2.1681).

Today a card always wins (`stop.card_owns_the_turn`). The arbiter reads two facts already there: rows on screen his
reference can land on (→ card), and an errand he names that has no rows and holds a deferred choice (→ errand); both
→ ask which. It is emitted (`thread` · `arbiter`, `would` beside `did`, `changes`) once per turn, and the owner rule's
answer — what the doors obey — is exactly what it was.
"""
from __future__ import annotations

import pytest

from nucleo import dispatch
from nucleo.circuit import ledger
from nucleo.request import stop
from nucleo.turn import brief as tb, pick_pending
from voice import trace

from ._pick_fixture import brief, thread, world  # noqa: F401

SAID = {"es": "de la búsqueda de monitores, abre el segundo que encuentres",
        "en": "from the monitors search, open the second one you find"}
GOAL = {"es": "buscar monitores de segunda mano", "en": "search for second-hand monitors"}


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("owns, rows_on_screen, pick, would, changes", [
    (True, True, False, "card", False),
    (True, True, True, "ask", True),
    (True, False, True, "errand", True),
    (False, False, True, "errand", False),
    (False, False, False, "none", False),
])
def test_the_arbiter_says_whose_turn_beside_the_owner_rule(world, monkeypatch, lang, owns, rows_on_screen, pick,
                                                           would, changes):
    uid = world["errand"]("k5", GOAL[lang], "k5")
    if pick:
        ledger.card_written(uid, pick_pending={"heard": "abre el mejor", "at": 1})
    monkeypatch.setattr(tb, "of_this_turn", lambda: brief("act", SAID[lang]))
    monkeypatch.setattr(stop, "card_owns_the_turn", lambda *a, **k: owns)
    monkeypatch.setattr(pick_pending, "_rows_on_screen", lambda b: rows_on_screen)
    assert dispatch.his_words_may_reach_an_errand() is (not owns), "the shadow changed the owner rule's answer"
    (ev,) = thread(world, "arbiter")
    assert ev["would"] == would and ev["did"] == ("card" if owns else "errand") and ev["changes"] is changes, ev
    dispatch.his_words_may_reach_an_errand()
    assert len(thread(world, "arbiter")) == 1, "arbitrated twice in one turn"
    trace.adopt("T-other")

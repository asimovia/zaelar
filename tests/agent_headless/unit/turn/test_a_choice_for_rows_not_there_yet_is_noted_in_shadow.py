"""A choice about rows that do not exist yet is kept on the errand's card — in SHADOW (V2-878 §5, node 2.1679).

«abre el que sea mejor oferta» while a monitors search had NO rows: the request was relayed to the worker as a note and
forgotten. Now the one door his words cross into a running errand (`soon.relay_his_words` — the portal's inject, a
steer, the model's own `send_to_worker`), for an errand whose sheet has no rows and a turn that does not ask to be TOLD
(`wants_words` is not `tell`), writes `pick_pending` on that errand's card, emits it (`thread` · decided · verb
`pick_pending` · shadow) and hands it to the commission's shadow. Measured first in the sandbox: the model sent the
order with its own `send_to_worker` and a portal-only note never ran. The relay runs exactly as before.
"""
from __future__ import annotations

import pytest

from nucleo import dispatch
from nucleo.circuit import ledger
from nucleo.turn import brief as tb, commission, flow_door, pick_pending

from ._pick_fixture import brief, thread, world  # noqa: F401

SAID = {"es": "abre el que sea mejor oferta", "en": "open whichever is the best deal"}


@pytest.mark.parametrize("lang", ["es", "en"])
def test_an_order_over_rows_still_to_come_is_kept_on_the_card(world, monkeypatch, lang):
    uid = world["errand"]("k1", "buscar monitores de 27 pulgadas", "k1")
    monkeypatch.setattr(tb, "of_this_turn", lambda: brief("act", SAID[lang]))
    assert flow_door.obey(SAID[lang], {"as": "inject", "flow": "k1", "sheet": "k1"}, {}) is False
    assert len(world["relayed"]) == 1, "the relay changed"
    card = ledger.card(uid)
    assert card["pick_pending"]["heard"] == SAID[lang]
    (ev,) = thread(world, "decided")
    assert ev["verb"] == "pick_pending" and ev["shadow"] is True and ev["id"] == "k1"
    out = commission.shadow(lambda *a, **k: None, at="close", brief=brief("act"), escalate_req={}, words_said=True)
    assert out["pick_pending"]["uid"] == uid, "the commission's shadow does not carry it"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_models_own_send_to_the_errand_is_noted_too(world, monkeypatch, lang):
    uid = world["errand"]("k6", "buscar monitores baratos", "k6")
    monkeypatch.setattr(tb, "of_this_turn", lambda: brief("act", SAID[lang]))
    relayed = "Operator wants to open the best deal as soon as possible."   # the model's own paraphrase
    assert dispatch.relay_his_words("k6", relayed) is True and world["injected"] == [("k6", relayed)]
    assert ledger.card(uid)["pick_pending"]["heard"] == SAID[lang], "the card kept the model's words, not his"


def test_a_question_or_rows_already_there_note_nothing(world, monkeypatch):
    uid = world["errand"]("k2", "buscar monitores", "k2")
    monkeypatch.setattr(tb, "of_this_turn", lambda: brief("tell"))
    flow_door.obey("¿cómo va lo de los monitores?", {"as": "inject", "flow": "k2", "sheet": "k2"}, {})
    monkeypatch.setattr(tb, "of_this_turn", lambda: brief("act"))
    monkeypatch.setattr(pick_pending, "_rows", lambda sheet: 3)
    flow_door.obey("abre el segundo", {"as": "steer", "flow": "k2", "sheet": "k2"}, {})
    assert "pick_pending" not in ledger.card(uid) and not thread(world, "decided")
    assert len(world["relayed"]) == 2

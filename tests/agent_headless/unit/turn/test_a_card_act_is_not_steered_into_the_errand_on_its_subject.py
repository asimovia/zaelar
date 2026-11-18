"""An order whose one act is a CARD's is that card's, even while an errand on the same subject runs (V2-879 O1).

Measured in the lab sandbox (es, 2026-11-11): a coffee-shop search running, then «ponme esas cafeterías en el mapa». The
brief read `catalog_widget=map` 0.95, `wants_words=act` 0.98, `acts_asked=one` 1.00 — and `stop_errand=steer` 0.68,
so the route said `steer` into the search and the one relay door sent his words to its worker («Voy a ello», no map).
`screen_action`, the verdict the owner rule read, is not asked with the map closed: the card-naming verdict there is
the catalogue's. These tests hold the reading — three paid verdicts and the manifest, no word list — at the route
(`flow_of.joins_as` → `card`), at the portal (`flow_door.obey` tells no errand) and at the one relay door.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.request import stop
from nucleo.turn import card_act

FLOW = {"id": "1", "request": "Búscame cafeterías de especialidad en Malasaña", "sheet": "S1", "surface": "lista",
        "parked": False}


def _brief(**verdicts) -> dict:
    ev = threading.Event()
    ev.set()
    res = {"_call_id": "t"}
    for key, (choice, conf) in verdicts.items():
        res[key] = {"choice": choice, "confidence": conf, "probs": {}}
    return {"event": ev, "turn_id": "t", "result": res, "judged": "ponme esas cafeterías en el mapa", "open_ids": []}


MEASURED = dict(wants_words=("act", 0.98), catalog_widget=("map", 0.95), acts_asked=("one", 1.0),
                stop_errand=("steer", 0.68), request_type=("order", 0.99))


@pytest.fixture(autouse=True)
def _a_search_runs(monkeypatch):
    monkeypatch.setattr("nucleo.dispatch.pending_summaries", lambda: [{"id": "1", "surface": "lista"}])


def test_the_one_relay_door_keeps_his_words_with_the_card(monkeypatch):
    from nucleo import dispatch
    from nucleo.dispatch import soon
    from nucleo.turn import brief as _tb
    sent = []
    monkeypatch.setattr(_tb, "of_this_turn", lambda: _brief(**MEASURED))
    monkeypatch.setattr(dispatch, "inject_soon", lambda which, words: sent.append(which))
    assert soon.relay_his_words("1", "ponme esas cafeterías en el mapa") is False and sent == [], \
        "the relay door sent a card's order to the running search"


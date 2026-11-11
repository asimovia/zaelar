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
from nucleo.turn import flow_door, flow_of

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


def test_the_route_gives_the_card_act_to_the_card_not_to_the_errand():
    assert flow_of.joins_as(FLOW, _brief(**MEASURED)) == flow_of.CARD, \
        "an order the brief gives to the map app was joined to the coffee-shop search as a steer"


def test_the_portal_tells_the_errand_nothing(monkeypatch):
    relayed = []
    monkeypatch.setattr("nucleo.dispatch.relay_his_words", lambda which, words: relayed.append(which) or True)
    ctx: dict = {}
    opened = flow_door.obey("ponme esas cafeterías en el mapa", {"as": flow_of.CARD, "flow": "1", "sheet": "S1"}, ctx)
    assert opened is False and relayed == [], "a card's act reached the errand or opened one"


def test_the_one_relay_door_keeps_his_words_with_the_card(monkeypatch):
    from nucleo import dispatch
    from nucleo.dispatch import soon
    from nucleo.turn import brief as _tb
    sent = []
    monkeypatch.setattr(_tb, "of_this_turn", lambda: _brief(**MEASURED))
    monkeypatch.setattr(dispatch, "inject_soon", lambda which, words: sent.append(which))
    assert soon.relay_his_words("1", "ponme esas cafeterías en el mapa") is False and sent == [], \
        "the relay door sent a card's order to the running search"


@pytest.mark.parametrize("why, over", [
    ("he asks to be TOLD", dict(wants_words=("tell", 0.95))),
    ("two acts in one sentence", dict(acts_asked=("several", 0.96))),
    ("the catalogue unsure", dict(catalog_widget=("map", 0.6))),
    ("the catalogue names no card", dict(catalog_widget=("none", 0.99))),
    ("a process banner is the errand's work", dict(catalog_widget=("search", 0.97))),
])
def test_without_a_card_act_his_words_still_reach_the_errand(why, over):
    assert flow_of.joins_as(FLOW, _brief(**{**MEASURED, **over})) == stop.STEER, why


def test_a_stop_of_the_errand_is_an_order_about_the_errand():
    b = _brief(**{**MEASURED, "stop_errand": ("stop", 0.97)})
    assert flow_of.joins_as(FLOW, b) == stop.STOP


def test_an_errand_that_builds_a_card_keeps_his_words(monkeypatch):
    monkeypatch.setattr("nucleo.dispatch.pending_summaries", lambda: [{"id": "1", "surface": "widget"}])
    assert not card_act.named(_brief(**MEASURED))
    assert flow_of.joins_as({**FLOW, "surface": "widget"}, _brief(**MEASURED)) == stop.STEER


def test_an_ended_errand_on_the_subject_is_not_reopened_by_a_card_act():
    assert flow_of.joins_as({**FLOW, "ended": True}, _brief(**MEASURED)) == flow_of.CARD


def test_the_settled_route_is_read_with_the_verdict_that_landed_after_it(monkeypatch):
    """The route is begun beside the model call, often before the brief lands (measured, en: decided `inject`, then
    the portal obeyed `card` and the close still said «its live errand (inject)»)."""
    import asyncio

    from nucleo.turn import brief as _tb
    from voice import trace
    monkeypatch.setattr(_tb, "of_this_turn", lambda: _brief(**MEASURED))

    async def scene():
        trace.adopt("T-card")
        early = asyncio.get_running_loop().create_future()
        early.set_result({"as": flow_of.INJECT, "flow": "1", "sheet": "S1", "words": "x", "text": "x", "_flow": FLOW})
        monkeypatch.setitem(flow_of._TURN, "T-card", early)
        return await flow_of.settled()
    try:
        assert asyncio.run(scene())["as"] == flow_of.CARD
    finally:
        trace.adopt("")


def test_an_act_on_the_sheet_the_errand_delivers_into_stays_the_errands():
    """V2-874's «abre el que sea mejor oferta» over a results sheet still empty is a choice for rows the errand will
    deliver (V2-878 §5, `pick_pending`): not a card act this rule claims."""
    b = _brief(**{**MEASURED, "catalog_widget": ("results", 0.97)})
    assert not card_act.named(b)
    assert flow_of.joins_as(FLOW, b) == stop.STEER
    assert flow_of.joins_as({**FLOW, "ended": True}, b) == flow_of.REOPEN

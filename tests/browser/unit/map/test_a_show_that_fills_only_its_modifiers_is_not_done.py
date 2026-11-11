"""A map `show` that carries only its modifiers paints nothing and is NOT done (V2-879 O1, the empty act).

Measured: `map.show {"places": [], …}` opened an empty map. The call sent `title` — a declared slot — so the funnel's
«fills none of its declared slots» read it as filled. `show`/`add` now declare what they FILL (`fills: rows, places`),
and the one funnel (`widgets/empty_act.run`) judges the call by that: an answer of ok over an unchanged card becomes
`slots_unfilled`, naming `rows` and `places`. No second check lives inside the map.
"""
from __future__ import annotations

import asyncio

import pytest

from widgets import contract, empty_act, runtime, server_api


def _spec(action="show"):
    return (runtime.get("map") or {})["actions"][action]


@pytest.mark.parametrize("action", ["show", "add"])
def test_the_map_declares_what_its_show_fills(action):
    assert _spec(action).get("fills") == ["rows", "places"]


@pytest.mark.parametrize("payload", [{"title": "Cafeterías", "places": []}, {"near": "Madrid", "rows": []},
                                     {"title": "coffee shops", "source": "google"}])
def test_a_call_with_only_modifiers_answered_ok_over_an_unchanged_map_is_not_done(monkeypatch, payload):
    """The card's answer is forced to ok here, so the verdict is the funnel's alone."""
    async def view(wid, pl):
        return {"places": [], "updated": 0}
    monkeypatch.setattr(empty_act, "_view", view)

    async def act(wid, action, pl):
        return {"ok": True, "places": []}
    res = asyncio.run(empty_act.run("map", "show", payload, act))
    assert res["ok"] is False and res["error"] == contract.SLOTS_UNFILLED, res
    assert res["unmet"] == ["rows", "places"], res


def test_a_call_that_fills_rows_or_places_is_the_handlers(monkeypatch):
    for pl in ({"rows": "all", "title": "x"}, {"places": ["Retiro"], "near": "Madrid"}):
        assert contract.unfilled("map", "show", empty_act.what_it_fills(_spec()), pl) is None, pl


def test_through_the_funnel_an_empty_show_is_refused_and_the_map_stays(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.map import data as mp
    before = mp.view_data()
    res = asyncio.run(server_api._dispatch("map", "show", {"title": "Cafeterías", "places": []}))
    assert res.get("ok") is False, res
    assert mp.view_data() == before


def test_an_act_with_no_fills_is_judged_by_all_its_slots_as_before():
    timer_set = (runtime.get("timer") or {})["actions"]["set"]
    assert empty_act.what_it_fills(timer_set) is timer_set

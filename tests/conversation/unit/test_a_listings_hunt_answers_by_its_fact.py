"""A listings hunt answers the manager by its FACT, with no face of its own (node 13.132, INI-078 F2 step 7c, row 13):
`search_listing.hunt` is the one hunt both channels run — it joins an open flow or starts one, runs the fast pass and
returns what happened; the old turn's spoken face is composed on top of it, the manager's model says the fact itself.
The rows found reach the model with their evidence (the prices are figures it may claim); his words, never the model's
query, are what the hunt is asked with; a hunt that joined a search parked on his yes returns its question."""
from __future__ import annotations

import asyncio

from nucleo.acts import search_listing
from nucleo.conversation_host import acts_tasks, routing


def _no_flow(monkeypatch, joined=None):
    from nucleo.turn import open_flows

    async def join(text):
        return dict(joined or {})
    monkeypatch.setattr(open_flows, "join", join)
    monkeypatch.setattr(search_listing, "_born", lambda asked: (7, "w_sheet"))


def test_the_hunt_returns_the_pass_and_the_manager_says_its_rows_with_evidence(monkeypatch):
    _no_flow(monkeypatch)
    passed = {}

    def fast_pass(query, **kw):
        passed.update(query=query, **kw)
        return {"delivered": True, "n": 2, "escalated": 0, "sheet": "w_sheet", "ctx": "w_car_a 9500 €; w_car_b 11200 €"}
    monkeypatch.setattr(search_listing, "fast_pass", fast_pass)
    monkeypatch.setitem(routing._last, "said", "w_find me a car under twelve thousand")
    got = acts_tasks.run("listings", {"query": "w_car", "price_max": 12000})
    assert got.status == "ok" and got.data["found"] == 2 and got.data["on_his_results_sheet"] is True
    assert "w_car_b 11200" in got.data["rows"] and got.evidence and 11200 in got.evidence[0].numbers
    assert passed["operator_text"] == "w_find me a car under twelve thousand" and passed["new_sheet"] == "w_sheet"
    assert asyncio.run(search_listing.hunt("w_x", {"query": "w_car"}))["kind"] == "done"


def test_a_hunt_parked_on_his_yes_returns_its_question_and_starts_nothing(monkeypatch):
    _no_flow(monkeypatch, {"absorbed": True, "question": "w_shall I go on?", "flow": "f1"})
    monkeypatch.setattr(search_listing, "fast_pass", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
    monkeypatch.setitem(routing._last, "said", "w_the cheaper one")
    got = acts_tasks.run("listings", {"query": "w_car"})
    assert got.status == "ok" and got.data["asked"] == "w_shall I go on?"

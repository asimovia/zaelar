"""One request, one errand, one sheet (V2-843, 2026-11-02).

A car request dictated in fragments: the first fragment parked on his «yes» (it moves money); each later fragment
reached the listing fast pass with the joined request. The flow door DID match the parked errand every time — and
answered «no flow», because a parked errand has no sheet yet. Each fragment minted a box of its own, its escalation
was absorbed into the parked errand, and three cards stayed on «Searching in depth…» with nobody behind them.

The decision was right; its consequence was not. A request a live errand covers lands in that errand's sheet — the
one its id names when it has none yet — and a folded launch never leaves its box behind.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from nucleo import sheets
from nucleo.acts import search_listing
from nucleo.dispatch import confirm
from nucleo.errands import launches

REQ = {"query": "SUV"}

#: The same request in fragments, each turn carrying the joined text (EN as measured, ES, and a flat).
CAR_EN = ("I wanna buy a car. A new car.",
          ["let's focus on the car. I wanna... One of those big runners.",
           "let's focus on the car. I wanna... One of those big runners. Two or three good offers right now.",
           "let's focus on the car. I wanna... One of those big runners. Two or three good offers right now. "
           "The price, thirty, forty, fifty. Show it as soon as possible."])
CAR_ES = ("Quiero comprarme un coche nuevo.",
          ["Vale, el coche. Uno de esos todoterreno grandes.",
           "Vale, el coche. Uno de esos todoterreno grandes. Dos o tres buenas ofertas.",
           "Vale, el coche. Uno de esos todoterreno grandes. Dos o tres buenas ofertas. Entre treinta y cincuenta mil.",
           "Vale, el coche. Uno de esos todoterreno grandes. Dos o tres buenas ofertas. Entre treinta y cincuenta mil. "
           "Enséñamelo cuanto antes."])
FLAT_EN = ("Find me a flat to rent in Madrid.",
           ["The flat, two bedrooms.", "The flat, two bedrooms. Near Retiro, under fifteen hundred."])


@pytest.fixture
def scene(monkeypatch):
    """No live flow but what each test parks; `fast_pass` replaced by a recorder; the judge answers by request."""
    launches.reset()
    calls: list[dict] = []
    judge = {"id": ""}

    def fake_pass(query, **kw):
        calls.append(kw)
        return {"delivered": False, "n": 0, "sheet": kw.get("sheet") or kw.get("new_sheet"), "escalated": 0,
                "reason": "", "ctx": ""}

    monkeypatch.setattr(search_listing, "fast_pass", fake_pass)
    monkeypatch.setattr(search_listing, "_taken_line", lambda: "")
    monkeypatch.setattr("nucleo.request.append.about_a_live_errand", lambda text, live: judge["id"])
    monkeypatch.setattr("nucleo.dispatch.pending_summaries", lambda: [])
    monkeypatch.setattr("nucleo.acts.errand.pending", lambda: [])
    monkeypatch.setattr(confirm, "_PENDING_CONFIRM", {})
    yield calls, judge
    launches.reset()


def _park(tid: str, request: str, sheet: str = "") -> dict:
    confirm._PENDING_CONFIRM[tid] = {"request": request, "question": "¿Lo hago?", "sheet": sheet, "ts": time.time(),
                                     "context": {}}
    return confirm._PENDING_CONFIRM[tid]


def test_two_different_requests_are_two_errands_and_two_sheets(scene):
    calls, judge = scene
    _park("2", CAR_EN[0])
    judge["id"] = ""             # the judge says: not about the car
    asyncio.run(search_listing.listings({"text": "find me a used acoustic guitar in Barcelona"}, REQ))
    assert calls[0]["new_sheet"] and not calls[0]["sheet"], "a different request was folded into the car"
    assert confirm._PENDING_CONFIRM["2"].get("refinements") is None, "the guitar was folded into the car"


def test_a_new_flow_names_its_sheet_after_the_errand_it_hands_on_to(scene):
    calls, _judge = scene
    asyncio.run(search_listing.listings({"text": "find me a used acoustic guitar in Barcelona"}, REQ))
    eid = calls[0]["errand_id"]
    assert eid and calls[0]["new_sheet"] == sheets.sheet_id_for(eid), \
        "a new hunt's sheet is a counter of its own, not the errand it hands on to"


# ── S2 · the reserved id is the errand's; an unreserved escalation is unchanged ──────────────────────────────

@pytest.fixture
def portal(monkeypatch):
    from nucleo.acts import errand
    errand.reset()
    sent: list = []
    monkeypatch.setattr(errand, "_emit_bus", lambda topic, payload: sent.append((topic, payload)))
    monkeypatch.setattr("nucleo.consequence.passes", lambda *a, **kw: True)
    yield errand, sent
    errand.reset()


def test_a_born_errand_is_the_one_that_hands_on(portal, monkeypatch):
    errand, sent = portal
    monkeypatch.setattr("nucleo.circuit.ledger.born", lambda tid, req, ctx=None: f"b1-{tid}")
    tid, uid = errand.born("find me a used acoustic guitar in Barcelona")      # V2-844 F1a: born, not reserved
    assert errand.escalate_to_slowbrain("find me a used acoustic guitar in Barcelona", task_id=tid,
                                        context={"born_uid": uid}) == tid
    assert [p["id"] for t, p in sent if t == "escalate.requested"] == [tid]


def test_an_unreserved_escalation_takes_the_next_id_as_before(portal):
    errand, sent = portal
    first = errand.escalate_to_slowbrain("find me a used acoustic guitar in Barcelona")
    second = errand.escalate_to_slowbrain("book a table for two in Seville tonight")
    assert (first, second) == (1, 2)


def test_the_errands_own_filled_sheet_is_never_opened_fresh(monkeypatch, tmp_path):
    """The fast pass filled the errand's sheet under its reserved id; the worker that inherits it must not wipe it."""
    from types import SimpleNamespace

    from widgets import store
    from widgets.results import data as sheet_mod
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    opened: list = []
    monkeypatch.setattr(sheet_mod, "begin_task", lambda title, fresh=True, sheet="": opened.append((sheet, fresh)))
    mine = sheets.sheet_id_for("7")
    store.save(sheet_mod.sheet_key(mine), {"title": "a guitar", "items": [{"title": "Yamaha FG800"}]})
    rec = SimpleNamespace(task_id="7", sheet=mine, uid="", goal="a guitar", title="", label="", heard="", brief="")
    sheets._sheet_open(rec, show=False)
    assert opened == [(mine, False)], "the worker wiped the rows its own fast pass had already delivered"


# ── S3 · a launch folded into a parked errand (another door's escalation) never leaves its box behind ─────

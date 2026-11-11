"""The first rows of an errand holding a deferred choice: what WOULD be relayed — in SHADOW (V2-878 §5, node 2.1680).

When the rows land (`first_rows_notice.landed`, the sheet's door), the choice he made before they existed is the thing
the worker should act on («ya hay filas: elige por …»). In shadow it is emitted (`thread` · `would_relay`, his words and
how long it was held) once per errand, and nothing is injected.
"""
from __future__ import annotations

from nucleo.circuit import ledger
from nucleo.turn import first_rows_notice, pick_pending

from ._pick_fixture import thread, world  # noqa: F401

ROWS = [{"title": "Dell S2722QC", "url": "https://example.org/a", "price": "289 €"}]


def test_the_first_rows_report_the_choice_once_and_relay_nothing(world, monkeypatch):
    uid = world["errand"]("k3", "buscar monitores", "k3")
    ledger.card_written(uid, pick_pending={"heard": "abre el que sea mejor oferta", "at": 1})
    monkeypatch.setattr(first_rows_notice, "_errand_of", lambda sheet: {"id": "k3", "sheet": "k3"})
    monkeypatch.setattr(first_rows_notice.threading, "Thread", lambda **k: type("T", (), {"start": lambda s: None})())
    first_rows_notice.forget()
    first_rows_notice.landed("results::k3", ROWS)
    (ev,) = thread(world, "would_relay")
    assert ev["heard"] == "abre el que sea mejor oferta" and ev["shadow"] is True and ev["held_s"] > 0
    assert not world["injected"] and not world["relayed"], "a shadow relayed his words"
    first_rows_notice.forget()
    first_rows_notice.landed("results::k3", ROWS)
    assert len(thread(world, "would_relay")) == 1, "reported twice for one errand"


def test_an_errand_with_no_deferred_choice_reports_nothing(world):
    world["errand"]("k4", "buscar monitores", "k4")
    assert pick_pending.at_first_rows("results::k4", {"id": "k4"}) is None and not thread(world, "would_relay")

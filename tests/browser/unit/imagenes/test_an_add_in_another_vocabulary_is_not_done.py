"""The empty act is a CLASS, not the timer (V2-879): a second card, the images' `add`.

`imagenes.add` declares `items`. A call in another vocabulary (`{"images": [...]}`) answered `{"ok": True, "added": 0}`
and the card did not change — the same «ok over nothing» the timer gave «Listo» for. At the single funnel it now comes
back as the `slots_unfilled` refusal naming `items`; the same images under the declared key are added and stand.
"""
from __future__ import annotations

import asyncio

from widgets import contract, server_api
from widgets.imagenes import data as imagenes

IMG = {"url": "https://example.org/a.jpg", "title": "A"}


def _n() -> int:
    return len((imagenes.view_data() or {}).get("items") or [])


def test_an_add_in_another_vocabulary_that_changed_nothing_is_refused():
    before = _n()
    res = asyncio.run(server_api._dispatch("imagenes", "add", {"images": [IMG]}))
    assert res["ok"] is False and res["error"] == contract.SLOTS_UNFILLED, res
    assert res["unmet"] == ["items"] and _n() == before


def test_the_declared_slot_adds_and_its_answer_stands():
    before = _n()
    res = asyncio.run(server_api._dispatch("imagenes", "add", {"items": [IMG]}))
    assert res.get("ok") is not False and _n() == before + 1, res

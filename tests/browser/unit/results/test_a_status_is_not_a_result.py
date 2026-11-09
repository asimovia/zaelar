"""A result is a FINDING, never a status: a row the worker writes says where it was found (V2-868 D4).

Measured on the operator's console: an errand parked on a sign-in wrote ONE row whose facts were its own status
(«login pending», «daily check 11:00») plus a recalled price, and the sheet listed it as a result. The door's rule is
STRUCTURAL, never a word list: a row that states data needs a `url` (its own or a part's) or a `source` the sheet
knows; otherwise it is filed in `rejected` with a reason the worker reads. Only the worker's writes are screened —
the bridge stamps them — because the engine's own producers carry the page or index they read by construction.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from widgets.results import data as sheet
from widgets.results import provenance

WORKER = {provenance.WRITER: provenance.WORKER}
STATUS = {"title": "AliExpress order", "price": "15,22 €",
          "facts": [{"label": "state", "value": "login pending"}, {"label": "check", "value": "daily 11:00"}]}
FOUND = {"title": "Order 8812 — shipped", "price": "15,22 €", "url": "https://shop.example.test/order/8812"}


def _titles(s: str) -> list[str]:
    return [i["title"] for i in sheet.view_data(s)["items"]]


def test_a_status_the_worker_writes_is_filed_with_its_reason_and_the_finding_stays():
    res = sheet.apply_action("present", {"sheet": "t868a", "title": "Parcel", "items": [STATUS, FOUND], **WORKER})
    assert _titles("t868a") == [FOUND["title"]]
    rej = {r["title"]: r for r in sheet.view_data("t868a")["rejected"]}
    assert rej["AliExpress order"]["why"] == provenance.WHY and rej["AliExpress order"]["source"] == "provenance"
    assert res["no_provenance"] == ["AliExpress order"] and "rejected" in res["note_for_worker"]


def test_an_append_meets_the_same_door():
    sheet.store.save(sheet.sheet_key("t868b"), {"title": "Parcel", "items": []})
    sheet.apply_action("append", {"sheet": "t868b", "items": [STATUS], **WORKER})
    assert _titles("t868b") == []


@pytest.mark.parametrize("named", ["Booking", "BOOKING", "booking.com", "https://www.booking.com/x"])
def test_a_row_naming_a_source_the_sheet_knows_is_a_finding(named):
    row = {**STATUS, "title": "Hotel Sol", "source": named}
    sheet.apply_action("present", {"sheet": "t868c", "items": [row],
                                   "sources": [{"name": "Booking", "url": "https://www.booking.com"}], **WORKER})
    assert _titles("t868c") == ["Hotel Sol"]


def test_a_source_the_sheet_does_not_know_is_no_provenance():
    sheet.apply_action("present", {"sheet": "t868d", "items": [{**STATUS, "source": "my memory"}], **WORKER})
    assert _titles("t868d") == []


def test_a_bare_name_claims_nothing_and_a_part_with_a_link_carries_its_row():
    plan = {"title": "Plan A", "price": "1.840 €", "parts": [{"title": "Ferry", "url": "https://ferry.example.test"}]}
    sheet.apply_action("present", {"sheet": "t868e", "items": [{"title": "Option one"}, plan], **WORKER})
    assert _titles("t868e") == ["Option one", "Plan A"]


def test_the_engines_own_producers_are_not_screened_and_the_worker_cannot_unstamp_itself():
    sheet.apply_action("present", {"sheet": "t868f", "items": [STATUS]})       # an extraction, Zaelar's search
    assert _titles("t868f") == ["AliExpress order"]
    from nucleo.cli import worker_api_exec
    stamped = {**{"writer": "engine"}, **worker_api_exec._WRITER.get("results", {})}
    assert stamped["writer"] == provenance.WORKER, "the bridge's stamp wins over the worker's own key"


def test_disarm_the_screen_and_a_status_lands():
    """Without the door, the measured status row is listed as a result: the guard above is what stops it."""
    src = Path(provenance.__file__)
    orig = src.read_text(encoding="utf-8")
    try:
        src.write_text(orig.replace("(on if sourced(it, srcs) else off).append(it)", "on.append(it)"), encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        import importlib
        importlib.reload(provenance)
        sheet.apply_action("present", {"sheet": "t868g", "items": [STATUS], **WORKER})
        assert _titles("t868g") == ["AliExpress order"], "disarmed, the status is a result again"
    finally:
        src.write_text(orig, encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        import importlib
        importlib.reload(provenance)

"""The chart's end state is a FRESH fetch, never the chart left on screen (operator's four principles, 2026-11-08).

`show`/`range`/`refresh` declare `fetched_at changed` + `failed absent`. A failure of the price source used to be
stored in `error`, and the verifier reads a view with an `error` as «cannot be read» — so a failed refresh over
yesterday's chart was «unverifiable» and nothing iterated. The failure is a readable outcome now (`failed`), the
view's `error` stays empty while the card is fine, and `fetched_at` moves on every fetch, even two in one second.
"""
from __future__ import annotations

import pytest

from nucleo.circuit import spec, verify
from widgets.markets import data as mk


def _chart(symbol="AAPL"):
    return {"chart": {"result": [{
        "meta": {"symbol": symbol, "currency": "USD", "shortName": "Apple Inc.", "regularMarketPrice": 110.0,
                 "previousClose": 105.0, "chartPreviousClose": 105.0, "regularMarketTime": 1790366400},
        "timestamp": [1790300000, 1790300300], "indicators": {"quote": [{"close": [100.0, 110.0]}]}}]}}


@pytest.fixture
def yahoo(monkeypatch, tmp_path):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(mk.time, "time", lambda: 1_790_000_000.5)      # every fetch inside ONE second
    state = {"down": False}

    def get(url):
        if state["down"]:
            raise OSError("connection refused")
        return _chart()
    monkeypatch.setattr(mk, "_get", get)
    return state


def _done(action, payload):
    dw = spec.render("markets", action, payload)
    assert dw, f"markets:{action} declares no renderable end state"
    return dw


def test_a_fetch_reads_met_and_a_second_in_the_same_second_too(yahoo):
    dw = _done("show", {"symbol": "AAPL"})
    assert mk.apply_action("show", {"symbol": "AAPL"})["ok"]
    assert verify.check(dw) is True
    dw = _done("refresh", {})
    assert mk.apply_action("refresh", {})["ok"]
    assert verify.check(dw) is True, "two fetches in one second are two"
    assert mk.view_data()["error"] == "" and mk.view_data()["failed"] == ""


def test_a_failed_refresh_over_the_old_chart_reads_unmet_not_unverifiable(yahoo):
    assert mk.apply_action("show", {"symbol": "AAPL"})["ok"]
    yahoo["down"] = True
    dw = _done("range", {"range": "1mo"})
    assert not mk.apply_action("range", {"range": "1mo"})["ok"]
    view = mk.view_data()
    assert view["error"] == "" and "connection refused" in view["failed"]
    assert view["symbol"] == "AAPL", "the last chart stays on screen, marked stale"
    assert verify.check(dw) is False


def test_an_older_store_with_the_failure_in_error_is_read_as_failed(yahoo):
    mk.store.save(mk.WID, {**mk._seed(), "symbol": "AAPL", "error": "OSError: boom"})
    view = mk.view_data()
    assert view["error"] == "" and view["failed"] == "OSError: boom"

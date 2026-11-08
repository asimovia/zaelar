"""Each sheet action declares the outcome it produces, on fields the view always carries (operator, 2026-11-08).

`detail` reads the record it opened (`focus changed`, so a refused detail over another open record reads unmet),
`choose` his pick, `list` the grid, `tab` the tab on screen by ANY word for it («fuentes» and «sources» alike —
`tab_words`, derived every read), `clear` an empty sheet. And `auth_done` with the browser down is an OFFER in the
reply, never a dead stop.
"""
from __future__ import annotations

import pytest

from nucleo.circuit import spec, verify
from widgets.results import data

ITEMS = [{"title": "Dell 27 Plus S2725QC", "price": "$329.99"}, {"title": "KTC M27P6S", "price": "$399.99"}]


@pytest.fixture
def sheet(monkeypatch, tmp_path):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    assert data.apply_action("present", {"items": ITEMS}).get("ok")


def _run(action, payload):
    dw = spec.render("results", action, payload)
    assert dw, f"results:{action} declares no renderable end state"
    got = data.apply_action(action, payload)
    return got, verify.check(dw)


def test_a_detail_reads_met_and_a_refused_one_over_an_open_record_reads_unmet(sheet):
    got, met = _run("detail", {"index": 1})
    assert got.get("ok") and met is True
    got, met = _run("detail", {"title": "Philips nowhere"})
    assert not got.get("ok")
    assert met is False, "the record left open is not the one he asked for"


def test_choose_and_list_read_their_outcome(sheet):
    got, met = _run("choose", {"index": 2})
    assert got.get("ok") and met is True
    _run("detail", {"index": 1})
    got, met = _run("list", {})
    assert got.get("ok") and met is True


@pytest.mark.parametrize("said", ["sources", "fuentes", "criterios", "summary"])
def test_a_tab_is_met_by_any_word_for_it(sheet, said):
    got, met = _run("tab", {"tab": said})
    assert got.get("ok") and met is True, data.view_data().get("tab_words")


def test_a_tab_that_did_not_move_reads_unmet(sheet):
    assert verify.check(spec.render("results", "tab", {"tab": "fuentes"})) is False


def test_the_words_are_derived_never_stored(sheet):
    data.apply_action("tab", {"tab": "fuentes"})
    from widgets import store
    assert "tab_words" not in store.load(data.sheet_key(""), {})


def test_clear_reads_an_empty_sheet(sheet):
    got, met = _run("clear", {})
    assert got.get("ok") and met is True


def test_auth_done_with_the_browser_down_is_an_offer(sheet, monkeypatch):
    from widgets import supervisor
    monkeypatch.setattr(supervisor, "enqueue", lambda *a, **k: False)
    got = data.apply_action("auth_done", {"task_id": "t3"})
    assert got["ok"] is False and got["offer"], got
    assert got["retry"] == {"action": "auth_done", "payload": {"task_id": "t3"}}


def test_the_process_tab_reads_met_while_the_panel_it_opened_is_fresh(sheet, monkeypatch):
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda *a, **k: None)
    got, met = _run("tab", {"tab": "proceso"})
    assert got.get("ok") and got["opened"] == "procesos" and met is True
    from widgets.results.derived import _tab_words, PROCESS_OPENED_TTL_S
    stale = {"tab": "results", "process_opened": 1000.0}
    assert "proceso" not in _tab_words(stale, now=1000.0 + PROCESS_OPENED_TTL_S + 1)

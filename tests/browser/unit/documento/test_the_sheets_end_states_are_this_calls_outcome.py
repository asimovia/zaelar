"""The sheet's end states are what THIS call left on it (2026-11-08).

`show` declared «a body is present», which any document already on the sheet satisfies: a `show` that never ran
read «met». `clear` and `save_to_library` declared nothing. The sheet now writes a `rev` counter (+1 per show, never
reset by `clear`), `saved_at`/`saved_rel` (the last save to the library) and a `focus` that is always a value, and
the manifest reads them: `show` = `rev changed` and `empty is false`; `clear` = `empty is true`; `save_to_library` =
`saved_at changed`; `goto` = `focus changed`. Each is read BEFORE the op (not met) and AFTER it (met).
"""
from __future__ import annotations

import pytest


@pytest.fixture
def doc(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.documento import data as _d
    return _d


def _born(action, payload=None):
    from nucleo.circuit import spec
    dw = spec.render("documento", action, payload or {})
    assert dw, f"documento:{action} declares no end state"
    return dw


def _met(dw):
    from nucleo.circuit import verify
    return verify.check(dw)


def test_a_show_is_not_met_by_the_document_already_there(doc):
    doc.apply_action("show", {"title": "Recipe", "body": "# Recipe\n\nFlour and water."})
    dw = _born("show", {"title": "Report", "body": "# Report"})
    assert _met(dw) is False, "the recipe already on the sheet met the end state of a show that has not run"
    doc.apply_action("show", {"title": "Report", "body": "# Report\n\nThe findings."})
    assert _met(dw) is True


def test_a_refused_show_stays_unmet(doc):
    doc.apply_action("show", {"title": "Recipe", "body": "# Recipe"})
    dw = _born("show", {"title": "Empty"})
    assert doc.apply_action("show", {"title": "Empty", "body": "  "})["ok"] is False
    assert _met(dw) is False


def test_the_show_counter_never_goes_back(doc):
    doc.apply_action("show", {"title": "A", "body": "a"})
    doc.apply_action("show", {"title": "B", "body": "b"})
    assert doc.view_data()["rev"] == 2
    doc.apply_action("clear", {})
    assert doc.view_data()["rev"] == 2, "a counter that resets could meet a later show's `changed` by accident"


def test_a_clear_is_met_by_an_empty_sheet(doc):
    doc.apply_action("show", {"title": "A", "body": "a"})
    dw = _born("clear")
    assert _met(dw) is False
    doc.apply_action("clear", {})
    assert _met(dw) is True


def test_a_save_is_met_by_THIS_save(doc, monkeypatch):
    from library import index as _lib
    monkeypatch.setattr(_lib, "save_text", lambda name, body, kind="", replace="": {
        "ok": True, "rel": f"documents/{name}.md", "path": f"/tmp/{name}.md", "entry": {"name": name}})
    doc.apply_action("show", {"title": "Notes", "body": "# Notes"})
    doc.apply_action("save_to_library", {})
    dw = _born("save_to_library")
    assert _met(dw) is False, "the earlier save met the end state of a save that has not run"
    doc.apply_action("save_to_library", {})
    assert _met(dw) is True
    assert doc.view_data()["saved_rel"] == "documents/Notes.md"


def test_a_goto_is_readable_before_any_focus_was_set(doc):
    doc.apply_action("show", {"title": "Doc", "body": "# The history\n\nHow it began.\n\n# Proof of work\n\nHow blocks are sealed."})
    assert isinstance(doc.view_data()["focus"], dict), "a None focus reads «unverifiable», never unmet"
    dw = _born("goto", {"text": "proof of work"})
    assert _met(dw) is False
    assert doc.apply_action("goto", {"text": "proof of work"})["ok"] is True
    assert _met(dw) is True


def test_every_key_an_end_state_reads_is_always_in_the_view(doc):
    v = doc.view_data()
    for key in ("rev", "saved_at", "saved_rel", "focus", "empty"):
        assert key in v and v[key] is not None, key

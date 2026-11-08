"""A result on screen is picked the way he names it — its number, its name or words of it (V2-861).

The music card was the measured case (a list named among five: «not this one» had nothing to pick from). A survey of
every card the same day found the same gap in three more: the results sheet's `choose` took only the EXACT title, the
file explorer listed what a search found with no numbers and `open_file` needed an id, and the photo gallery's search
told the brain only the year counts. Each now numbers what it shows and resolves a spoken reference through the same
rule (`widgets/result_refs.py` for the explorer; the sheet's own finder, which `detail` already used, for `choose`).
Disarm: `_a_choose` storing the title as given → `choose` by number goes red; `_named_entry` returning the payload
untouched → the explorer tests go red.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def stores(monkeypatch, tmp_path):
    import widgets.store as store
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
    return tmp_path


def test_the_sheet_chooses_a_row_by_its_number_or_words_and_keeps_its_real_title(stores):
    from widgets.results import data as results
    assert results.apply_action("present", {"title": "Hotels", "choosable": True, "items": [
        {"title": "Hotel Arts Barcelona"}, {"title": "Casa Fuster"}, {"title": "Hotel Neri"}]})["ok"]
    by_number = results.apply_action("choose", {"index": 2})
    assert by_number["ok"] and results.view_data()["chosen"] == "Casa Fuster", "the card marks the row it is"
    by_words = results.apply_action("choose", {"title": "neri"})
    assert by_words["ok"] and by_words["chosen"] == "Hotel Neri"
    assert not results.apply_action("choose", {"title": "Ritz"})["ok"], "a row that is not there is refused"


ENTRIES = [{"id": "f1", "name": "Contratos", "kind": "folder"},
           {"id": "d1", "name": "Contrato alquiler 2025.pdf", "kind": "file"},
           {"id": "d2", "name": "Factura luz octubre.pdf", "kind": "file"}]


def test_the_explorer_opens_the_row_he_names_by_number_or_name():
    from widgets.archivos import data as _files  # noqa: F401 — the card loads its actions through data
    from widgets.archivos.actions import _named_entry
    db = {"entries": ENTRIES}
    assert _named_entry(db, "open_file", {"fileId": "3"})["fileId"] == "d2"
    assert _named_entry(db, "open_file", {"fileId": "factura luz"})["fileId"] == "d2"
    assert _named_entry(db, "open_folder", {"folderId": 1})["folderId"] == "f1"
    assert _named_entry(db, "open_file", {"fileId": "d1"}) == {"fileId": "d1"}, "an id on the list stays as it is"
    assert _named_entry(db, "open_file", {"fileId": "1"}) == {"fileId": "1"}, "a folder is not opened as a file"


def test_the_explorer_digest_numbers_what_it_shows(monkeypatch):
    from widgets.archivos import data as files
    monkeypatch.setattr(files, "_load", lambda: {"provider": "local", "query": "contrato", "entries": ENTRIES})
    d = files.prompt_digest()
    assert "1. 📁 Contratos" in d and "3. · Factura luz octubre.pdf" in d and "open_file{fileId: número o nombre}" in d


def test_the_gallery_digest_numbers_what_a_search_found(monkeypatch):
    from widgets.fotos import data as photos
    monkeypatch.setattr(photos, "_load", lambda: {
        "connected": True, "total": 40, "years": [{"year": 2024, "count": 40}],
        "active_filter": {"query": "Marrakech"},
        "items": [{"id": "p1", "filename": "IMG_0101.jpg", "taken_at": "2024-04-02T10:00:00Z"},
                  {"id": "p2", "filename": "IMG_0102.jpg", "taken_at": "2024-04-03T11:00:00Z"}]})
    d = photos.prompt_digest()
    assert "BÚSQUEDA EN PANTALLA («Marrakech», 2 fotos)" in d and "2. IMG_0102.jpg — 2024-04-03" in d

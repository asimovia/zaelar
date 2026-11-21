"""What a turn reads of the screen is read once, and what is remembered between turns never outlives a write.

Sampled on a live engine (2026-11-19, the loop held 1–5 s several times per turn): every door that resolves a
reference rebuilt the directory's whole index (the store read, ranked, and an n² membership test), the brief's table
built its screen question three times and read the rows again for the row question, and every catalogue lookup listed
both widget roots and stat'ed two files per widget. Three memos, each with the thing that invalidates it:

  · the directory's index is built once per VERSION of its store — any write, by this process or another, is a new one;
  · the brief reads each open card's rows once per turn (`brief_screen.one_read`);
  · the widget folders are scanned at most once per `runtime.SCAN_TTL_S` — a folder added or removed and a lifecycle
    op (`invalidate`) are seen at once.
"""
from __future__ import annotations

import json
import os

import pytest

from nucleo.turn import brief, brief_screen


# ── the directory's index ────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def ct(tmp_path, monkeypatch):
    """ISOLATED store with three people, one of them blocked (never a candidate, still mapped), and a count of the
    whole-store reads the index makes."""
    from widgets import directory, store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    directory._WINDOW.clear()
    from widgets.contactos import data as d
    db = d.load_db()
    for i, row in enumerate([{"name": "Quinn Ferrer"}, {"name": "Rowan Vidal", "favorite": True},
                             {"name": "Sasha Blocked", "flags": ["blocked"]}]):
        db["contacts"].append({"id": f"c{i}", "kind": "person", "aliases": [], "relation": "", "channels": [], **row})
    store.save(d.WIDGET_ID, db)
    reads = {"n": 0}
    real = d.load_db

    def _counted():
        reads["n"] += 1
        return real()
    monkeypatch.setattr(d, "load_db", _counted)
    d.reads = reads
    return d


def _labels(d) -> list[str]:
    return [r["label"] for r in d.ref_index()]


def test_an_unchanged_directory_is_indexed_once(ct):
    first = _labels(ct)
    assert first == ["Rowan Vidal", "Quinn Ferrer", "Sasha Blocked"], "closest first, and a never-candidate last"
    assert _labels(ct) == first and _labels(ct) == first
    assert ct.reads["n"] == 1, "three asks, one read of the store"


def test_a_write_is_seen_by_the_next_read(ct):
    from widgets import store
    assert len(_labels(ct)) == 3
    db = store.load(ct.WIDGET_ID)
    db["contacts"].append({"id": "c9", "kind": "person", "name": "Tavi Soler", "channels": []})
    store.save(ct.WIDGET_ID, db)
    assert "Tavi Soler" in _labels(ct), "a contact saved after the index was built is in the next index"
    db["contacts"] = [c for c in db["contacts"] if c["id"] != "c0"]
    store.save(ct.WIDGET_ID, db)
    assert "Quinn Ferrer" not in _labels(ct), "and a removed one is out of it"


def test_a_write_by_another_process_is_seen_too(ct):
    from widgets import store
    assert len(_labels(ct)) == 3
    path = os.path.join(store.data_dir(ct.WIDGET_ID), "state.json")
    db = json.load(open(path, encoding="utf-8"))
    db["contacts"][0]["name"] = "Quinn Renamed"
    before = os.stat(path).st_mtime_ns
    with open(path, "w", encoding="utf-8") as f:       # not through `store.save`: this process counted no change
        json.dump(db, f)
    os.utime(path, ns=(before + 1_000_000, before + 1_000_000))
    assert "Quinn Renamed" in _labels(ct)


def test_a_caller_that_edits_its_rows_edits_nobody_elses(ct):
    rows = ct.ref_index()
    rows[0]["label"] = "scribbled"
    rows.clear()
    assert _labels(ct)[0] == "Rowan Vidal"


def test_disarm_an_index_that_ignores_the_store_version_serves_the_old_directory(ct, monkeypatch):
    from widgets import store
    from widgets.contactos import digest
    monkeypatch.setattr(digest, "_index_key", lambda: "always the same")
    assert len(_labels(ct)) == 3
    db = store.load(ct.WIDGET_ID)
    db["contacts"].append({"id": "c9", "kind": "person", "name": "Tavi Soler", "channels": []})
    store.save(ct.WIDGET_ID, db)
    assert "Tavi Soler" not in _labels(ct), "this is the stale read the store's version in the key prevents"


# ── the brief reads the screen once per turn ─────────────────────────────────────────────────────────────────────
@pytest.fixture
def card(monkeypatch):
    """Two rows on a card whose actions each must name one, and an index that counts its reads."""
    from nucleo.acts import frontend
    from widgets import refs
    reads = {"n": 0}

    def _index(base):
        reads["n"] += 1
        return [{"field": "contactId", "id": "c1", "label": "Quinn Ferrer"},
                {"field": "contactId", "id": "c2", "label": "Rowan Vidal"}]
    acts = {f"act_{i}": {"desc": f"does thing {i} to one person"} for i in range(6)}
    monkeypatch.setattr(frontend, "declared_actions", lambda base: acts if base == "people" else {})
    monkeypatch.setattr(refs, "id_field_for_action", lambda base, action: "contactId")
    monkeypatch.setattr(refs, "selector_is_optional", lambda base, action, field: False)
    monkeypatch.setattr(refs, "_exposes_ref_index", lambda base: True)
    monkeypatch.setattr(refs, "_ref_index", _index)
    monkeypatch.setattr(brief_screen, "_card_label", lambda wid: wid)
    return reads


def test_the_whole_table_of_one_turn_reads_an_open_card_once(card):
    qs = brief.build("call Quinn", open_ids=["people"])
    assert brief.TARGET_KEY in qs and brief.ITEM_REF_KEY in qs, "both questions that read the rows were asked"
    assert brief.CATALOG_KEY not in qs, "and the gates that ask the screen question again still read it the same"
    assert card["n"] == 1, "the screen question, its two gates and the row question: one read"


def test_the_next_turn_reads_again(card):
    brief.build("call Quinn", open_ids=["people"])
    brief.build("call Rowan", open_ids=["people"])
    assert card["n"] == 2, "nothing of one turn's reading is kept for the next"


def test_each_asker_of_the_screen_question_gets_its_own(card):
    with brief_screen.one_read():
        q = brief_screen.target_question(["people"])
        q["criteria"].clear()
        assert len(brief_screen.target_question(["people"])["criteria"]) == 7


def test_disarm_outside_one_read_every_question_reads_the_card(card):
    brief_screen.target_question(["people"])
    brief_screen.target_question(["people"])
    brief_screen.item_ref_question(["people"])
    assert card["n"] == 3, "these are the reads `one_read` folds into one"


# ── the catalogue's folders ──────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def shelf(tmp_path, monkeypatch):
    """A widget root of its own with one widget, and a count of the scans of it."""
    from widgets import paths, runtime
    root = tmp_path / "shelf"
    root.mkdir()

    def add(wid: str, **man):
        (root / wid).mkdir(exist_ok=True)
        (root / wid / "widget.js").write_text("export default {}", encoding="utf-8")
        (root / wid / "manifest.json").write_text(json.dumps({"id": wid, "state": {}, **man}), encoding="utf-8")
    scans = {"n": 0}
    real = paths.iter_folders
    monkeypatch.setattr(paths, "roots", lambda: [str(root)])

    def _counted():
        scans["n"] += 1
        return real()
    monkeypatch.setattr(paths, "iter_folders", _counted)
    add("lamp", name="Lamp")
    runtime.invalidate()
    yield type("Shelf", (), {"add": staticmethod(add), "scans": scans, "root": root})
    runtime.invalidate()


def test_many_lookups_are_one_scan_of_the_folders(shelf):
    from widgets import runtime
    assert all(runtime.get("lamp")["name"] == "Lamp" for _ in range(50))
    assert runtime.get("nothing") is None and runtime.get(["not", "an", "id"]) is None
    assert shelf.scans["n"] == 1


def test_a_new_folder_and_a_lifecycle_op_are_seen_at_once(shelf):
    from widgets import runtime
    assert runtime.get("vase") is None
    shelf.add("vase", name="Vase")                       # a folder appears: its root moved
    assert runtime.get("vase")["name"] == "Vase"
    (shelf.root / "vase" / "widget.js").unlink()         # a change inside a folder moves no root: every lifecycle op
    runtime.invalidate()                                 # announces it, and the announcement is a new scan
    assert runtime.get("vase") is None, "a folder with no client code is debris, out of the catalogue"
    shelf.add("vase", name="Urn")
    runtime.invalidate()
    assert runtime.get("vase")["name"] == "Urn"


def test_an_unannounced_edit_in_place_is_seen_when_the_scan_expires(shelf, monkeypatch):
    from widgets import runtime
    assert runtime.get("lamp")["name"] == "Lamp"
    man = shelf.root / "lamp" / "manifest.json"
    man.write_text(json.dumps({"id": "lamp", "state": {}, "name": "Lantern"}), encoding="utf-8")
    at = os.stat(man).st_mtime_ns + 5_000_000_000
    os.utime(man, ns=(at, at))
    monkeypatch.setattr(runtime, "SCAN_TTL_S", 0.0)
    assert runtime.get("lamp")["name"] == "Lantern"


def test_disarm_with_no_trust_in_a_scan_every_lookup_scans(shelf, monkeypatch):
    from widgets import runtime
    monkeypatch.setattr(runtime, "SCAN_TTL_S", 0.0)
    for _ in range(5):
        runtime.get("lamp")
    assert shelf.scans["n"] >= 5, "this is the scan per lookup the turn used to pay"

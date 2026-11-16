"""A list asked for WITH what goes in it is one order: its rows land in the same write.

Measured on a text session (2026-11-16): «Make me a shopping list: oat milk, avocados, sourdough bread, eggs, …» →
`add_list {name}` — the only shape the card declared — created the list, the mouth said «Done.» and the list stayed
empty: the turn has one model call and no second one to add the rows. `add_list` now declares `items` and writes
them through the one `add_task` door; a list that already exists takes the rows it lacks, and a row asked twice is
not written twice.
"""
from __future__ import annotations

import importlib
import json
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def ag(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as _d
    return _d


def _titles(ag, name):
    from widgets.agenda import task_read
    db = ag.load_db()
    lst, _why = task_read.pick_list(db, name)
    return [t["title"] for t in task_read.items(db, lst["id"])]


def test_the_card_declares_the_rows_of_a_new_list():
    payload = json.loads((ENGINE / "widgets/agenda/manifest.json").read_text())["actions"]["add_list"]["payload"]
    assert "items" in payload, "the model can only fill a slot the card declares"


@pytest.mark.parametrize("name, rows", [
    ("Hardware store", ["wood screws", "sandpaper", "a spirit level"]),
    ("la ferretería", ["tornillos", "lija"]),
])
def test_a_list_asked_with_its_rows_is_written_whole(ag, name, rows):
    r = ag.apply_action("add_list", {"name": name, "items": rows})
    assert r.get("ok") and r.get("created"), r
    assert _titles(ag, name) == rows, "the list was created and its rows were not"


def test_rows_given_as_rows_or_as_lines_are_the_same_rows(ag):
    ag.apply_action("add_list", {"name": "Camping", "items": [{"title": "tent"}, {"title": "stove"}]})
    ag.apply_action("add_list", {"name": "Picnic", "items": "bread\ncheese\n"})
    assert _titles(ag, "Camping") == ["tent", "stove"] and _titles(ag, "Picnic") == ["bread", "cheese"]


def test_a_list_that_exists_takes_only_the_rows_it_lacks(ag):
    ag.apply_action("add_list", {"name": "Camping", "items": ["tent", "stove"]})
    r = ag.apply_action("add_list", {"name": "camping", "items": ["Stove", "lantern"]})
    assert r.get("ok") and r.get("existed"), r
    assert _titles(ag, "Camping") == ["tent", "stove", "lantern"], "asked twice is not two rows"


def test_a_list_with_no_rows_named_is_still_just_a_list(ag):
    r = ag.apply_action("add_list", {"name": "Someday"})
    assert r.get("ok") and "rows" not in r and _titles(ag, "Someday") == []


def test_disarmed_the_rows_are_dropped_again(ag):
    """The disarm: stop reading the rows and the list is born empty under the same `ok`."""
    from widgets.agenda import tasklists
    src = pathlib.Path(tasklists.__file__)
    original = src.read_text(encoding="utf-8")
    reader = 'for title in _rows_named(p.get("items") if "items" in p else p.get("tasks")):'
    assert reader in original, "the rows are no longer read where this disarm expects them"
    try:
        src.write_text(original.replace(reader, "for title in ():"), encoding="utf-8")
        importlib.reload(tasklists)
        r = ag.apply_action("add_list", {"name": "Garden", "items": ["seeds", "gloves"]})
        assert r.get("ok") and _titles(ag, "Garden") == [], "the mutation did not land"
    finally:
        src.write_text(original, encoding="utf-8")
        for pyc in (src.parent / "__pycache__").glob("tasklists.*.pyc"):
            pyc.unlink()
        importlib.reload(tasklists)
    ag.apply_action("add_list", {"name": "Garden", "items": ["seeds", "gloves"]})
    assert _titles(ag, "Garden") == ["seeds", "gloves"]

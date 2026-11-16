"""V2-887 step 6 — one person is one candidate: a contact named by its HANDLE whose letters spell another matched
contact's full name is that person.

Measured 2026-11-11 (his directory): «Raquel Salinas» matched the Google contact «Raquel Salinas Ortega» and the
address-named row «raquel.salinasortega» of the same person, and the send asked «which one?» between them;
«pedrosalinas12» sat beside «Pedro Salinas» the same way. A plain one-word name («Raquel») is a name, not a
handle, and stays a candidate of its own.
"""
from __future__ import annotations

import time

import pytest


def _person(cid, name, mail):
    return {"id": cid, "kind": "person", "name": name, "aliases": [], "relation": "",
            "channels": [{"platform": "email", "handle": mail, "chatId": mail, "volume": 1,
                          "last_seen": time.time() - 400 * 86400}]}


@pytest.fixture
def world(tmp_path, monkeypatch):
    from widgets import directory, store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets.contactos import data as cd
    directory._WINDOW.clear(); directory._ASKED.clear()
    db = cd.load_db()
    db["contacts"] = [_person("c1", "Raquel Salinas Ortega", "r@x.com"),
                      _person("c2", "raquel.salinasortega", "raquel.salinasortega@example.org"),
                      _person("c3", "Pedro Salinas", "p@x.com"),
                      _person("c4", "pedrosalinas12", "pedrosalinas12@x.com"),
                      _person("c5", "Raquel Lozoya", "j@x.com"),
                      _person("c6", "Raquel", "solo@x.com")]
    cd.store.save(cd.WIDGET_ID, db)
    yield directory
    directory._WINDOW.clear(); directory._ASKED.clear()


@pytest.mark.parametrize("said", ["Raquel Salinas", "raquel salinas"], ids=["typed", "voice"])
def test_her_name_and_her_handle_are_one_candidate(world, said):
    assert [c["id"] for c in world.resolve(said, tolerant=False)] == ["c1"]


def test_pedro_and_his_handle_are_one_candidate(world):
    assert [c["id"] for c in world.resolve("Pedro Salinas", tolerant=False)] == ["c3"]


def test_a_plain_one_word_name_is_still_its_own_person(world):
    assert [c["id"] for c in world.resolve("Raquel", tolerant=False)] == ["c6"], "«Raquel» is a name, not a handle"
    ids = {c["id"] for c in world.resolve("Salinas", tolerant=False)}
    assert ids == {"c1", "c3"}, "each person once: neither handle row is a candidate of its own"

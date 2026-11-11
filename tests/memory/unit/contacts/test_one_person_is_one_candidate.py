"""V2-887 step 6 — one person is one candidate: a contact named by its HANDLE whose letters spell another matched
contact's full name is that person.

Measured 2026-11-11 (his directory): «Raquel Salvador» matched the Google contact «Raquel Salvador Esteban» and the
address-named row «raquel.salvadoresteban» of the same person, and the send asked «which one?» between them;
«pedrosalvador12» sat beside «Pedro Salvador» the same way. A plain one-word name («Raquel») is a name, not a
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
    db["contacts"] = [_person("c1", "Raquel Salvador Esteban", "r@x.com"),
                      _person("c2", "raquel.salvadoresteban", "raquel.salvadoresteban@bt.com"),
                      _person("c3", "Pedro Salvador", "p@x.com"),
                      _person("c4", "pedrosalvador12", "pedrosalvador12@x.com"),
                      _person("c5", "Raquel Jofre", "j@x.com"),
                      _person("c6", "Raquel", "solo@x.com")]
    cd.store.save(cd.WIDGET_ID, db)
    yield directory
    directory._WINDOW.clear(); directory._ASKED.clear()


@pytest.mark.parametrize("said", ["Raquel Salvador", "raquel salvador"], ids=["typed", "voice"])
def test_her_name_and_her_handle_are_one_candidate(world, said):
    assert [c["id"] for c in world.resolve(said, tolerant=False)] == ["c1"]


def test_pedro_and_his_handle_are_one_candidate(world):
    assert [c["id"] for c in world.resolve("Pedro Salvador", tolerant=False)] == ["c3"]


def test_a_plain_one_word_name_is_still_its_own_person(world):
    assert [c["id"] for c in world.resolve("Raquel", tolerant=False)] == ["c6"], "«Raquel» is a name, not a handle"
    ids = {c["id"] for c in world.resolve("Salvador", tolerant=False)}
    assert ids == {"c1", "c3"}, "each person once: neither handle row is a candidate of its own"

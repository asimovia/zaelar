"""A widget's store gets what it owes at the engine's START, and a start that repeats it changes nothing (V2-934).

A store's migration is lazy: `store.load` upgrades what it reads and writes nothing. A migration that does real work
— the contacts card folding the rows that are one person — therefore ran again on every read until somebody saved,
and on an engine nobody wrote to it never reached the disk. A widget now declares a start step
(`"background": {"on_start": true}` → `data.on_start()`), run once per start, off the loop, isolated.
"""
from __future__ import annotations

import json
import os

import pytest

MOBILE = "+34 600 11 22 33"


@pytest.fixture
def book(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets.contactos import data
    seeded = data.load_db()                  # a store in use: its group rows are already there, so a read writes nothing
    store.save(data.WIDGET_ID, {**seeded, "_v": 4, "next_id": 9, "contacts": [
        {"id": "c1", "kind": "person", "name": "Odile Varga Lund", "source": "google", "phone": MOBILE,
         "phones": [{"value": MOBILE, "label": ""}]},
        {"id": "c2", "kind": "person", "name": "Odi V", "source": "whatsapp", "phone": "600 11 22 33",
         "phones": [{"value": "600 11 22 33", "label": ""}],
         "channels": [{"platform": "whatsapp", "handle": "77000000109@lid", "chatId": "77000000109@lid"}]}]})
    return data, os.path.join(str(tmp_path), "contactos", "state.json")


def _disk(path):
    return json.load(open(path, encoding="utf-8"))


def test_the_contacts_card_declares_its_start_step():
    from widgets import runtime, start_steps
    card = next(w for w in runtime.catalog() if w.get("id") == "contactos")
    assert start_steps.declared(card) and not start_steps.declared({"background": "30s"})
    assert not start_steps.declared({"background": {"every": "30s"}})


def test_reading_alone_never_wrote_the_fold_and_the_start_step_does(book):
    data, path = book
    assert len([c for c in data.load_db()["contacts"]]) == 1, "the lazy migration folds what is READ"
    assert _disk(path)["_v"] == 4 and len(_disk(path)["contacts"]) == 2, "…and writes nothing"
    got = data.on_start()
    assert got == {"people": 1, "folded_now": 0, "folded_in_all": 1}, got      # folded by the migration it triggered
    disk = _disk(path)
    assert disk["_v"] == data.DB_VERSION and [c["id"] for c in disk["contacts"]] == ["c1"] and "c2" in disk["merged"]
    assert {"name": "Odi V", "source": "whatsapp"} in disk["contacts"][0]["knownAs"]


def test_a_second_start_changes_nothing(book):
    data, path = book
    data.on_start()
    before, stamp = open(path, encoding="utf-8").read(), os.stat(path).st_mtime_ns
    again = data.on_start()
    assert again["folded_now"] == 0 and again["folded_in_all"] == 1
    assert open(path, encoding="utf-8").read() == before and os.stat(path).st_mtime_ns == stamp, "not even rewritten"


def test_the_runner_runs_declared_steps_and_a_failing_one_never_holds_the_start(book, monkeypatch):
    from widgets import runtime, start_steps
    data, path = book
    monkeypatch.setattr(runtime, "catalog", lambda: [{"id": "contactos", "background": {"every": "30s", "on_start": True}},
                                                     {"id": "agenda", "background": {"every": "30s"}},
                                                     {"id": "nothing_here", "background": {"on_start": True}}])
    out = start_steps.run()
    assert set(out) == {"contactos", "nothing_here"} and out["contactos"]["folded_in_all"] == 1, out
    assert "error" in out["nothing_here"], "said, and the start goes on"
    assert _disk(path)["_v"] == data.DB_VERSION
    monkeypatch.setattr(data, "on_start", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert "boom" in start_steps.run()["contactos"]["error"]

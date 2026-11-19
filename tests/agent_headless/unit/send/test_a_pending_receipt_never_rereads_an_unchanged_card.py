"""A send that waits for its receipt reads the card when the card CHANGED, and naming a row never walks the directory.

Sampled on a live engine (2026-11-19, the loop held 1–5 s every ~2.5 s for ten minutes): a send whose receipt never
came was followed by re-reading the messaging card's whole view once per poll, on the loop, and that view named each of
its rows by walking every channel, address and number of a directory of thousands. Two things, each with what
invalidates it:

  · the follower reads the receipt when the card's store has a new VERSION (the connector's receipt is a write) and
    otherwise every `REREAD_S` — a receipt that lands is still told at the next poll;
  · the namer's lookups are built once per version of the contacts store — a save, or a write by another process, is
    seen by the next view.
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest

from nucleo.request import send_receipt


@pytest.fixture
def stores(tmp_path, monkeypatch):
    from widgets import chat_names, store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    chat_names._NAMES.update({"key": None, "index": None})
    return store


# ── the follower ─────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def followed(stores, monkeypatch):
    """A send being followed over a real store, with a count of the receipt reads and of what it ended as."""
    from nucleo import circuit
    stores.save("mensajeria", {"outbox": [{"ref": "r1", "state": "queued"}]})
    seen = {"reads": 0, "said": [], "settled": []}

    def receipt(wid, ref, done_when):
        seen["reads"] += 1
        row = next(r for r in stores.load("mensajeria")["outbox"] if r["ref"] == ref)
        return ("sent", "") if row["state"] == "sent" else ("", "")

    async def say(uid, stage, key, **fmt):
        seen["said"].append(stage)
    monkeypatch.setattr(send_receipt, "receipt", receipt)
    monkeypatch.setattr(send_receipt, "_say", say)
    monkeypatch.setattr(send_receipt, "_mark_landed", lambda *a: None)
    monkeypatch.setattr(send_receipt, "family", lambda *a: "send")
    monkeypatch.setattr(circuit, "settle", lambda **kw: seen["settled"].append(kw.get("verdict")))
    return seen


def _follow(**kw) -> str:
    return asyncio.run(send_receipt.follow("u1", "mensajeria", "send_to", {}, {"ref": "r1"}, None, **kw))


def test_an_unchanged_card_is_read_once_however_long_the_receipt_takes(followed):
    assert _follow(receipt_s=9, late_s=0.3, poll_s=0.005) == "unconfirmed"
    assert followed["reads"] == 1, "dozens of polls over a card nobody wrote: one read"
    assert followed["settled"] == ["unverifiable"]


def test_a_receipt_that_lands_is_read_at_the_next_poll(followed, stores):
    async def run():
        task = asyncio.ensure_future(send_receipt.follow("u1", "mensajeria", "send_to", {}, {"ref": "r1"}, None,
                                                         receipt_s=9, late_s=5, poll_s=0.005))
        await asyncio.sleep(0.05)
        stores.save("mensajeria", {"outbox": [{"ref": "r1", "state": "sent"}]})     # the connector's receipt
        return await asyncio.wait_for(task, 2)
    assert asyncio.run(run()) == "sent"
    assert followed["reads"] == 2 and followed["said"] == ["sent"] and followed["settled"] == ["met"]


def test_an_unchanged_card_is_still_reread_every_so_often(followed, monkeypatch):
    monkeypatch.setattr(send_receipt, "REREAD_S", 0.05)
    assert _follow(receipt_s=9, late_s=0.3, poll_s=0.005) == "unconfirmed"
    assert 3 <= followed["reads"] <= 8, "an end state may read more than its store: re-read on a slow clock"


def test_a_card_whose_version_cannot_be_told_is_read_every_poll(followed, monkeypatch):
    monkeypatch.setattr(send_receipt, "_version", lambda wid: None)
    assert _follow(receipt_s=9, late_s=0.1, poll_s=0.01) == "unconfirmed"
    assert followed["reads"] >= 5


# ── the namer ────────────────────────────────────────────────────────────────────────────────────────────────────
PEOPLE = [
    {"id": "a", "name": "Quinn Ferrer", "channels": [{"platform": "WhatsApp", "chatId": "111@lid"}]},
    {"id": "b", "name": "Rowan Vidal", "emails": [{"value": "Rowan@Example.com"}], "phone": "+34 600 111 222"},
    {"id": "c", "name": "Sasha One", "phones": [{"value": "600 333 444"}]},
    {"id": "d", "name": "Sasha Two", "phones": [{"value": "+34600333444"}]},
    {"id": "g", "name": "Team", "kind": "group", "channels": [{"platform": "whatsapp", "chatId": "9@g.us"}]},
    {"id": "h", "name": "Tavi Hidden", "hidden": True, "channels": [{"platform": "whatsapp", "chatId": "7@lid"}]},
]


@pytest.fixture
def directory(stores, monkeypatch):
    from widgets import directory as d
    from widgets.contactos import data as cd
    db = cd.load_db()
    db["contacts"] += [{"kind": "person", **p} for p in PEOPLE]
    stores.save(cd.WIDGET_ID, db)
    reads = {"n": 0}
    real = cd.load_db

    def counted():
        reads["n"] += 1
        return real()
    monkeypatch.setattr(cd, "load_db", counted)
    d.reads, d.cd = reads, cd
    return d


def _named(d, platform, chat_id, fallback="as the platform said") -> str:
    return d.namer()(platform, chat_id, fallback)["name"]


def test_a_conversation_is_named_by_its_contact_through_the_index(directory):
    d = directory
    assert _named(d, "whatsapp", "111@lid") == "Quinn Ferrer", "the contact holding this conversation"
    assert _named(d, "email", "rowan@example.com") == "Rowan Vidal", "the address, folded"
    assert _named(d, "whatsapp", "34600111222@s.whatsapp.net") == "Rowan Vidal", "the number the id carries"
    assert _named(d, "whatsapp", "600111222@c.us") == "Rowan Vidal", "with or without its country prefix"
    assert _named(d, "whatsapp", "34600333444@s.whatsapp.net") == "as the platform said", "two rows, one number"
    assert _named(d, "whatsapp", "9@g.us") == "as the platform said", "no contact is a group chat"
    assert _named(d, "whatsapp", "7@lid") == "as the platform said", "a hidden row names nobody"
    assert _named(d, "telegram", "111@lid") == "as the platform said", "another platform's conversation"
    assert _named(d, "whatsapp", "nobody@lid", "") == "nobody", "the bare id last"


def test_the_index_and_a_walk_of_the_directory_name_the_same(directory):
    d = directory
    rows = [("whatsapp", "111@lid"), ("email", "ROWAN@example.com"), ("whatsapp", "34600111222@s.whatsapp.net"),
            ("whatsapp", "34600333444@s.whatsapp.net"), ("whatsapp", "+34 600 111 222"), ("telegram", "600111222"),
            ("whatsapp", "222@s.whatsapp.net"), ("email", "x@example.com")]
    people = d.cd.visible(d.cd.load_db())
    for p, cid in rows:
        hits = {id(c): c for c in people if c.get("kind") != "group" and (
            any(d._norm(ch.get("platform")) == p and str(ch.get("chatId") or "") == cid for ch in c.get("channels") or [])
        )}
        if len(hits) != 1 and p == "email":
            hits = {id(c): c for c in people if any(d._norm(a) == d._norm(cid) for a in d._emails(c))}
        if len(hits) != 1 and d._phone_of(p, cid):
            hits = {id(c): c for c in people if any(d._same_phone(d._phone_of(p, cid), t) for t in d._phones(c))}
        want = next(iter(hits.values()))["name"] if len(hits) == 1 else "?"
        assert _named(d, p, cid, "?") == want, (p, cid)


def test_an_unchanged_directory_is_read_once_for_every_view(directory):
    for _ in range(5):
        assert _named(directory, "whatsapp", "111@lid") == "Quinn Ferrer"
    assert directory.reads["n"] == 1, "five views, one read of the store"


def test_a_write_is_seen_by_the_next_view(directory, stores):
    d = directory
    assert _named(d, "whatsapp", "555@lid") == "as the platform said"
    db = stores.load(d.cd.WIDGET_ID)
    db["contacts"].append({"id": "n", "kind": "person", "name": "Uma Soler",
                           "channels": [{"platform": "whatsapp", "chatId": "555@lid"}]})
    stores.save(d.cd.WIDGET_ID, db)
    assert _named(d, "whatsapp", "555@lid") == "Uma Soler"


def test_a_write_by_another_process_is_seen_too(directory, stores):
    d = directory
    assert _named(d, "whatsapp", "111@lid") == "Quinn Ferrer"
    path = os.path.join(stores.data_dir(d.cd.WIDGET_ID), "state.json")
    with open(path, encoding="utf-8") as f:
        db = json.load(f)
    next(c for c in db["contacts"] if c.get("id") == "a")["name"] = "Quinn Renamed"
    before = os.stat(path).st_mtime_ns
    with open(path, "w", encoding="utf-8") as f:          # not through `store.save`: this process counted no change
        json.dump(db, f)
    os.utime(path, ns=(before + 10**9, before + 10**9))
    assert _named(d, "whatsapp", "111@lid") == "Quinn Renamed"


def test_people_handed_in_are_indexed_as_given_and_never_remembered(directory):
    d = directory
    mine = [{"name": "Only Mine", "channels": [{"platform": "telegram", "chatId": "42"}]}]
    assert d.namer(mine)("telegram", "42")["name"] == "Only Mine"
    assert d.namer()("telegram", "42", "from the store")["name"] == "from the store"

"""The bridge tells who a @lid is and when a name changes — and the directory hears it without an import.

WhatsApp addresses most 1:1 chats by a linked id with no number; the phone rides on every message key
(`remoteJidAlt` / `participantAlt`) and is the only key that recognises the same person in the address book.
A rename on the phone used to reach the directory only when he pressed «import» again.
"""
import asyncio
import pathlib
import re
import shutil
import subprocess

import pytest

from connectors.messaging import contacts_bus
from connectors.whatsapp import client
from connectors.whatsapp.service import directory

BRIDGE = pathlib.Path("connectors/whatsapp/bridge/bridge.js")


# --- _wa_person: which name it is, and the others he is known by -------------------------------------------

def test_a_saved_name_keeps_the_nickname_as_another_name():
    p = directory._wa_person({"id": "100000000000473@lid", "name": "Odile Varga", "notify": "Odi ✨",
                              "phoneNumber": "34600000311"})
    assert p["name"] == "Odile Varga" and p["nameKind"] == "saved"
    assert p["knownAs"] == ["Odi ✨"]
    assert p["phone"] == "+34600000311"


def test_a_nickname_only_is_the_persons_own_name_and_repeats_are_not_other_names():
    p = directory._wa_person({"id": "100000000000746@lid", "notify": "Tomas Brandt",
                              "verifiedName": "  tomas   BRANDT "})
    assert p["nameKind"] == "self"
    assert p["knownAs"] == [], "the same name in other case/spacing is not another name"
    assert p["phone"] == "", "a @lid without phoneNumber is never a phone"


def test_a_number_only_says_so():
    p = directory._wa_person({"id": "34600000311@s.whatsapp.net"})
    assert p["name"] == "+34600000311" and p["nameKind"] == "number" and p["knownAs"] == []


# --- _drain_contact_changes: pushes what changed, every 60 s, walking the cursor -----------------------------

@pytest.fixture
def bridge(monkeypatch):
    calls, answers = [], []

    async def fake_get_contacts(since=None):
        calls.append(since)
        return answers.pop(0) if answers else {"contacts": [], "now": 0}

    monkeypatch.setattr(client, "get_contacts", fake_get_contacts)
    monkeypatch.setattr(directory, "_changes_at", 0.0)
    monkeypatch.setattr(directory, "_changes_since", None)
    contacts_bus.take_pushed()
    yield calls, answers
    contacts_bus.take_pushed()


def test_changes_are_pushed_spaced_and_the_cursor_advances(bridge, monkeypatch):
    calls, answers = bridge
    answers += [{"contacts": [{"id": "100000000000747@lid", "notify": "Ines Halloran"}], "now": 1_000.0},
                {"contacts": [], "now": 2_000.0}]
    asyncio.run(directory._drain_contact_changes())
    assert calls == [0], "the first pass takes the whole book"
    pushed = contacts_bus.take_pushed()
    assert [r["name"] for r in pushed["whatsapp"]] == ["Ines Halloran"]

    asyncio.run(directory._drain_contact_changes())
    assert calls == [0], "asked again before CHANGES_EVERY_S"

    monkeypatch.setattr(directory, "_changes_at", 0.0)
    asyncio.run(directory._drain_contact_changes())
    assert calls == [0, 1_000.0], "the next pass starts at the previous answer's `now`"
    assert contacts_bus.take_pushed() == {}, "nothing changed, nothing pushed"
    assert directory._changes_since == 2_000.0


def test_a_bridge_that_fails_does_not_raise(bridge, monkeypatch):
    async def boom(since=None):
        raise RuntimeError("bridge down")

    monkeypatch.setattr(client, "get_contacts", boom)
    asyncio.run(directory._drain_contact_changes())
    assert contacts_bus.take_pushed() == {}


# --- contacts_bus.push / take_pushed ------------------------------------------------------------------------

def test_push_and_take_round_trip_and_the_buffer_is_bounded():
    contacts_bus.take_pushed()
    contacts_bus.push("WhatsApp", [{"name": "Odile Varga"}])
    contacts_bus.push("telegram", [{"name": "Tomas Brandt"}, "not a row"])
    got = contacts_bus.take_pushed()
    assert got == {"whatsapp": [{"name": "Odile Varga"}], "telegram": [{"name": "Tomas Brandt"}]}
    assert contacts_bus.take_pushed() == {}, "a take empties the buffer"

    contacts_bus.push("whatsapp", [{"n": i} for i in range(contacts_bus.PUSH_MAX + 7)])
    rows = contacts_bus.take_pushed()["whatsapp"]
    assert len(rows) == contacts_bus.PUSH_MAX and rows[-1] == {"n": contacts_bus.PUSH_MAX + 6}, "newest kept"
    contacts_bus.push("", None)  # never raises
    assert contacts_bus.take_pushed() == {}


# --- bridge.js: the wiring exists, and the file parses ------------------------------------------------------

def test_the_bridge_learns_the_phone_behind_a_lid_and_stamps_changes():
    src = re.sub(r"//[^\n]*", "", BRIDGE.read_text(encoding="utf-8"))
    for needle in ("function learnPn", "remoteJidAlt", "participantAlt", "'lid-mapping.update'",
                   "zaelar-contacts.json", "req.query.since", "now: Date.now()", "updatedAt = Date.now()",
                   "getPNForLID"):
        assert needle in src, needle


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_the_bridge_parses():
    r = subprocess.run(["node", "--check", str(BRIDGE)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

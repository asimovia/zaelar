"""The words that left are his, or they are said (INI-071 B4, 2026-11-16).

Measured on the local engine: he dictated a text word for word («…: te debo $50»), the turn's call carried another
(«te debes $50»), the act's end state was rendered from the call's text, the echo of THAT text landed, and the row was
said «sent, checked». The check was true — of the words the turn wrote, not of the ones he said.

The class: what leaves in his name is his words, in order (`send_task.his_text`, the reading every send door already
uses), or the receipt SAYS the words that left. Nothing classifies his sentence as a dictation: the act's declared
`composed` slot (`exit_slots.declared`) is read against his words at the echo, and a text that is not a run of them is
named in the fact the mouth composes its line from (`circuit.SENT` + the words). His own words leave the fact as it was.

Variants: Spanish via `reply`, English via `send_to`, and his own words (no change said).
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb
from nucleo import circuit
from nucleo.circuit import spec
from nucleo.request import model as rq


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db()
    memdb.get_db()
    spec.reset()
    from widgets import rows as R
    sent: list[dict] = []
    monkeypatch.setattr(R, "declared", lambda wid: {"sent": {"id": "id", "from": "view"},
                                                    "outbox": {"id": "ref", "from": "view"}} if wid == "mensajeria" else {})
    monkeypatch.setattr(R, "_rows", lambda wid, coll: [r for r in sent if r["coll"] == coll] if wid == "mensajeria" else [])
    from nucleo.workers import spoken_delivery
    from voice import proactive
    facts: list = []

    async def line(goal, fact, **k):
        facts.append((fact, k.get("verdict")))
        return "ok"

    async def notify(*_a, **_k):
        return True
    monkeypatch.setattr(spoken_delivery, "line", line)
    monkeypatch.setattr(proactive, "notify", notify)
    yield sent, facts
    spec.reset()
    memdb.reset_db()


def _echo(world, said: str, action: str, payload: dict, landed: dict) -> list:
    sent, facts = world

    async def run():
        rq.begin(said)
        e = spec.open_for_action("mensajeria", action, payload, text=said)
        assert e is not None, "the act declares no end state"
        e["row"], e["turn"] = rq.opened("mensajeria", action), rq.current()
        sent.append(landed)
        circuit.tick(now=float(e["born"]) + circuit.CHECK_EVERY_S + 1)
        await asyncio.sleep(0.05)
    asyncio.run(run())
    return facts


def test_a_reply_whose_words_are_not_his_says_the_words_that_left(world):
    said = "contesta a Ana en el primero: te debo $50"
    facts = _echo(world, said, "reply", {"n": 1, "text": "te debes $50"},
                  {"coll": "sent", "id": "e1", "body": "te debes $50", "name": "Ana", "queued": False})
    assert len(facts) == 1 and facts[0][1] == "met"
    assert facts[0][0].startswith(circuit.SENT) and "«te debes $50»" in facts[0][0], \
        "the words that left were not his and the receipt said only «sent»"


def test_a_send_in_english_whose_words_are_not_his_says_them(world):
    said = "text Rowan exactly this: I owe you twenty quid"
    facts = _echo(world, said, "send_to", {"contact": "Rowan", "text": "You owe me twenty quid"},
                  {"coll": "outbox", "ref": "r1", "name": "Rowan", "platform": "whatsapp", "state": "sent", "kind": "dm"})
    assert len(facts) == 1 and "«You owe me twenty quid»" in facts[0][0]


def test_his_own_words_leave_the_receipt_as_it_was(world):
    said = "contesta a Ana en el primero: te debo $50"
    facts = _echo(world, said, "reply", {"n": 1, "text": "Te debo $50."},
                  {"coll": "sent", "id": "e2", "body": "Te debo $50.", "name": "Ana", "queued": False})
    assert facts == [(circuit.SENT, "met")]


def test_the_reading_is_the_send_doors_own_and_the_slot_is_declared():
    from nucleo.request import send_task
    from nucleo.workers import exit_slots
    assert exit_slots.declared("mensajeria", "reply")["text"]["from"] == "composed"
    assert exit_slots.words_not_his("mensajeria", "reply", {"text": "te debes $50"}, "…: te debo $50") == "te debes $50"
    assert exit_slots.words_not_his("mensajeria", "reply", {"text": "te debo $50"}, "…: te debo $50") == ""
    assert send_task.his_text("te debo $50", "…: te debo $50")


def test_a_yes_to_a_draft_never_reads_as_words_that_are_not_his(world):
    """He dictated the text a turn earlier and this turn only says «yes»: the text is not a run of THIS sentence, and
    that is all the fact may say — the words are named, never called not his. A long body is named by its start."""
    body = "Te debo $50. " + "Gracias por adelantarlo el otro día, de verdad. " * 12
    facts = _echo(world, "sí, envíalo", "reply", {"n": 1, "text": body},
                  {"coll": "sent", "id": "e3", "body": body, "name": "Ana", "queued": False})
    fact = facts[0][0]
    assert "«Te debo $50." in fact and "no son las que él dijo" not in fact
    assert len(fact) < len(circuit.SENT) + circuit.SENT_TEXT_MAX + 120 and "…»" in fact

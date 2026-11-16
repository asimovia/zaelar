"""What runs AROUND a group of his people is said right (isolated-engine replay over 2.1776, 8 scenarios).

A — a call another card's act served (`mensajeria:create_group` → `contactos:create_group`) is not said «not done»:
    the turn's words come from the act that RAN.
B — our clarifying question between cards («¿mensajería o contactos?») is not a send task of `send_to`.
D — the group's answer names whom it put in (the receipt reads `title` and `added`).
E — a channel the call names that is not connected is said in the turn, the row ends `cannot`, nothing is promised.
F — «añade a la lista de la compra leche y pan»: `add_list` takes `items`, they land in the list, and the act declares
    its end state.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.request import send_task, send_task_words
from widgets.contract import would_refuse as _REAL_WOULD_REFUSE     # before the fixture stubs it
from tests.agent_headless.unit.turn.test_a_send_is_commissioned_by_the_verdict import (  # noqa: F401 — fixture
    _asks, _brief, _rows, _say, world)


def test_a_call_another_card_served_is_not_said_undone(monkeypatch):
    from nucleo.turn import rerouted, unserved
    monkeypatch.setattr("nucleo.turn.reply._trace", lambda: "t-A")
    call = [{"name": "widget_data", "args": {"widget_id": "mensajeria", "action": "create_group"}}]
    assert unserved.calls_not_run(call, []) == [("mensajeria", "create_group")], "RED proof: unserved without the note"
    rerouted.note("mensajeria", "create_group")
    assert unserved.calls_not_run(call, []) == [], "the twin served it: its card answers for it"


def test_a_question_between_cards_is_not_a_send_task(world):
    said = "crea un grupo"
    _say(said)
    brief = _brief(screen_action=("contactos:create_group", 0.6))
    assert send_task_words.hold("mensajeria", ["create_group", "send_to"], said, "¿En mensajería o en contactos?",
                                brief=brief) == ""
    assert not [r for r in _rows() if "send_to" in str(r.get("title") or r.get("goal") or "")]


def test_a_question_about_this_cards_act_asks_on_that_act_not_the_primary_send(world):
    said = "crea un grupo"
    _say(said)
    brief = _brief(screen_action=("mensajeria:create_group", 0.5))
    send_task_words.hold("mensajeria", ["create_group", "send_to"], said, "¿Con quién?", brief=brief)
    acts = [send_task.artefact(str(r["id"])).get("action") for r in _rows()]
    assert acts == ["create_group"], acts        # the act the reading named, never the card's primary `send_to`


def test_the_groups_answer_names_whom_it_put_in(world):
    from widgets.contactos import data as cd
    from widgets.server_api import brain_action
    from nucleo.turn import reply
    for n in ("Ana", "Ana García", "Luis Mora"):
        cd.apply_action("add_contact", {"name": n, "phone": "+34600000001"})
    res = asyncio.run(brain_action("contactos", "create_group", {"name": "cena", "contactIds": ["Ana", "Luis"]}))
    said = reply.object_of(res)
    assert "«Ana»" in said and "«Luis Mora»" in said and "García" not in said, said


def test_a_channel_that_is_down_is_said_in_the_turn_and_nothing_is_promised(world, monkeypatch):
    from widgets import contract
    from widgets.mensajeria.outbound import targets
    monkeypatch.setattr(contract, "would_refuse", _REAL_WOULD_REFUSE)
    monkeypatch.setattr(targets, "connected_platforms", lambda db=None: set())     # known: nothing connected
    said = "mándale un WhatsApp a Quinn diciendo que llego tarde"
    _say(said)
    uid = send_task.commission("mensajeria", "send_to", {"contact": "Quinn Gold", "text": "llego tarde",
                                                         "channel": "whatsapp"}, said, emit=world["emit"])
    from memory import tasks_store as ts
    row = ts.task_get(uid)
    assert row["state"] in ("failed", "cancelled", "done") and "WhatsApp" in str(row.get("outcome") or ""), row
    assert world["sent"] == [], "nothing queued"


def test_disarmed_without_the_cards_dry_reading_the_send_is_queued(world, monkeypatch):
    from widgets import contract
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)
    said = "mándale un WhatsApp a Quinn diciendo que llego tarde"
    _say(said)
    send_task.commission("mensajeria", "send_to", {"contact": "Quinn Gold", "text": "llego tarde",
                                                   "channel": "whatsapp"}, said, emit=world["emit"])
    assert world["sent"], "RED proof: with no dry reading the send goes on"


def test_items_land_in_the_list_and_the_act_declares_its_end_state(world):
    from nucleo.circuit import spec
    from widgets.agenda import data as agenda
    from widgets.server_api import brain_action
    res = asyncio.run(brain_action("agenda", "add_list", {"name": "la compra", "items": ["leche", "pan"]}))
    assert res.get("added") == ["leche", "pan"], res
    db = agenda.load_db()
    lid = res.get("list") or (res.get("result") or {}).get("list")
    titles = [t.get("title") for t in db.get("tasks", []) if str(t.get("list") or t.get("listId") or "") == str(lid)]
    assert {"leche", "pan"} <= set(titles), (lid, titles)
    assert spec.template_of("agenda", "add_list"), "a declared end state: «done» only with its check"

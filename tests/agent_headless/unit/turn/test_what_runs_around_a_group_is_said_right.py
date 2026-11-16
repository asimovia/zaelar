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


# ── replay over 65c0f7e63 ────────────────────────────────────────────────────────────────────────────────────────
def _people(world):
    from widgets.contactos import data as cd
    for n in ("Ana Ruiz", "Luis Mora", "Marta Gil"):
        cd.apply_action("add_contact", {"name": n, "phone": "+34600000002"})


def test_a_group_asked_with_members_under_their_synonym_gets_them_through_the_real_door(world):
    """`contactos:create_group {members: [...]}` made an EMPTY group judged `met`: `members` is a declared synonym."""
    from widgets.server_api import brain_action
    _people(world)
    res = asyncio.run(brain_action("contactos", "create_group", {"name": "cena", "members": ["Ana", "Luis"]}))
    assert res.get("added") == ["Ana Ruiz", "Luis Mora"], res


def test_an_empty_group_where_people_were_named_is_not_met(world):
    from nucleo.circuit import spec, verify
    from widgets.contactos import data as cd
    _people(world)
    cd.apply_action("create_group", {"name": "vacío"})                       # the group exists, nobody in it
    unmet = spec.render("contactos", "create_group", {"name": "vacío", "members": ["Ana"]})
    assert verify.check(unmet) is False, "a group asked WITH people and holding none is not done"
    cd.apply_action("create_group", {"name": "lleno", "contactIds": ["Ana"]})
    assert verify.check(spec.render("contactos", "create_group", {"name": "lleno", "members": ["Ana"]})) is True
    assert verify.check(spec.render("contactos", "create_group", {"name": "vacío"})) is True, "asked with nobody"


def test_disarmed_without_the_synonym_the_group_is_made_empty(world, monkeypatch):
    from widgets import contract
    monkeypatch.setitem(contract._ALIASES, "contactIds", ())
    from widgets.server_api import brain_action
    _people(world)
    res = asyncio.run(brain_action("contactos", "create_group", {"name": "cena2", "members": ["Ana", "Luis"]}))
    assert res.get("added") == [], "RED proof: `members` unread, nobody added"


@pytest.mark.parametrize("said,twin", [("se llama Pádel, con Marta y Luis", True),
                                       ("crea un grupo de WhatsApp familia con Ana", False),
                                       ("hazme un grupo de telegram con Luis", False)])
def test_with_his_words_naming_no_channel_the_group_is_of_his_contacts(said, twin):
    from nucleo.request import channel_twin
    got = channel_twin.twin("mensajeria", "create_group", {"members": ["Marta", "Luis"], "name": "Pádel"},
                            {"result": {}}, said)
    assert bool(got) is twin, got


def test_our_clarifying_question_closes_when_the_act_it_asked_about_runs(world, monkeypatch):
    from nucleo.request import ask_outside_door, clarified
    from nucleo.turn import brief_turn
    from memory import tasks_store as ts
    monkeypatch.setattr(brief_turn, "of_this_turn", lambda: _brief(screen_action=("contactos:create_group", 0.6)))
    _say("crea un grupo")
    ask = ask_outside_door.held({"widget": "mensajeria", "leaves": ["create_group"], "actions": ["create_group"]},
                                "¿Un grupo de contactos o de mensajería?", "crea un grupo")
    assert ask
    rows = [r for r in _rows() if r.get("state") == "waiting"]
    assert clarified.answered("mensajeria", "contactos") == 1
    assert ts.task_get(str(rows[0]["id"]))["state"] == "done"


def test_a_task_for_a_list_he_names_that_does_not_exist_makes_it_and_loses_nothing(world):
    from widgets.agenda import data as agenda
    from widgets.server_api import brain_action
    a = asyncio.run(brain_action("agenda", "add_task", {"title": "Leche", "list": "Compra"}))
    b = asyncio.run(brain_action("agenda", "add_task", {"title": "Pan", "list": "Compra"}))
    assert a.get("list_created") and a.get("ok") is not False and b.get("ok") is not False, (a, b)
    db = agenda.load_db()
    lid = a["list"]
    assert {t["title"] for t in db.get("tasks", []) if t.get("listId") == lid} == {"Leche", "Pan"}
    assert asyncio.run(brain_action("agenda", "add_task", {"title": "x", "list": "7"})).get("ok") is False, \
        "a list NUMBER that does not exist is never made"


def test_a_draft_declares_its_end_state():
    from nucleo.circuit import spec
    assert spec.render("mensajeria", "draft", {"text": "llego tarde", "contact": "Ana"}), "«done» only with its check"

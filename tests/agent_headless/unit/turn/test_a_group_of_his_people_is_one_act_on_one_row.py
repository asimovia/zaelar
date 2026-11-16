"""«crea un grupo cena con Ana y Luis»: a list of people is a filled slot, his answer fills the SAME row, a group with no
channel named is his contacts' group, and two errands of one turn are never folded together.

Measured on an isolated engine (v3.160, real workers): the turn called `mensajeria:create_group` with
`members: ["Ana", "Luis"]`, the send task read the list as an EMPTY slot (`has = isinstance(v, str)`) and asked «to
whom?»; his answer «con Ana y Luis» got the same question again and a second row opened; with no channel named the
act was a WhatsApp group, impossible with the channels off; «… y búscame un restaurante italiano» was folded into the
group's errand by the dispatcher's dedup and one worker got both. Each is now one mechanism, declared by the cards.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.request import send_task, send_task_answer
from tests.agent_headless.unit.turn.test_a_send_is_commissioned_by_the_verdict import (  # noqa: F401 — fixture
    _asks, _rows, _say, world)

SAID = "crea un grupo cena con Ana y Luis por WhatsApp"


@pytest.fixture
def people(world):
    from widgets.contactos import data as cd
    for name in ("Ana Ruiz", "Luis Mora", "Marta Gil"):
        cd.apply_action("add_contact", {"name": name, "phone": "+34600000000"})
    return world


@pytest.mark.parametrize("members", [["Ana", "Luis"], ("Ana",), ["Ana Ruiz", "Luis"]])
def test_a_list_of_people_is_a_filled_slot(people, members):
    _say(SAID)
    got = send_task.sources("mensajeria", "create_group", {"members": members, "platform": "whatsapp",
                                                           "name": "cena"}, SAID)
    assert got["recipient"]["source"] == "his", got


def test_the_group_asks_no_question_for_its_optional_first_message(people):
    _say(SAID)
    uid = send_task.retain("mensajeria", "create_group", {"members": ["Ana", "Luis"], "platform": "whatsapp",
                                                          "name": "cena"}, SAID)
    assert send_task.missing(send_task.artefact(uid)) == ("", ""), "`text` is declared optional: never asked"


def test_disarmed_a_list_read_as_text_is_an_empty_slot(people, monkeypatch):
    """RED proof: the pre-fix reading (only a non-blank str is a value) asks «to whom?» for a full list."""
    monkeypatch.setattr(send_task, "filled", lambda v: isinstance(v, str) and bool(v.strip()))
    _say(SAID)
    got = send_task.sources("mensajeria", "create_group", {"members": ["Ana", "Luis"]}, SAID)
    assert got["recipient"]["source"] == "none"


def test_his_answer_fills_the_same_row_and_opens_no_other(people):
    """«crea un grupo» → one question → «se llama Pádel, con Marta y Luis»: the answering turn's call fills it."""
    _say("crea un grupo por WhatsApp")
    uid = send_task.commission("mensajeria", "create_group", {"platform": "whatsapp"}, "crea un grupo por WhatsApp")
    assert uid and send_task.missing(send_task.artefact(uid))[0] == "recipient"
    before = len(_rows())
    answer = "se llama Pádel, con Marta y Luis"
    _say(answer)
    got = send_task_answer.take_call("mensajeria", "create_group",
                                     {"members": ["Marta", "Luis"], "name": "Pádel", "platform": "whatsapp"}, answer)
    assert got == uid, "the waiting row took the call"
    art = send_task.artefact(uid)
    assert art["payload"]["members"] == ["Marta", "Luis"] and send_task.missing(art) == ("", "")
    assert len(_rows()) == before, "no second row"


def test_with_no_channel_named_the_group_is_his_contacts_group(people):
    from nucleo.request import channel_twin
    to = channel_twin.twin("mensajeria", "create_group", {"members": ["Ana", "Luis"], "name": "cena"}, None)
    assert to == ("contactos", "create_group", {"contactIds": ["Ana", "Luis"], "name": "cena"})
    assert channel_twin.twin("mensajeria", "create_group",
                             {"members": ["Ana"], "name": "cena", "platform": "whatsapp"}, None) is None, \
        "he named the channel: the leaving act"


def test_the_twin_creates_the_group_with_his_people_through_the_real_card(people):
    from widgets.server_api import brain_action
    from nucleo.request import channel_twin
    wid, act, payload = channel_twin.twin("mensajeria", "create_group", {"members": ["Ana", "Luis"], "name": "cena"},
                                          None)
    res = asyncio.run(brain_action(wid, act, payload))
    added = (res.get("result") or res).get("added") or []
    assert len(added) == 2, res


def _two_parts(monkeypatch, part):
    """The real listener (`dispatch.run_listener`): a live errand, then an escalation that would dedup into it."""
    import bus
    from nucleo import dispatch
    from nucleo.acts import errand as escalate
    from nucleo.workers.session import SessionRecord
    from tests.agent_headless.unit.test_dispatch import _FakeBackend
    monkeypatch.setattr(dispatch, "get_backend", lambda *a, **k: _FakeBackend())
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    injected: list = []

    async def _fake_inject(which, msg):
        injected.append((which, msg))
        return [which]
    monkeypatch.setattr(dispatch, "inject", _fake_inject)
    goal = "busca un restaurante italiano en Barcelona para cenar el viernes con terraza"

    async def run():
        bus.reset()
        escalate.reset()
        dispatch._SESSIONS["live"] = SessionRecord(task_id="live", kind="web", status="running", goal=goal)
        stop = asyncio.Event()
        task = asyncio.create_task(dispatch.run_listener(stop))
        await asyncio.sleep(0.05)
        escalate.escalate_to_slowbrain(goal + " por favor", context={"kind": "web", **({"part": 1} if part else {})})
        await asyncio.sleep(0.2)
        stop.set()
        await asyncio.sleep(0.05)
        task.cancel()
    asyncio.run(run())
    return injected


def test_two_errands_of_one_turn_are_never_folded_together(fresh_db, monkeypatch):
    """Through the real listener: one of several errands of his turn (`part`) is its own errand, never a refinement
    folded into another live one — and without `part` the same words still fold (the dedup is untouched)."""
    assert _two_parts(monkeypatch, part=True) == [], "a part of the turn was folded into another errand"
    assert _two_parts(monkeypatch, part=False), "RED proof: without `part` the dedup folds it"


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from memory import db as memdb
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "z.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()

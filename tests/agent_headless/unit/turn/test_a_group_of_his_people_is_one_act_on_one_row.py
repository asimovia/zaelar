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
#: The turn's reading SAYS no channel (its `message_channel` verdict landed `none`): the only case the twin runs.
_NONE = {"result": {"message_channel": {"choice": "none", "confidence": 0.9}}}


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
    monkeypatch.setattr(send_task, "filled", lambda v, many=False: isinstance(v, str) and bool(v.strip()))
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
    to = channel_twin.twin("mensajeria", "create_group", {"members": ["Ana", "Luis"], "name": "cena"}, _NONE)
    assert to == ("contactos", "create_group", {"contactIds": ["Ana", "Luis"], "name": "cena"})


def test_the_twin_creates_the_group_with_his_people_through_the_real_card(people):
    from widgets.server_api import brain_action
    from nucleo.request import channel_twin
    wid, act, payload = channel_twin.twin("mensajeria", "create_group", {"members": ["Ana", "Luis"], "name": "cena"},
                                          _NONE)
    res = asyncio.run(brain_action(wid, act, payload))
    added = (res.get("result") or res).get("added") or []
    assert len(added) == 2, res


def _two_parts(monkeypatch, part, turn="turn-A"):
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
        live = SessionRecord(task_id="live", kind="web", status="running", goal=goal)
        live.reading = {"turn_id": "turn-A"}
        dispatch._SESSIONS["live"] = live
        stop = asyncio.Event()
        task = asyncio.create_task(dispatch.run_listener(stop))
        await asyncio.sleep(0.05)
        escalate.escalate_to_slowbrain(goal + " por favor", context={"kind": "web", "reading": {"turn_id": turn},
                                                                    **({"part": 1} if part else {})})
        await asyncio.sleep(0.2)
        stop.set()
        await asyncio.sleep(0.05)
        task.cancel()
    asyncio.run(run())
    return injected


def test_two_errands_of_one_turn_are_never_folded_together(fresh_db, monkeypatch):
    """Through the real listener: one of several errands of his turn (`part`) is its own errand, never a refinement
    folded into another live one — and without `part` the same words still fold (the dedup is untouched)."""
    assert _two_parts(monkeypatch, part=True) == [], "a part was folded into a SIBLING of its own turn"
    assert _two_parts(monkeypatch, part=True, turn="turn-B"), "an earlier turn's errand still takes its repetition"
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


# ── audit of 2.1776 ──────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("payload,reading", [
    ({"members": ["Ana"], "name": "x", "channel": "whatsapp"}, _NONE),          # a synonym of the channel slot
    ({"members": ["Ana"], "name": "x", "platform": "telegram"}, _NONE),
    ({"members": ["Ana"], "name": "x"}, {"result": {"message_channel": {"choice": "whatsapp", "confidence": 0.25}}}),
    ({"members": ["Ana"], "name": "x"}, {"result": {}}),                          # the reading does not say
    ({"members": ["Ana"], "name": "x"}, None),                                     # no reading at all
    ({"members": ["Ana"], "name": "x", "text": "hola a todos"}, _NONE),            # a first message: a chat group
])
def test_any_sign_of_a_channel_keeps_the_leaving_act(payload, reading):
    from nucleo.request import channel_twin
    assert channel_twin.twin("mensajeria", "create_group", payload, reading) is None


@pytest.mark.parametrize("payload", [
    {"contact": "Quinn Gold", "text": ["hola"]}, {"contact": "Quinn Gold", "text": False},
    {"contact": "Quinn Gold", "text": {}}, {"contact": "Quinn Gold", "text": 0},
    {"contact": [{}], "text": "hola"}, {"contact": ["Quinn Gold", "Test Test"], "text": "hola"},   # one person {"contact": {"name": "Quinn"}, "text": "hola"}, {"contact": 123, "text": "hola"},
])
def test_a_value_of_the_wrong_kind_is_asked_never_sent(people, payload):
    """Audit B2: a list where TEXT is expected went out as «['hola']». Only a slot of people takes a list."""
    said = "manda hola a Quinn"
    _say(said)
    uid = send_task.commission("mensajeria", "send_to", payload, said, emit=people["emit"])
    assert uid and send_task.missing(send_task.artefact(uid))[0], payload
    assert people["sent"] == [] and _asks(people), "asked, not sent"


def test_an_optional_field_the_end_state_names_is_still_asked(people):
    """Audit B1: «envíalo» over a draft — `contact` is declared optional, but `send_draft`'s end state names it."""
    _say("envíalo")
    uid = send_task.commission("mensajeria", "send_draft", {}, "envíalo", emit=people["emit"])
    assert send_task.missing(send_task.artefact(uid))[1] == "contact" and _asks(people)
    from memory import tasks_store as ts
    assert ts.task_get(uid)["state"] == "waiting", "a question on the row, never a failed row"


def test_a_channel_group_closes_checkpoint_one_by_its_declared_unreadable_end(people):
    """Audit 4: `create_group` declares `done_when_unreadable`; its send row is not refused at checkpoint 1."""
    from nucleo.request import send_task_run
    from nucleo.workers.prompts import playbook
    _say(SAID)
    uid = send_task.retain("mensajeria", "create_group", {"members": ["Ana", "Luis"], "platform": "whatsapp",
                                                          "name": "cena"}, SAID)
    rec = send_task_run._rec(uid, send_task.artefact(uid))
    assert rec.unreadable_end and playbook.checkpoint_one(rec) == ""


@pytest.mark.parametrize("members,unresolved", [(["Ana", "Luis"], ["Ana"]), (["Pepe"], ["Pepe"]),
                                                ("Luis y Marta", ["Luis y Marta"])])
def test_a_member_who_cannot_be_found_is_named_and_no_group_is_made(people, members, unresolved):
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Ana Sanz", "phone": "+34611111111"})     # a second Ana
    from widgets.server_api import brain_action
    res = asyncio.run(brain_action("contactos", "create_group", {"name": "cena", "contactIds": members}))
    assert res.get("ok") is False and res.get("names") == unresolved, res
    assert not any(g.get("name") == "cena" for g in cd.load_db().get("groups", []) if isinstance(g, dict))


def test_a_name_without_its_accent_or_with_a_full_stop_is_found(people):
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "José Pérez", "phone": "+34622222222"})
    from widgets.server_api import brain_action
    res = asyncio.run(brain_action("contactos", "create_group", {"name": "obra", "contactIds": ["jose", "Marta."]}))
    assert len((res.get("result") or res).get("added") or []) == 2, res


def _turn_call(monkeypatch, brief, text="crea un grupo cena con Ana y Luis"):
    """The turn's real data-op door (`tool_executor_widget_calls._apply_widget_data`) with the card licence open."""
    from types import SimpleNamespace

    from nucleo.acts import card
    from nucleo.flash import tool_executor_widget_calls as tx
    monkeypatch.setattr(card, "licence", lambda *a, **k: SimpleNamespace(verdict=card.RUN, card="", why=""))
    monkeypatch.setattr(card, "logged", lambda lic, emit: lic)
    monkeypatch.setattr(tx, "_verdict_instead", lambda *a, **k: False)
    ran, tasks = [], []
    monkeypatch.setattr(tx, "_leaving_is_a_task", lambda *a, **k: tasks.append(a[:2]) or True)
    tx._apply_widget_data("mensajeria", "create_group", {"members": ["Ana", "Luis"], "name": "cena"},
                          _apply_widget_data=lambda w, a, p: ran.append((w, a, p)), _brief=brief, _frontend=None,
                          _request_data_confirm=None, _spawn=None, _tag_emit=lambda *a, **k: None, _turn_op_tasks=[],
                          acted={}, brain=SimpleNamespace(), data_done={}, deduped={}, emit=lambda *a, **k: None,
                          escalate_req={"v": None}, text=text)
    return ran, tasks


def test_the_turn_door_runs_the_twin_only_when_no_channel_is_named(monkeypatch):
    ran, tasks = _turn_call(monkeypatch, _NONE)
    assert ran == [("contactos", "create_group", {"contactIds": ["Ana", "Luis"], "name": "cena"})] and not tasks
    ran, tasks = _turn_call(monkeypatch, None, text="crea un grupo de WhatsApp cena con Ana y Luis")
    assert not ran and tasks, "he named the channel: the leaving act keeps its route"
    ran, tasks = _turn_call(monkeypatch, None)
    assert ran and not tasks, "no channel named anywhere: the group is of his contacts"


def test_disarmed_without_the_twin_the_group_goes_to_messaging(monkeypatch):
    from nucleo.request import channel_twin
    monkeypatch.setattr(channel_twin, "twin", lambda *a, **k: None)
    ran, tasks = _turn_call(monkeypatch, _NONE)
    assert not ran and tasks


def test_a_removal_by_name_takes_out_only_who_it_names(people):
    """`add_to_group` shares the name resolution: `remove: true` with a name takes out that member and nobody else."""
    from widgets.server_api import brain_action
    made = asyncio.run(brain_action("contactos", "create_group", {"name": "cena", "contactIds": ["Ana", "Luis"]}))
    gid = str(((made.get("result") or made).get("group") or {}).get("id") or "cena")
    out = asyncio.run(brain_action("contactos", "add_to_group", {"groupId": gid, "contactIds": ["Luis"], "remove": True}))
    assert out.get("ok") is not False, out
    from widgets.contactos import data as cd
    db = cd.load_db()
    members = [c["name"] for c in db.get("contacts", []) if any(str(g) in (gid, "cena")
               for g in (c.get("groups") or []))]
    assert "Ana Ruiz" in members and "Luis Mora" not in members, members

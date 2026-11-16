"""A list field and a channel field keep the shape and the key their action DECLARES through every question (V2-919).

Found by the audit of V2-919 (executed probes, 2026-11-16):
  · a «which one?» asked about ONE name of a list of people replaced the WHOLE list with the answer: with two people
    called Raquel in his directory, `members: [Raquel Salinas, Marta Ruiz]` asked «which Raquel?» and the group left
    with Raquel alone. «Which one?» belongs to a field of one person; a declared list's ambiguity is the widget's to
    refuse (with its reason), and an answer never replaces a list that already has people;
  · «which channel?» was asked and answered under the literal key `channel` while the action declares its channel
    under another key (`platform`): the payload carried both, and the act left by the channel he did NOT choose.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb, embeddings as mememb
from nucleo import his_words, untrusted
from nucleo.circuit import asker
from nucleo.request import inline_ask, model, send_task, send_task_answer, send_task_run

WID = "mensajeria"
READING = {"result": {"message_channel": {"choice": "whatsapp", "confidence": 0.97}}, "open_ids": [WID]}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    from nucleo import consent
    from widgets import directory, store
    from widgets.contactos import data as cd
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    for name, phone in (("Raquel Salinas", "600 111 222"), ("Raquel Lozoya", "611 000 777"), ("Marta Ruiz", "611 222 333")):
        cd.apply_action("add_contact", {"name": name, "phone": phone})
        jid = "34" + phone.replace(" ", "") + "@s.whatsapp.net"
        assert directory.note_inbound("whatsapp", {"chatId": jid, "senderId": jid, "from": name})
    untrusted.reset()
    his_words.reset()
    for d in (inline_ask._RECENT, inline_ask._TAKEN, inline_ask._RESUMING):
        d.clear()
    sent, events = [], []

    async def _dispatch(wid, action, payload, *, row="", text="", **kw):
        sent.append({"action": action, "payload": dict(payload), "row": row})
        return {"ok": True}
    from nucleo.flash import data_ops
    monkeypatch.setattr(data_ops, "dispatch_and_report", _dispatch)
    monkeypatch.setattr(send_task, "_schedule", lambda uid: asyncio.run(send_task_run.run(uid)))
    import nucleo.request.send_task_answer as sta
    monkeypatch.setattr(sta, "_schedule", lambda uid: asyncio.run(send_task_run.run(uid)))
    import voice.observer as _obs
    real = _obs.emit
    monkeypatch.setattr(_obs, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        events.append({"kind": kind, "label": label, "text": text, **(extra or {})})
                        or real(kind, label, text=text, role=role, extra=extra))
    yield {"sent": sent, "events": events}
    model._TURN.set(None)
    for d in (inline_ask._RESUMING, inline_ask._TAKEN):
        d.clear()
    consent._reset_for_tests()
    untrusted.reset()
    his_words.reset()
    memdb.reset_db()
    mememb.reset()


def _say(text: str) -> None:
    model.begin(text, trace="t-1")
    his_words.note(text)


@pytest.mark.parametrize("said,members", [
    ("crea un grupo de WhatsApp con Raquel y Marta que se llame Viaje", ["Raquel Salinas", "Marta Ruiz"]),
    ("make a WhatsApp group called Trip with Raquel and Marta", ["Raquel", "Marta Ruiz"]),
])
def test_a_list_with_an_ambiguous_name_is_never_trimmed_by_a_which(world, said, members, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es" if said.startswith("crea") else "en")
    _say(said)
    uid = send_task.commission(WID, "create_group", {"name": "Viaje", "platform": "whatsapp", "members": members},
                               said, reading=READING)
    entry = asker.artefact(uid)
    assert not entry.get("candidates"), "«which one?» is never asked about one name of a list"
    for order in world["sent"]:
        assert order["payload"]["members"] == members, "no order ever leaves with the list cut down"
    assert send_task.artefact(uid)["payload"]["members"] == members


def test_an_answer_never_replaces_a_list_that_already_has_people(world, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    said = "crea un grupo con Raquel y Marta"
    _say(said)
    uid = send_task.retain(WID, "create_group", {"name": "Viaje", "members": ["Raquel Salinas", "Marta Ruiz"]}, said)
    send_task._question(uid, send_task.artefact(uid), "recipient", "members", "¿Cuál Raquel?",
                        ["Raquel Salinas", "Raquel Lozoya"])
    got = send_task_answer.answered(uid, asker.artefact(uid), "Raquel Lozoya", choice=1)
    assert got.get("unclear") and world["sent"] == []
    assert send_task.artefact(uid)["payload"]["members"] == ["Raquel Salinas", "Marta Ruiz"]


def _channel_actions() -> list[tuple[str, str]]:
    from nucleo.workers import exit_slots
    from widgets import effects, runtime
    out = []
    for w in runtime.catalog():
        wid = str(w.get("id") or "")
        for act, s in ((runtime.get(wid) or {}).get("actions") or {}).items():
            if isinstance(s, dict) and effects.leaves(wid, act) and "channel" in exit_slots.declared(wid, act):
                out.append((wid, act))
    return out


CHANNEL_ACTS = _channel_actions()


def test_the_channel_sweep_covers_an_action_whose_key_is_not_the_slots_name():
    from nucleo.workers import exit_slots
    assert any(exit_slots.declared(w, a)["channel"]["key"] != "channel" for w, a in CHANNEL_ACTS)


@pytest.mark.parametrize("wid,act", CHANNEL_ACTS, ids=[f"{w}:{a}" for w, a in CHANNEL_ACTS])
def test_which_channel_is_answered_under_the_declared_key_and_no_other(world, wid, act, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    from nucleo.workers import exit_gate, exit_slots
    key = exit_slots.declared(wid, act)["channel"]["key"]
    said = "by telegram"
    _say(said)
    uid = send_task.retain(wid, act, {key: "whatsapp"}, said)
    monkeypatch.setattr(exit_gate, "cross", lambda *a, **k: _async(exit_gate.Exit(a[2], slots={"channel": "unknown"})))
    monkeypatch.setattr(exit_slots, "channel_choices", lambda turn, payload: ["telegram", "whatsapp"])
    got = asyncio.run(send_task_run.run(uid))
    assert got.get("asked"), got
    entry = asker.artefact(uid)
    assert entry["retained"]["slot"] == key
    send_task_answer.answered(uid, entry, "telegram", choice=0)
    payload = send_task.artefact(uid)["payload"]
    assert payload[key] == "telegram"
    assert [k for k, v in payload.items() if v in ("telegram", "whatsapp") and k != key] == [], payload
    reading = (send_task.artefact(uid).get("reading") or {}).get("result") or {}
    assert reading["message_channel"]["choice"] == "telegram", "his answer is his reading: the exit never doubts it"


async def _coro(v):
    return v


def _async(v):
    return _coro(v)


@pytest.mark.parametrize("call_members", [["Luis Gil"], "Luis Gil", ["Luis Gil", "Marta Ruiz"], ["Marta Ruiz"]],
                         ids=["a shorter list", "one name as text", "a list with someone new", "another person"])
def test_the_answering_turns_call_never_replaces_the_list_the_row_holds(world, call_members, monkeypatch):
    """Second audit: the row holds `members: [Luis Gil, Raquel Lozoya]` and waits on «which channel?»; the answering
    turn's call carries the channel AND another members value — the merge used to replace the list and the group left
    without Raquel, unasked. The same rule as an answer: a list that already has people is replaced by nothing."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    said = "crea un grupo con Luis Gil y Raquel Lozoya que se llame Viaje"
    _say(said)
    held = ["Luis Gil", "Raquel Lozoya"]
    uid = send_task.retain(WID, "create_group", {"name": "Viaje", "members": held, "platform": "whatsapp"}, said)
    send_task._question(uid, send_task.artefact(uid), "channel", "platform", "¿Por WhatsApp o por Telegram?",
                        ["telegram", "whatsapp"])
    _say("por telegram")
    assert send_task_answer.take_call(WID, "create_group", {"name": "Viaje", "platform": "telegram",
                                                           "members": call_members}, "por telegram") == uid
    art = send_task.artefact(uid)
    assert art["payload"]["members"] == held and art["payload"]["platform"] == "telegram"
    for order in world["sent"]:
        assert order["payload"]["members"] == held, "no order ever leaves with the list the row held replaced"


def test_a_slot_the_call_just_changed_is_not_kept_his(world, monkeypatch):
    """«What he already gave stays his» holds only for a value the call left as it was."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    said = "send Marta Ruiz a message"
    _say(said)
    uid = send_task.retain(WID, "send_to", {"contact": "Marta Ruiz"}, said)
    assert send_task.artefact(uid)["slots"]["recipient"]["source"] == "his"
    send_task._question(uid, send_task.artefact(uid), "text", "text", "What should I tell her?")
    _say("running late")
    send_task_answer.take_call(WID, "send_to", {"contact": "Quinn Xavier", "text": "running late"}, "running late")
    art = send_task.artefact(uid)
    assert art["payload"]["contact"] == "Quinn Xavier" and art["slots"]["recipient"]["source"] != "his"

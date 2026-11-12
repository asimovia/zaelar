"""A second prose question about the same send is asked on the row that WAITS — never a second row (group A6; ES/EN).

Measured on the multi-turn bench (2026-11-12, two Raquels in the directory, `cual-*` 3/6): turn 1 «mándale un whatsapp
a Raquel diciendo que llego tarde» → «¿a cuál Raquel?» made durable on a send row; turn 2 «A Raquel Jofre» → the model
asked «¿qué le digo?» in prose and the close opened a SECOND row for the same send — two questions waited, his next
words fit both, and the engine asked «which task is your answer for?». Now the turn's question about a card whose send
already waits is anchored to THAT row (`send_task_anchor.to_waiting`): his words of this turn fill the one declared
candidate they name (identity, never phrasing), the question is asked for the slot that still lacks on the same row,
and his next answer completes that one task. Disarm: make `to_waiting` return "" → a second row is born and the test
goes red.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from memory import db as memdb, embeddings as mememb, tasks_store as ts
from nucleo import his_words, untrusted
from nucleo.circuit import asker
from nucleo.request import ask_outside_door as aod, inline_ask, model, send_task, send_task_anchor

WID, ACT = "mensajeria", "send_to"
WORDS = {
    "es": {"said": "Mándale un whatsapp a Raquel diciendo que llego tarde", "q1": "Hay dos Raquel. ¿A cuál se lo mando?",
           "pick": "A Raquel Jofre", "q2": "¿Qué le digo exactamente?", "text": "que llego tarde",
           "vague": "Dile que llego tarde", "q1b": "¿A qué Raquel?"},
    "en": {"said": "Send Raquel a WhatsApp saying that I'm running late", "q1": "There are two Raquels. Which one?",
           "pick": "To Raquel Jofre", "q2": "What exactly should I tell her?", "text": "that I'm running late",
           "vague": "Tell her I'm running late", "q1b": "Which Raquel?"},
}


def _brief() -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [WID],
            "result": {"catalog_widget": {"choice": WID, "confidence": 0.9}}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    from nucleo import consent
    from widgets import contract, directory, store
    from widgets.contactos import data as cd
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    for name, phone in (("Raquel Jofre", "680 762 886"), ("Raquel Salvador", "680 111 222")):
        cd.apply_action("add_contact", {"name": name, "phone": phone})
    for num in ("34680762886", "34680111222"):
        assert directory.note_inbound("whatsapp", {"chatId": f"{num}@s.whatsapp.net", "senderId": f"{num}@s.whatsapp.net",
                                                   "from": "Raquel"})
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)
    untrusted.reset()
    his_words.reset()
    inline_ask._RECENT.clear()
    inline_ask._TAKEN.clear()
    inline_ask._RESUMING.clear()
    sent, events = [], []

    async def _dispatch(wid, action, payload, *, row="", text="", **kw):
        sent.append({"widget": wid, "action": action, "payload": dict(payload), "row": row})
        return {"ok": True, "result": {"to": payload.get("contact"), "channel": "whatsapp"}}
    from nucleo.flash import data_ops
    monkeypatch.setattr(data_ops, "dispatch_and_report", _dispatch)
    from nucleo.acts import errand
    monkeypatch.setattr(errand, "escalate_to_slowbrain",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("a worker was started")))
    import voice.observer as _obs
    monkeypatch.setattr(_obs, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        events.append({"kind": kind, "label": label, "text": text, **(extra or {})}))
    yield {"sent": sent, "events": events}
    model._TURN.set(None)
    inline_ask._RESUMING.clear()
    inline_ask._TAKEN.clear()
    consent._reset_for_tests()
    untrusted.reset()
    his_words.reset()
    memdb.reset_db()
    mememb.reset()


def _rows():
    return ts.tasks_where(states=("waiting", "running", "done", "failed", "cancelled"), visible_only=False)


def _turn_ends_asking(said: str, question: str, trace: str) -> str:
    """His turn, the model's prose question about the card, the close making it durable."""
    model._TURN.set(None)
    model.begin(said, trace=trace)
    his_words.note(said)
    measured = aod.measure(_brief(), question, did_act=False)
    assert measured and measured["widget"] == WID and ACT in measured["leaves"]
    return aod.held(measured, question, said)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_second_question_is_asked_on_the_row_that_waits_and_his_pick_fills_it(world, lang):
    w = WORDS[lang]
    ask1 = _turn_ends_asking(w["said"], w["q1"], "t-1")
    (row,) = _rows()
    uid = row["id"]
    assert ask1 and row["ask_id"] == ask1 and set(asker.artefact(uid)["candidates"]) == {"Raquel Jofre", "Raquel Salvador"}
    ask2 = _turn_ends_asking(w["pick"], w["q2"], "t-2")
    assert ask2 and ask2 != ask1
    (row,) = _rows()
    assert row["id"] == uid and row["state"] == "waiting" and row["ask_id"] == ask2 and row["ask"] == w["q2"], \
        "ONE row: the second question waits on the first row"
    art = send_task.artefact(uid)
    assert art["payload"]["contact"] == "Raquel Jofre" and art["slots"]["recipient"]["source"] == "his", \
        "his words named one declared candidate: it fills the slot by identity"
    ret = asker.artefact(uid)["retained"]
    assert ret["kind"] == "send" and ret["slot"] == "text" and ret["candidates"] == []
    assert world["sent"] == []
    asyncio.run(inline_ask.rerun(uid, dict(asker.artefact(uid), state="pending"), w["text"]))
    (s,) = world["sent"]
    assert (s["widget"], s["action"], s["row"]) == (WID, ACT, uid)
    assert s["payload"]["contact"] == "Raquel Jofre" and s["payload"]["text"] == w["text"]
    assert len(_rows()) == 1


def test_words_that_name_nobody_anchor_the_question_without_filling_anything(world):
    w = WORDS["es"]
    _turn_ends_asking(w["said"], w["q1"], "t-1")
    (row,) = _rows()
    uid = row["id"]
    ask2 = _turn_ends_asking(w["vague"], w["q1b"], "t-2")
    (row,) = _rows()
    assert row["id"] == uid and row["ask_id"] == ask2 and row["ask"] == w["q1b"]
    art = send_task.artefact(uid)
    assert "contact" not in art["payload"] and art["slots"]["recipient"]["source"] == "none", "nobody was filled in"
    assert set(asker.artefact(uid)["candidates"]) == {"Raquel Jofre", "Raquel Salvador"}, "the which? stays, re-asked"
    assert any(e["label"].startswith("📨 a second question about the same send") for e in world["events"])


def test_another_cards_question_opens_its_own_row(world):
    w = WORDS["es"]
    _turn_ends_asking(w["said"], w["q1"], "t-1")
    assert send_task_anchor.to_waiting("agenda", "A Raquel Jofre", "¿A qué hora?") == ""
    assert len(_rows()) == 1


def test_disarmed_a_second_row_is_born_for_the_same_send(world, monkeypatch):
    monkeypatch.setattr(send_task_anchor, "to_waiting", lambda wid, said, q, emit=None: "")
    w = WORDS["es"]
    _turn_ends_asking(w["said"], w["q1"], "t-1")
    _turn_ends_asking(w["pick"], w["q2"], "t-2")
    assert len(_rows()) == 2, "the defect: two rows for one send"

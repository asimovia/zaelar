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


# ── audit 2026-11-12, A4 + A5 — an intention is the card, the act AND the person ─────────────────────────────────────
# A5: with one send waiting «which Odalys?», «send Thaddeus the address» ended asking too and its question was put on
# the Odalys row — Thaddeus got no row. A4: the same order twice to a name two people share left TWO rows waiting «to
# whom?» (that branch never ended the row that waited). One reader says whom a waiting send is about
# (`one_row.people`): the same person → the same row; another person → a row of its own, and the first keeps waiting.

ODALYS = {"es": {"said": "Mándale un whatsapp a Odalys diciendo que llego tarde", "q": "Hay dos Odalys. ¿A cuál?",
                 "other": "Mándale a Thaddeus la dirección", "q2": "¿Qué dirección le mando?",
                 "again": "Escríbele a Odalys por whatsapp"},
          "en": {"said": "Send Odalys a WhatsApp saying I'm running late", "q": "There are two Odalys. Which one?",
                 "other": "Send Thaddeus the address", "q2": "Which address should I send him?",
                 "again": "Write to Odalys on WhatsApp"}}


@pytest.fixture
def invented(world):
    from widgets import directory
    from widgets.contactos import data as cd
    for name, num in (("Odalys Brezmes", "600555014"), ("Odalys Quintanar", "600555015"), ("Thaddeus Wrenfield", "600555016")):
        cd.apply_action("add_contact", {"name": name, "phone": num})
        directory.note_inbound("whatsapp", {"chatId": f"34{num}@s.whatsapp.net", "senderId": f"34{num}@s.whatsapp.net",
                                            "from": name.split()[0]})
    return world


def _waiting():
    return [r for r in _rows() if r["state"] == "waiting"]


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_question_about_a_send_to_somebody_else_waits_on_a_row_of_its_own(invented, lang):
    w = ODALYS[lang]
    ask1 = _turn_ends_asking(w["said"], w["q"], "t-1")
    (first,) = _rows()
    assert set(asker.artefact(first["id"])["candidates"]) == {"Odalys Brezmes", "Odalys Quintanar"}
    ask2 = _turn_ends_asking(w["other"], w["q2"], "t-2")
    assert ask2 and ask2 != ask1
    rows = {r["id"]: r for r in _waiting()}
    assert len(rows) == 2 and rows[first["id"]]["ask_id"] == ask1 and rows[first["id"]]["ask"] == w["q"], \
        "the Odalys send keeps ITS question"
    (second,) = [r for r in rows.values() if r["id"] != first["id"]]
    assert second["ask_id"] == ask2 and second["ask"] == w["q2"]
    assert send_task.artefact(second["id"])["payload"]["contact"] == "thaddeus", "Thaddeus has his own send"
    assert "contact" not in send_task.artefact(first["id"])["payload"]


@pytest.mark.parametrize("said, q2", [("Mándale a Bartolomeu la dirección", "¿Por WhatsApp o por Telegram?"),
                                      ("Send Bartholomew the address", "On WhatsApp or on Telegram?")])
def test_a_new_order_that_names_nobody_of_his_never_lands_on_the_row_of_somebody_else(invented, monkeypatch, said, q2):
    """With one send waiting «which Odalys?», a NEW order about a person who is not among his contacts ended asking,
    and its question was put on the Odalys row: his answer would have filled HER send. His words resolve nobody, so
    the reading is the turn's: a sure order is a new intention. A turn that is no order (his vague answer) still
    anchors. Disarm: `to_waiting` blind to the order → the question lands on the Odalys row."""
    from nucleo.turn import brief as _tb
    w = ODALYS["es"]
    _turn_ends_asking(w["said"], w["q"], "t-1")
    (first,) = _rows()
    monkeypatch.setattr(_tb, "of_this_turn", lambda: {})                            # no order read: his vague answer
    ask2 = _turn_ends_asking("la de siempre", "¿Cuál de las dos?", "t-2")
    assert ask2 and ts.task_get(first["id"])["ask_id"] == ask2, "an answer that names nobody stays on the row that waits"
    order = _brief()
    order["result"]["request_type"] = {"choice": "order", "confidence": 0.9}
    monkeypatch.setattr(_tb, "of_this_turn", lambda: order)                          # this turn: a sure order
    ask3 = _turn_ends_asking(said, q2, "t-3")
    assert ask3 != ask2 and ts.task_get(first["id"])["ask_id"] == ask2 and ts.task_get(first["id"])["ask"] == "¿Cuál de las dos?"
    assert "contact" not in send_task.artefact(first["id"])["payload"], "nothing of the other send reached her row"
    (new,) = [r for r in _waiting() if r["id"] != first["id"]]
    assert new["ask_id"] == ask3 and new["ask"] == q2, "the new order asks on a row of its own"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_same_order_twice_to_a_name_two_people_share_is_one_waiting_row(invented, lang):
    from nucleo.request import send_task_words
    w = ODALYS[lang]
    rows = []
    for n, said in enumerate((w["said"], w["again"])):
        model._TURN.set(None)
        model.begin(said, trace=f"t-{n}")
        his_words.note(said)
        uid, how = send_task_words.from_verdict(WID, ACT, said, "")
        assert how == "asked" and set(asker.artefact(uid)["candidates"]) == {"Odalys Brezmes", "Odalys Quintanar"}
        rows.append(uid)
    assert rows[0] != rows[1] and [r["id"] for r in _waiting()] == [rows[1]], "his new order is the task: ONE row waits"
    assert ts.task_get(rows[0])["state"] == "cancelled"


def test_a_new_order_to_somebody_else_leaves_the_send_that_waits_alone(invented):
    w = ODALYS["en"]
    _turn_ends_asking(w["said"], w["q"], "t-1")
    (first,) = _rows()
    model._TURN.set(None)
    model.begin(w["other"], trace="t-2")
    his_words.note(w["other"])
    second = send_task.commission(WID, ACT, {"contact": "Thaddeus"}, w["other"])
    assert second and second != first["id"]
    assert ts.task_get(first["id"])["state"] == "waiting", "another person is another intention: nothing is replaced"
    assert {r["id"] for r in _waiting()} == {first["id"], second}

"""V2-807 T-13 — reading the mail card answers from what its screen holds.

The class (live, 2026-10-26): with the draft open on the card, «it's what we are doing right now» was read against the
card and its `read_query` keyword-searched the INBOX: four unrelated messages matched filler words and the reply
talked about one of them. With a draft (or one mail) open, the read now returns THAT object; the inbox is searched
when the screen holds a list. Spanish and English questions, a draft and an opened message.
"""
from __future__ import annotations

import time

import pytest

from widgets import store as wstore
from widgets.mensajeria import data, inbox_read, mailbox

DRAFT = "Hola,\n\nQueremos acceso a vuestra API de reservas.\n\nUn saludo,\nEquipo Zaelar"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wstore, "_last_hash", {})
    db = data.load_db()
    now = time.time()
    db["items"] = [
        {"platform": "email", "chatId": "a@x.example", "messageId": "1", "from": "Greenhouse Shop",
         "body": "Lo que estamos haciendo ahora mismo en el invernadero: ofertas", "ts": now - 60},
        {"platform": "email", "chatId": "b@x.example", "messageId": "2", "from": "Newsletter",
         "body": "What we are doing right now with your saved state", "ts": now - 120},
    ]
    wstore.save("mensajeria", db)
    yield


def _open_draft():
    out = data.apply_action("draft", {"contact": "partners@booking.example", "subject": "API access", "text": DRAFT})
    assert out["ok"], out
    assert data.apply_action("open_draft", {"contact": "partners@booking.example"})["ok"]


@pytest.mark.parametrize("question", ["¿Cómo que no lo tienes guardado en tu estado? Si es lo que estamos haciendo",
                                      "what are we doing right now, is it saved in your state?"])
def test_with_a_draft_open_the_read_is_the_draft_not_the_inbox(question):
    _open_draft()
    got = data.read_query(question)   # the door `nucleo/flash/widget_read` asks
    assert "partners@booking.example" in got and "API access" in got and "Queremos acceso" in got
    assert "Greenhouse" not in got and "Newsletter" not in got, "the inbox is not what the screen holds"


def test_with_one_mail_open_the_read_is_that_mail():
    db = data.load_db()
    mailbox.open_message(db, "77", "INBOX")
    mailbox.fold(db, {"folder": "INBOX", "open": {"uid": "77", "from": "Rowan Pike <rowan@x.example>",
                                                  "subject": "Thursday venue", "body": "Deposit is 200, terrace ok."}})
    wstore.save("mensajeria", db)
    got = inbox_read.read_query("what does it say about the deposit?")
    assert "Thursday venue" in got and "Deposit is 200" in got and "Greenhouse" not in got


def test_with_a_list_on_screen_the_inbox_is_searched_as_before():
    got = inbox_read.read_query("¿qué me ha escrito Greenhouse?")
    assert "Greenhouse" in got

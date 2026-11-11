"""V2-886 D5 — a question card speaks his language: its heading is its row's title (else its goal), inline rows
included, and a recipient is shown by his contact's name — never «a process», never a raw chat id.

Measured 2026-11-11: «Pregunta de «un proceso» — … «send_draft» con «62861309169746@lid» en tu nombre».
Invented people only."""
import pytest

from nucleo.circuit import asker
from widgets import directory

_PEOPLE = [{"name": "Zarina Quell", "channels": [{"platform": "whatsapp", "chatId": "40000000000001@lid",
                                                  "handle": "+34 600 111 222"}]},
           {"name": "Bram Ostrow", "email": "bram@example.org", "channels": []}]


@pytest.fixture
def people(monkeypatch):
    monkeypatch.setattr(directory, "_contacts", lambda: _PEOPLE)


@pytest.mark.parametrize("raw,shown", [("40000000000001@lid", "Zarina Quell"), ("+34600111222", "Zarina Quell"),
                                       ("bram@example.org", "Bram Ostrow"), ("77777777777@lid", "77777777777@lid"),
                                       ("Someone New", "Someone New")])
def test_a_recipient_is_shown_by_his_contacts_name(people, raw, shown):
    assert directory.shown_as(raw) == shown


def test_the_card_heading_is_its_rows_title_or_goal(monkeypatch):
    from memory import tasks_store
    rows = {"r1": {"id": "r1", "title": "Close the open cards", "goal": "close everything"},
            "r2": {"id": "r2", "title": "", "goal": "send the draft to Zarina"}}
    monkeypatch.setattr(tasks_store, "task_get", lambda uid: rows.get(uid))
    seen = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **kw: seen.append(kw.get("extra") or {}))
    asker.emit_ask(task_id="r1", ask_id="a1", text="?")
    asker.emit_ask(task_id="r2", ask_id="a2", text="?")
    asker.emit_ask(task_id="nope", ask_id="a3", text="?")
    assert [e["title"] for e in seen] == ["Close the open cards", "send the draft to Zarina", ""]

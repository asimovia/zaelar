"""V2-886 D7 · Every question card has a ✕: closing it is his NO to the task that waits on it.

`POST /api/tasks/<row>/asks/<ask_id>/dismiss` → when that question is the row's open one, the row ends through his
cancel door (the same as the cancel button: worker told, one line said) and an `ask_dismissed` event records it; a
question that is not the open one (answered, replaced, gone) is 409 and changes nothing. The card carries the ✕ and
its label in both languages."""
from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import dispatch

ENGINE = Path(__file__).resolve().parents[3]


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    events, said = [], []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None:
                        events.append({"kind": kind, "label": label, **(extra or {})}))
    monkeypatch.setattr(dispatch, "cancel_session", lambda tid, **k: True)
    from nucleo.pulse import notices

    async def notify(title, text, **kw):
        said.append(text)
        return {"id": 1, "state": "spoken", "channel": "voice", "duplicate": False}
    monkeypatch.setattr(notices, "notify", notify)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from server import tasks_api
    app = FastAPI()
    app.include_router(tasks_api.router)
    yield SimpleNamespace(c=TestClient(app), events=events, said=said)
    memdb.reset_db()


def _waiting(uid: str, ask_id: str) -> None:
    ts.task_put({"id": uid, "goal": "Send the draft to Zarina", "title": "Send the draft to Zarina",
                 "state": "running", "created_at": int(time.time())})
    from nucleo.circuit import ledger
    ledger.waiting(uid, ledger.USER_ANSWER, ask_id, "Send it?")      # the one writer of a wait


def test_the_open_question_dismissed_ends_its_row_once(world):
    _waiting("d1", "d1-q1")
    r = world.c.post("/api/tasks/d1/asks/d1-q1/dismiss")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert ts.task_get("d1")["state"] == "cancelled"
    assert [e for e in world.events if e.get("kind_diag") == "ask_dismissed" and e.get("ask_id") == "d1-q1"]
    again = world.c.post("/api/tasks/d1/asks/d1-q1/dismiss")
    assert again.status_code == 409, "a dismissed question is never dismissed (or asked) twice"


def test_a_question_that_is_not_the_open_one_changes_nothing(world):
    _waiting("d2", "d2-q2")
    assert world.c.post("/api/tasks/d2/asks/d2-q1/dismiss").status_code == 409
    assert ts.task_get("d2")["state"] == "waiting"
    assert world.c.post("/api/tasks/nope/asks/x/dismiss").status_code == 409


def test_the_card_carries_the_close_button_in_both_languages():
    js = (ENGINE / "frontend/app/components/TaskAsk.js").read_text(encoding="utf-8")
    assert "asks.dismiss(a.task_id, a.ask_id)" in js and "tq-close" in js
    store = (ENGINE / "frontend/app/core/asks.js").read_text(encoding="utf-8")
    assert "/dismiss" in store
    for lang in ("es", "en"):
        bundle = json.loads((ENGINE / f"i18n/genesis/{lang}/ui.json").read_text(encoding="utf-8"))
        assert bundle.get("chat.askDismiss"), lang

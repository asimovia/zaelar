"""An irreversible act of a card waits for his yes ON ITS ROW, through the one asker (V2-857 phase 3).

What he does by hand: «vacía toda la agenda» — the agenda's `clear_all` is `confirm:true`, so the engine asks. The
question used to live in this process's memory for 90 s (`widgets.confirm._PENDING`) and its yes was read by a word
list before the brief: a restart or a barge-in lost it, and «ok, book it» once sent a mail. Now the request's inline
row waits with its `ask_id`, the act is retained on the row, the two answers are DECLARED candidates the brief picks
(`#0` yes · `#1` no) and the screen shows as buttons, and the yes re-runs the act through its own door — once,
whoever answered first (his voice, delivered to the row by the switchboard, or the card's button). Nothing waits in memory.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.request import consent_ask as ca, inline_ask as ia, model as rq

TURNS = {"es": ("vacía toda la agenda", "¿Vacío toda la agenda?", "sí, vacíala"),
         "en": ("clear the whole agenda", "Clear the whole agenda?", "yes, clear it")}


@pytest.fixture
def world(monkeypatch):
    from nucleo.cli import worker_api_resume
    from nucleo.acts import data_ops
    from widgets import confirm as wc
    st = {"dispatched": [], "events": []}

    async def _dispatch(wid, action, payload, **kw):
        st["dispatched"].append((wid, action, dict(payload or {}), kw.get("row")))
        return {"ok": True}
    monkeypatch.setattr(data_ops, "dispatch_and_report", _dispatch)
    monkeypatch.setattr(worker_api_resume, "resume_soon", lambda uid, e: None)
    import voice.observer as _obs
    real = _obs.emit
    monkeypatch.setattr(_obs, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        st["events"].append((kind, label, dict(extra or {}))) or real(kind, label, text=text, role=role, extra=extra))
    wc.reset()
    ia._TAKEN.clear()
    st["rows"] = []
    yield st
    from nucleo.circuit import ledger
    for uid in st["rows"]:                      # the rows this test opened go with it: nothing waits for the next test
        ledger.store().task_forget(uid)
    wc.reset()
    ia._TAKEN.clear()
    rq._TURN.set(None)


def _ask(world, lang: str) -> tuple[str, str]:
    words, question, _yes = TURNS[lang]
    rq.begin(words)
    row, ask_id = ca.ask_consent("agenda", "clear_all", {}, question, text=words)
    assert row and ask_id, "the question found no row"
    world["rows"].append(row)
    return row, ask_id


@pytest.mark.parametrize("lang", ["es", "en"])
def test_his_yes_runs_the_act_once_on_that_row(world, lang):
    from nucleo.cli import worker_api
    from nucleo.circuit import ledger
    row, ask_id = _ask(world, lang)
    assert asyncio.run(worker_api.answer(ask_id, TURNS[lang][2], choice=0)) is True
    assert world["dispatched"] == [("agenda", "clear_all", {}, row)]
    assert (ledger.get(row) or {}).get("waiting_for") in (None, ""), "the row still waits after his yes"
    # a second reader of the same answer (the model re-calling the act, the button) runs nothing more
    assert asyncio.run(worker_api.answer(ask_id, TURNS[lang][2], choice=0)) is False
    assert len(world["dispatched"]) == 1


def test_his_no_ends_the_row_and_runs_nothing(world):
    from nucleo.cli import worker_api
    from nucleo.circuit import ledger
    row, ask_id = _ask(world, "es")
    assert asyncio.run(worker_api.answer(ask_id, "no, déjala", choice=1)) is True
    assert world["dispatched"] == [] and (ledger.get(row) or {}).get("state") == "cancelled"


def test_the_cards_button_answers_the_same_question(world):
    from fastapi.responses import JSONResponse
    from widgets import server_api
    row, ask_id = _ask(world, "en")
    res: JSONResponse = asyncio.run(server_api.confirm_widget("agenda", {"ok": True}))
    assert res.status_code == 200 and world["dispatched"] == [("agenda", "clear_all", {}, row)]
    again: JSONResponse = asyncio.run(server_api.confirm_widget("agenda", {"ok": True}))
    assert again.status_code == 409 and len(world["dispatched"]) == 1


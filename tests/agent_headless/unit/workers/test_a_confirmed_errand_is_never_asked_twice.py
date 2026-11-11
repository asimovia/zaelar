"""V2-877 #2 — one question is one ask: a confirmed errand is never asked again, a re-ask is a NEW ask, the bind door
never reports an answer the answer door refuses, and an answered question settles its notice.

Measured 2026-11-11 in the sandbox (EN, «build me an app that shows the time in Tokyo»): his first «yes» relaunched the
build; the worker stalled, the stall restart went through the widget confirm gate again (`context["confirmed"]` is a
flag of ONE worker's context, the relay does not carry it) and asked the same question under the SAME id
(`{uid}-start`). Every later «yes» was «bound to its task» — `answer_soon` saw the id among the open asks — while
`answer()` refused it (its entry was already `answered`): the row waited a week and he was told «passing that on».
The `approval:N` notice that said the question stayed `owed` after the answer and was painted on the next screen.

The classes, fixed at their doors: the confirmation is a fact of the ROW (`dispatch.confirm.CONFIRMED_SLOT`, read by
both start gates); an ask id is per ASK; `answer_soon` and `answer` share one reading (`worker_api_answer.refusal`);
the notice is bound to its question (`notices.bind_ask`) so `notice_ask.closed_answered` settles it.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import tasks_store as ts


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    now = int(time.time())
    ts.task_put({"id": "c1-1", "goal": "build me an app that shows the time in Tokyo", "title": "Tokyo clock",
                 "kind": "code", "state": "running", "created_at": now, "started_at": now})
    yield "c1-1"
    memdb.reset_db()
    mememb.reset()


def _gate_run(monkeypatch, context: dict) -> dict:
    """Drive the ONE door a worker starts through (`_run_session`) up to its gates. Returns which gate stopped it:
    `asked` (the widget confirm gate parked it) or `passed` (it reached the next gate, which stops the run here)."""
    from nucleo import dispatch
    from nucleo.dispatch import confirm as _dconf
    seen = {"asked": False, "passed": False}
    monkeypatch.setattr(dispatch, "remember_code_change", lambda *a, **k: seen.__setitem__("asked", True))
    monkeypatch.setattr(dispatch, "make_durable", lambda *a, **k: "")

    async def _quiet(rec):
        return None
    monkeypatch.setattr(dispatch, "_deliver_confirm", _quiet)

    async def _stop_here(task, key, req):
        seen["passed"] = True
        return True
    monkeypatch.setattr(_dconf, "unlicensed_gate", _stop_here)
    from nucleo.workers.session import SessionRecord
    task = dispatch.Task(id=91, request="build me an app that shows the time in Tokyo", kind="code", trusted=True,
                         context=dict(context))
    monkeypatch.setitem(dispatch._SESSIONS, "91", SessionRecord(task_id="91", goal=task.request, kind="code"))
    asyncio.run(dispatch._run_session(task))
    return seen


def test_a_relay_of_a_confirmed_row_is_not_asked_again(db, monkeypatch):
    """The stall restart's context carries the row, not the flag: the gate reads the ROW's yes."""
    from nucleo.dispatch import confirm as dc
    relay = {"src": "stall_restart", "kind": "code", "task_uid": db, "relay_gen": 1}
    assert _gate_run(monkeypatch, relay)["asked"], "an UNconfirmed row asks — this test would prove nothing"
    dc.confirmed_on_row(db)
    seen = _gate_run(monkeypatch, relay)
    assert seen["passed"] and not seen["asked"], "his yes is a fact of the row: a relay of it is never asked again"


def test_the_gate_his_yes_crossed_writes_it_on_the_row(db, monkeypatch):
    """The ONE place the fact is written: the start gate a confirmed launch crosses (any path that confirmed it)."""
    from nucleo.dispatch import confirm as dc
    assert not dc.confirmed({"task_uid": db})
    assert _gate_run(monkeypatch, {"kind": "code", "task_uid": db, "confirmed": True})["passed"]
    assert dc.confirmed({"task_uid": db}), "the confirmed launch left its yes on its row"
    assert not dc.confirmed({"task_uid": "c1-other"}), "another row is not confirmed by it"


def test_a_new_ask_on_the_same_row_gets_a_new_id(monkeypatch):
    """A re-ask, when one is legitimately needed, is a NEW open question — never a spent one."""
    from nucleo.circuit import asker
    from nucleo.dispatch import confirm as dc
    asked = []
    monkeypatch.setattr(asker, "ask", lambda uid, entry, bus_id="": asked.append(entry["ask_id"]) or entry["ask_id"])
    from nucleo.pulse import notice_ask
    bound = []
    monkeypatch.setattr(notice_ask, "bind_ask", lambda key, ask_id: bound.append((key, ask_id)) or True)
    dc._PENDING_CONFIRM.clear()
    task = SimpleNamespace(kind="code", trusted=True, context={"kind": "code"})
    rec = SimpleNamespace(uid="c1-1", task_id="7")
    for _ in range(2):
        dc.remember_code_change("7", "build me an app that shows the time in Tokyo", task)
        dc.make_durable("7", rec)
    dc._PENDING_CONFIRM.clear()
    first, second = asked
    assert first.startswith("c1-1-start-") and second.startswith("c1-1-start-")
    assert first != second, "the row's second question reused the first one's (spent) id"
    assert bound == [("approval:7", first), ("approval:7", second)], "the notice that said it is bound to its ask"


def _waiting_on(uid: str, ask_id: str, state: str) -> None:
    from nucleo.circuit import asker, ledger
    ledger.waiting(uid, ledger.USER_ANSWER, ask_id, "Shall I build it?")
    asker.keep(uid, {"ask_id": ask_id, "corr_id": ask_id, "uid": uid, "task_id": "3", "inline": True,
                     "question": "Shall I build it?", "state": state, "retained": {"kind": "start"}})


def test_the_bind_door_reports_the_refusal_and_says_so(db, monkeypatch):
    """A spent question the row still lists: never «bound», never «passed on» — the truth, in his language, once."""
    from i18n import langs
    from nucleo import dispatch
    from nucleo.cli import worker_api  # noqa: F401 — the package first: its answer module imports it back
    from nucleo.cli import worker_api_answer as wa
    from nucleo.pulse import notices
    said = []

    async def _notify(title, text, **kw):
        said.append((text, kw.get("key")))
        return {}
    monkeypatch.setattr(notices, "notify", _notify)
    monkeypatch.setattr(dispatch, "_LOOP", None, raising=False)
    _waiting_on(db, "c1-1-start-a", "answered")
    assert wa.refusal("c1-1-start-a") == wa.ANSWERED

    async def _go():
        bound = wa.answer_soon("c1-1-start-a", "yes")
        await asyncio.sleep(0)
        return bound, await wa.answer("c1-1-start-a", "yes")
    bound, taken = asyncio.run(_go())
    assert bound is False and taken is False, "the bind door and the answer door read the same refusal"
    line = langs.current_language().answer_already_given
    assert line and said == [(line, "answer_refused:c1-1-start-a")]


def test_an_open_question_is_still_bound(db, monkeypatch):
    from nucleo.cli import worker_api as _m
    from nucleo.cli import worker_api_answer as wa
    from nucleo import dispatch
    got = []

    async def _answer(ask_id, text, choice=None):
        got.append(ask_id)
        return True
    monkeypatch.setattr(_m, "answer", _answer)
    monkeypatch.setattr(dispatch, "_LOOP", None, raising=False)
    _waiting_on(db, "c1-1-start-b", "pending")
    assert wa.refusal("c1-1-start-b") == ""

    async def _go():
        ok = wa.answer_soon("c1-1-start-b", "yes")
        await asyncio.sleep(0)
        return ok
    assert asyncio.run(_go()) is True and got == ["c1-1-start-b"]
    assert wa.refusal("nobody-asked-this") == wa.CLOSED


def test_an_answered_question_settles_the_notice_that_said_it(db, monkeypatch):
    """The start question is spoken BEFORE it is durable: binding the notice to it lets the answer settle it."""
    from nucleo.cli import worker_api_asks
    from nucleo.pulse import notice_ask, notices
    row, _fresh = notices._claim("approval:3", "approval", "zaelar", "Shall I build it?", "", {"task": "3"})
    notices._owe(row)
    open_ = [{"ask_id": "c1-1-start-c"}]
    monkeypatch.setattr(worker_api_asks, "pending_asks", lambda: list(open_))
    assert notice_ask.bind_ask("approval:3", "c1-1-start-c")
    assert not notice_ask.closed_answered(notices.by_key("approval:3")), "an OPEN question's notice stays owed"
    open_.clear()                                               # he answered: the row no longer waits on it
    assert notice_ask.closed_answered(notices.by_key("approval:3"))
    assert notices.by_key("approval:3")["state"] == "answered"

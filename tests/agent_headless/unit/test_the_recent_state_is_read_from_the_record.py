from nucleo import circuit
"""V2-776 M2 · the prompt's recent state is read from the RECORD, always (nodes 2.196, 2.197, 3.112).

Manual session 7850de3f (2026-09-30): the INIT list finished at 11:19; at 12:43 the agent said «it's all still
running in the background». The record knew. `record_lines` quoted ONE row and only when RAM was silent. Now the
last requests of the last hours — inline, worker, list, errand — are one line each: facts, no instruction.
"""
import contextvars
import time

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo.request import model as rq


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db(); memdb.get_db()
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "active_sessions", lambda: [])
    monkeypatch.setattr(dispatch, "recently_ended_sessions", lambda now=None, limit=3: [])
    yield
    memdb.reset_db()


def _inline(text, widget, action, verdict, outcome=""):
    uid = contextvars.copy_context().run(lambda: (rq.begin(text), rq.opened(widget, action))[1])
    circuit.settle(row=uid, verdict=verdict, outcome=outcome)
    return uid


def test_reopening_a_task_never_offers_an_inline_request():
    """M5 — `reopen_task` reopens REPORTS; a session's thirty agenda adds must not turn it into a question."""
    from nucleo.errands import task_recall
    for i in range(4):
        _inline(f"add the flat viewing number {i} to my calendar", "agenda", "add_meeting", "met")
    ts.task_put({"id": "w-flat", "title": "Find a flat to rent in Madrid", "goal": "find me a flat in Madrid",
                 "kind": "web", "state": "done", "finished_at": int(time.time())})
    got = task_recall.resolve("the flat task")
    assert got["ok"] and got["task"]["id"] == "w-flat"


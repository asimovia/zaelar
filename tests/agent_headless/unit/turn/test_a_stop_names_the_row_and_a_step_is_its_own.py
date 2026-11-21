"""One identity per task (V2-852 T03, invariant I1): a line about a worker's step names the ROW, and the stop of a
step stops the step.

Measured in session c8a307fd: the browser tab driving the car search numbered itself «2» and asked «Task 2 needs your
OK to click «Eliminar Toyota 4Runner»». He answered «yes, close task 2»; the stop verdict read `stop`, the backstop
resolved it against the only live errand, and the whole search row was cancelled while the reply said «I've stopped
task 2 — the Toyota job». Two numberings of one work, and a stop of a step that ended the task.

Now (1) every line a step says is named by its row's title and keyed by its row's uid (`tasks.row_of`), so there is
no second number to say; (2) while a step waits for his OK the stop question offers `decline_step`, and a sure one
answers that step NO and cancels nothing. The variants are another domain (a flat, a booking) and another language.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nucleo.request import stop_row as sr


@pytest.fixture
def nav(monkeypatch):
    from widgets.navegador import tasks
    made: list = []

    def tab(goal: str, row_title: str | None, row_id: str = "7"):
        tid = tasks.create(goal, goal[:40])
        made.append(tid)
        rec = None if row_title is None else SimpleNamespace(task_id=row_id, title=row_title, goal=goal)
        from nucleo import dispatch
        monkeypatch.setattr(dispatch, "record_by_nav_task", lambda t, _tid=tid, _rec=rec: _rec if str(t) == _tid else None)
        return tid
    yield tasks, tab
    with tasks._lock:
        for t in made:
            tasks._tasks.pop(t, None)


@pytest.mark.parametrize("goal,row", [("Find a flat to rent in Lisbon under 1200", "Lisbon flat under 1200"),
                                      ("Reserva mesa para cuatro en Sevilla el viernes", "Mesa en Sevilla")])
def test_a_line_about_a_step_carries_the_rows_identity(nav, goal, row):
    from nucleo.circuit import ledger
    tasks, tab = nav
    tid = tab(goal, row)
    who = tasks.row_of(tid)
    assert who["title"] == row, "the step was named by its own registry, not by the task he commissioned"
    assert who["uid"] == ledger.task_uid("7") and who["step"] == tid
    from widgets.navegador import click_reason
    line = click_reason.needs_ok(who["title"], "Remove filter")
    assert row in line and f" {tid} " not in f" {line} ", f"the tab's own number reached the line: {line!r}"


def test_a_tab_he_drives_himself_is_its_own_task(nav):
    tasks, tab = nav
    tid = tab("compare two phone plans", None)
    who = tasks.row_of(tid)
    assert who["uid"] == "" and who["title"] == "compare two phone plans"


# ── the stop resolves against ROWS: their uid, their own number, their title — never a worker's number ─────────
@pytest.fixture
def rows(monkeypatch):
    from nucleo import dispatch
    recs = {"2": SimpleNamespace(uid="abffbc-7", title="Used Mercedes GLC 2021-22"),
            "5": SimpleNamespace(uid="abffbc-9", title="Flat to rent in Lisbon")}
    monkeypatch.setattr(dispatch, "resolve_sessions", lambda q: list(recs) if not q else [q] if q in recs else list(recs))
    monkeypatch.setattr(dispatch, "get_record", lambda k: recs.get(k))
    return recs

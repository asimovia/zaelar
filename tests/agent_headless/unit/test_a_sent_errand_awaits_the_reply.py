"""INI-042 #26 — an errand whose message went out WAITS for the reply; it is not «running».

The first errand of the operator's session («ask her what time she is coming») was sent fine and then sat on the
board as a task still being worked on, because every live errand state was mirrored as `running`. Who has the next
word is the difference: once the message is out the other party does, so the task row says `waiting` with
`waiting_for = reply` (the screen draws «sent · awaiting reply»). The class, not the case: every errand state in
which the other party has the next word mirrors that way, and the states where the work is ours go back to running.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def er(tmp_path, monkeypatch):
    """An isolated database and playbook layer (the same isolation `test_an_errand_outlives_the_turn` uses)."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    import memory.db as _db
    _db.reset_db()
    from nucleo import workspace
    from nucleo.errands import playbooks
    monkeypatch.setattr(workspace, "root", lambda: tmp_path)
    playbooks._override_cache = (None, {})
    from nucleo import errands
    yield errands
    _db.reset_db()


def _row(er, errand):
    from nucleo.circuit import ledger
    return ledger.store().task_get(ledger.errand_uid(errand["id"]))


def test_a_sent_errand_waits_for_the_reply_not_running(er):
    from nucleo.circuit import ledger
    e = er.start("preguntarle a Ana a qué hora viene")
    row = _row(er, e)
    assert e["state"] == "contacting"
    assert row["state"] == "waiting" and row["waiting_for"] == ledger.REPLY
    assert row["waiting_since"]
    board = ledger.board("live")
    assert [r["id"] for r in board] == [ledger.errand_uid(e["id"])], "a waiting errand stays on the live board"


def test_the_reply_wait_keeps_its_clock_and_ends_when_the_work_is_ours(er):
    from nucleo.circuit import ledger
    e = er.start("organizar una reunión con Iván esta tarde")
    since = _row(er, e)["waiting_since"]
    er.update(e["id"], state="negotiating")            # they answered, we answered back: their word again
    row = _row(er, e)
    assert row["state"] == "waiting" and row["waiting_for"] == ledger.REPLY and row["waiting_since"] == since
    er.update(e["id"], state="agreed")                 # now the work is ours: it runs
    row = _row(er, e)
    assert row["state"] == "running" and not row["waiting_for"]


def test_a_reply_wait_is_never_read_as_waiting_for_him(er):
    """The operator's own waits (`user_answer`) drive the nag, the prompt's «ESPERA tu respuesta» and the question
    cards. A reply wait must reach none of them."""
    from nucleo.turn.prompt import live_tasks
    er.start("preguntarle a Ana a qué hora viene")
    assert live_tasks.waiting_lines() == []


def test_a_closed_errand_still_lands_in_done(er):
    from nucleo.circuit import ledger
    e = er.start("preguntarle a Ana a qué hora viene")
    er.close(e["id"], why="viene a las 8")
    assert ledger.board("live") == []
    assert [r["state"] for r in ledger.board("done")] == ["done"]

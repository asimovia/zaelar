"""V2-931 · His stop ends the process at once — whatever state it is in.

Measured on his engine (2026-11-17, 23:10): with a task waiting on «shall I change your widget?», «stop every change
to any widget, I never asked for that» was handed to the task as words («OK, I'll pass it to the task») and the task
stayed open until he pressed its button seventeen minutes later. A stop is not a sentence for the worker to read: the
switchboard reads it (`"is": "stop"`, every process with `"all": true`) and ends the row through its ONE cancel door
(`dispatch.control.cancel_row`, the screen's button): a running worker's session is told to stop (signal, grace,
kill), a queued one never starts, a waiting question is closed, the row ends `cancelled`, and he hears one line.
"""
from __future__ import annotations

import time
from types import SimpleNamespace


from memory import tasks_store as ts


class _Session:
    """A worker session as the stop door drives it: `stop(reason=…)` is the signal → grace → kill of its backend."""

    def __init__(self):
        self.stops, self.alive = [], True

    async def stop(self, *, grace: float = 3.0, reason: str = "") -> None:
        self.stops.append(reason)
        self.alive = False


def _row(uid: str, state: str, title: str) -> None:
    ts.task_put({"id": uid, "goal": title, "title": title, "state": state, "created_at": int(time.time())})


def _proc(uid: str, title: str, *, tid: str = "", state: str = "running", ask_id: str = "") -> dict:
    return {"key": uid, "dispatch": tid, "title": title, "state": state, "question": "Shall I?" if ask_id else "",
            "ask_id": ask_id, "since": 0}


def _line(key: str) -> str:
    from i18n import langs
    return str(getattr(langs.current_language(), key))


def test_a_send_taken_to_its_receipt_is_never_judged_unmet_nor_relaunched(monkeypatch):
    """The session ended two seconds before the connector's receipt; its close read the goal «unmet» and relaunched the
    task on another model, which verified a sent message and said so again. The receipt is the verdict of a send the
    engine follows: the close steps aside."""
    from nucleo import circuit
    from nucleo.request import send_receipt
    launched = []
    monkeypatch.setattr("nucleo.acts.errand.escalate_to_slowbrain", lambda *a, **k: launched.append(a) or 1)
    monkeypatch.setattr(circuit, "verdict_of", lambda rec: ("unmet", "mensajeria.sent has no row"))
    monkeypatch.setattr(circuit, "_emit", lambda *a, **k: None)
    rec = SimpleNamespace(uid="s2-3", status="done", handoff="", task_id="9", goal="Message to Quinn", kind="generic",
                          trace_id="", done_when={}, depth=0, relay_gen=0, goal_retried=False, result_summary="", ok=True)
    monkeypatch.setitem(send_receipt._taken, "s2-3", time.time())
    assert circuit._close(rec, 3) == "skipped" and launched == [] and rec.verdict == "skipped"
    assert send_receipt.owns_the_verdict("s2-3") and not send_receipt.owns_the_verdict("nobody")


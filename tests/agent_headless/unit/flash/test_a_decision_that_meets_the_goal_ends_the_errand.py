"""A decision that meets the errand's goal ENDS it, as met (V2-831 T-29).

His cloud session, 2026-10-29: he picked one of the options the running errand had found, and the worker went on
working. The class is not a phrase («I'll keep X») but a verdict: the brief's `stop_errand` question, which already
decides steer and stop through one reading, answers `settled` when his message decides what the task was for. Then
the errand ends through `dispatch.settle_soon` — the row is DONE with his words as its outcome, the sheet's process
line names his pick, the end event is ok — never a cancellation. The question carries the errand's goal, because a
decision can only settle a goal the question names. The bench cases (ES+EN plus counter-cases) are in
`tests/brain/cases/errands.json`.
"""
from __future__ import annotations



def test_a_settled_errand_ends_done_with_his_pick(monkeypatch):
    from nucleo import dispatch
    from nucleo.circuit import ledger
    from nucleo.workers.session_record import SessionRecord
    events, phases = [], []
    monkeypatch.setattr("voice.observer.emit", lambda kind, label, **k: events.append((kind, label, k.get("extra") or {})))
    monkeypatch.setattr(dispatch, "record_phase", lambda rec, phase, *a, **k: phases.append(phase) or True)
    monkeypatch.setattr(dispatch, "_LOOP", None)
    monkeypatch.setattr(dispatch, "sync_state", lambda: None)
    rec = SessionRecord(task_id="t29", goal="Find a table for four on Friday", status="running")
    monkeypatch.setitem(dispatch._SESSIONS, "t29", rec)
    assert dispatch.settle_soon("t29", "the 7:30 table at Lolita") == ["t29"]
    assert rec.settled == rec.result_summary == "the 7:30 table at Lolita"
    assert dispatch.cancel_session("t29", reason="settled")
    rec.status = "cancelled"                        # what the stopping session writes
    assert ledger.state_of(rec) == "done", "a settled errand is met, not cancelled"
    assert any(k == "task" and lbl == "settled" for k, lbl, _ in events)
    assert [x.get("ok") for k, lbl, x in events if lbl == "end"] == [True]
    assert phases and "the 7:30 table at Lolita" in phases[0]


def test_a_plain_stop_still_cancels(monkeypatch):
    from nucleo import dispatch
    from nucleo.circuit import ledger
    from nucleo.workers.session_record import SessionRecord
    events = []
    monkeypatch.setattr("voice.observer.emit", lambda kind, label, **k: events.append((kind, label, k.get("extra") or {})))
    monkeypatch.setattr(dispatch, "sync_state", lambda: None)
    rec = SessionRecord(task_id="t29b", goal="Busca pisos en Gràcia", status="running")
    monkeypatch.setitem(dispatch._SESSIONS, "t29b", rec)
    assert dispatch.cancel_session("t29b")
    rec.status = "cancelled"
    assert ledger.state_of(rec) == "cancelled"
    assert [x.get("ok") for k, lbl, x in events if lbl == "end"] == [False]


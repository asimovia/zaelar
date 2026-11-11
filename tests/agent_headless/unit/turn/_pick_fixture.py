"""Shared fixture for the V2-878 §5 shadow tests: a live errand with a row and no sheet rows, a brief, the timeline."""
from __future__ import annotations

import threading

import pytest

from memory import db as memdb
from nucleo import dispatch
from nucleo.circuit import ledger
from nucleo.turn import pick_pending, thread_event
from nucleo.workers.session_record import SessionRecord
from voice import observer, trace


def brief(words: str = "act", judged: str = "", open_ids=()) -> dict:
    ev = threading.Event()
    ev.set()
    res = {"_call_id": "t", "wants_words": {"choice": words, "confidence": 0.9, "probs": {}}}
    return {"event": ev, "turn_id": "t", "result": res, "judged": judged, "open_ids": list(open_ids)}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    pick_pending.reset()
    thread_event.reset()
    state = {"events": [], "relayed": [], "injected": []}
    real = observer.emit
    monkeypatch.setattr(observer, "emit", lambda k, label, *a, **kw: state["events"].append((k, label, kw.get("extra") or {}))
                        or real(k, label, *a, **kw))
    from nucleo.dispatch import soon
    monkeypatch.setattr(soon, "his_words_may_reach_an_errand", lambda: True)   # the owner rule has its own test
    monkeypatch.setattr(dispatch, "inject_soon", lambda which, words: state["injected"].append((which, words)))
    state["relayed"] = state["injected"]          # what the one relay door sent on, as the worker would get it

    def errand(tid: str, goal: str, sheet: str) -> str:
        uid = ledger.born(tid, goal, {"said": goal})
        rec = SessionRecord(task_id=tid, goal=goal, uid=uid, sheet=sheet)
        rec.status = "running"
        dispatch._SESSIONS[tid] = rec
        return uid
    state["errand"] = errand
    trace.adopt("T-pick")
    yield state
    trace.adopt("")
    pick_pending.reset()
    memdb.reset_db()


def thread(state, event: str) -> list[dict]:
    return [x for k, _l, x in state["events"] if k == thread_event.KIND and x.get("event") == event]

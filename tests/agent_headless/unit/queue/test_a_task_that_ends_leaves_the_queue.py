"""A task of the queue has ONE writer, and when it ends it LEAVES (INI-078 Q-2, Q-4, Q-8; the orchestrator steps 3-4).

  · every old writer of a task row (the pulse's beat, a question, his answer, a died worker, a title, a playbook) sends
    its change to the queue as a signal of the task's owner; a generic `task_patch`/`task_put` never touches the row;
  · its ending (`circuit.settle`) archives it: ONE short-lived pill that names it and the artifacts kept — written once,
    since an archived task takes no more signals — and no row; the result stays in its artifacts;
  · the line it owes him is said once, keyed by its row alone, in one short sentence the genome's rule shapes;
  · a reference to it later finds its pill and reopens what its artifacts kept.
"""
from __future__ import annotations

import pytest

from memory import tasks_store as ts
from nucleo import circuit, queue


@pytest.fixture
def pills(monkeypatch):
    from memory import api as memory
    out = []
    monkeypatch.setattr(memory, "write", lambda text, **kw: out.append((text, kw)))
    return out


def _running(title="find flights to Rome"):
    tid = queue.add("worker", title)
    queue.signal(tid, "start", by="pulse")
    return tid


def test_a_generic_write_never_touches_a_task_of_the_queue():
    tid = _running()
    ts.task_patch(tid, state="done", phase="w_rewritten", title="w_other")
    ts.task_put({"id": tid, "title": "w_put", "goal": "w_put", "state": "failed"})
    row = ts.task_get(tid)
    assert (row["state"], row["phase"], row["title"]) == ("running", None, "find flights to Rome")


def test_the_old_writers_send_their_change_as_a_signal(monkeypatch):
    from nucleo.circuit import ledger, waits
    tid = _running()
    ledger.status_written({"uid": tid, "phase": "w_comparing", "done": 1, "total": 3})
    assert ts.task_get(tid)["phase"] == "w_comparing" and ts.task_get(tid)["progress"]["done"] == 1
    assert waits.waiting(tid, waits.USER_ANSWER, ask_id="a1", ask="aisle or window?")
    row = ts.task_get(tid)
    assert (row["state"], row["ask"], row["waiting_for"]) == ("waiting", "aisle or window?", waits.USER_ANSWER)
    other = queue.add("worker", "next in line")
    waits.resumed(tid)
    assert ts.task_get(tid)["state"] == "pending", "his answer puts it back in its lane, to run when its turn comes"
    assert [r["id"] for r in queue.view()["worker"]["pending"]] == [tid, other], "…at its head"


def test_its_ending_leaves_one_pill_and_no_row(pills):
    tid = _running("a table for four on Friday")
    ts.artifact_put(tid, "result", {"items": [{"title": "w_trattoria"}]})
    circuit.settle(row=tid, state="done", outcome="booked at w_trattoria, 21:00")
    circuit.settle(row=tid, state="done", outcome="again")
    assert ts.task_get(tid) is None and ts.artifact_get(tid, "result"), "no row; the result it paid for stays"
    (text, kw), = pills
    assert text == "a table for four on Friday: booked at w_trattoria, 21:00"
    assert kw["kind"] == "task" and kw["level"] == "short" and kw["meta"]["task_id"] == tid
    assert kw["meta"]["artifacts"] == ["result"] and kw["meta"]["state"] == "done"


def test_a_task_that_left_is_found_by_its_pill(monkeypatch):
    from memory import api as memory
    from nucleo.errands import task_recall
    monkeypatch.setattr(memory, "task_pills", lambda q, limit=15: [
        {"id": 9, "text": "a flat in Leeds: three found", "meta": {"task_id": "t-7", "state": "done"}}])
    got = task_recall.candidates("the flat in Leeds")
    assert [(r["id"], r["title"], r["outcome"]) for r in got] == [("t-7", "a flat in Leeds", "three found")]


def test_a_generic_write_that_meets_a_task_of_the_queue_is_said_with_its_writer(monkeypatch):
    """The SQL guard never drops a change in silence: the refusal is published, naming the fields and the writer."""
    import bus
    said = []
    monkeypatch.setattr(bus, "emit_sync", lambda topic, payload: said.append((topic, payload)))
    tid = _running()
    ts.task_patch(tid, phase="w_forgotten_writer")
    (topic, p), = [x for x in said if x[0] == "queue.refused"]
    assert p["task_id"] == tid and p["fields"] == ["phase"] and "test_a_task_that_ends_leaves_the_queue" in p["writer"]


def test_its_pill_is_written_outside_the_queues_lock(monkeypatch):
    """The pill may embed (a model): written after the row went and the lock was let go, it never holds the queue."""
    import threading

    from memory import api as memory
    free = []

    def write(text, **kw):
        t = threading.Thread(target=lambda: free.append(queue._lock.acquire(blocking=False)
                                                        and (queue._lock.release() or True)))
        t.start()
        t.join()
    monkeypatch.setattr(memory, "write", write)
    tid = _running()
    circuit.settle(row=tid, state="done", outcome="w")
    assert free == [True] and ts.task_get(tid) is None

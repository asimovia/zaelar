"""A task of the queue has ONE writer, and when it ends it is ARCHIVED (INI-078 Q-2, Q-4, Q-8, #5; steps 3-4).

  · every old writer of a task row (the pulse's beat, a question, his answer, a died worker, a title, a playbook) sends
    its change to the queue as a signal of the task's owner; a generic `task_patch`/`task_put` never touches the row;
  · its ending (`circuit.settle`) archives it in place: the row stays, in the state it ended in, with its outcome —
    out of the queue's view, readable by its id, once (an archived task takes no more signals) — and his memory keeps
    ONE short pill of it, written outside the queue's lock; the result stays in its artifacts;
  · a reference to it later finds its row by the same search, with how it ended.
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


def test_its_ending_archives_its_row_in_place_and_leaves_one_pill(pills):
    tid = _running("a table for four on Friday")
    ts.artifact_put(tid, "result", {"items": [{"title": "w_trattoria"}]})
    circuit.settle(row=tid, state="done", outcome="booked at w_trattoria, 21:00")
    circuit.settle(row=tid, state="failed", outcome="again")
    row = ts.task_get(tid)
    assert (row["state"], row["outcome"], row["owner"]) == ("done", "booked at w_trattoria, 21:00", "worker")
    assert row["finished_at"] and ts.artifact_get(tid, "result"), "archived once; the result it paid for stays"
    assert not any(r["id"] == tid for lane in queue.view().values() for st in lane.values() for r in st)
    (text, kw), = pills
    assert text == "a table for four on Friday: booked at w_trattoria, 21:00"
    assert kw["kind"] == "task" and kw["meta"]["task_id"] == tid and kw["meta"]["artifacts"] == ["result"]


def test_a_task_that_ended_is_found_by_the_same_search_with_how_it_ended(pills):
    from nucleo.errands import task_recall
    tid = _running("a flat in Leeds")
    circuit.settle(row=tid, state="done", outcome="three found")
    got = task_recall.candidates("the flat in Leeds")
    assert [(r["id"], r["state"], r["outcome"]) for r in got] == [(tid, "done", "three found")]


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
    """The pill may embed (a model): written after the row was archived and the lock let go, it never holds the queue."""
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
    assert free == [True] and ts.task_get(tid)["state"] == "done"

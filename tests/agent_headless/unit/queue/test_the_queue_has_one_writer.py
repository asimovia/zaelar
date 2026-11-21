"""The queue of his tasks has ONE writer, and a signal is applied whole, in the order it arrived (INI-078, Q-4).

`nucleo/queue.signal` is the only door that moves a task of the queue: a jump its table does not list is refused and
said, a task that already left takes no signal at all («finish a cancelled one» is exactly that case), two signals on
the same field leave the last one, and signals racing from several threads come out — rows and events — in one order.
"""
from __future__ import annotations

import threading

import pytest

from memory import tasks_store as ts
from nucleo import queue


@pytest.fixture
def said(monkeypatch):
    from voice import observer
    out = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None:
                        out.append((label, dict(extra or {}))) if kind == "queue" else None)
    return out


def _refused(said):
    return [e for label, e in said if label == "queue/refused"]


def test_a_jump_the_table_does_not_list_is_refused_and_said(said):
    tid = queue.add("worker", "find a flat in Leeds")
    assert not queue.signal(tid, "done", by="owner"), "a pending task cannot end done"
    assert not queue.signal(tid, "wait", by="owner"), "nor wait for him before it ran"
    assert ts.task_get(tid)["state"] == "pending"
    assert queue.signal(tid, "start", by="pulse") and queue.signal(tid, "wait", by="owner", ask="which area?")
    assert not queue.signal(tid, "progress", by="owner"), "a task waiting for him makes no progress"
    assert not queue.signal(tid, "start", by="nobody")
    assert [e["signal"] for e in _refused(said)] == ["done", "wait", "progress", "start"]
    assert ts.task_get(tid)["state"] == "waiting" and ts.task_get(tid)["ask"] == "which area?"


def test_a_task_that_left_takes_no_signal(said):
    tid = queue.add("send", "tell Ana I am late")
    assert queue.signal(tid, "cancelled", by="him")
    assert ts.task_get(tid) is None, "it left the queue: archived, no finished state"
    assert not queue.signal(tid, "done", by="owner"), "finishing a cancelled task"
    assert not queue.signal("nobody-knows-this-id", "start", by="pulse")
    assert [e["why"] for e in _refused(said)] == ["not in the queue"] * 2


def test_two_signals_on_the_same_field_leave_the_last():
    tid = queue.add("processor", "tidy the week's agenda")
    queue.signal(tid, "start", by="pulse")
    queue.signal(tid, "progress", by="owner", phase="reading the agenda")
    queue.signal(tid, "progress", by="pulse", phase="stalled?")
    assert ts.task_get(tid)["phase"] == "stalled?"


def test_racing_signals_apply_one_at_a_time_in_one_order(said):
    tid = queue.add("worker", "compare three monitors")
    queue.signal(tid, "start", by="pulse")
    go = threading.Barrier(8)

    def beat(i):
        go.wait()
        for k in range(10):
            queue.signal(tid, "progress", by="owner", phase=f"{i}-{k}")
    threads = [threading.Thread(target=beat, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    applied = [label for label, e in said if label == "queue/progress"]
    assert len(applied) == 80, "no signal lost"
    last = [e for label, e in said if label == "queue/progress"][-1]
    assert ts.task_get(tid)["phase"] == last["changed"]["phase"], "the row holds the last signal the events say was applied"


def test_back_and_urgent_go_first_and_a_move_lands_where_he_said():
    a, b, c = (queue.add("worker", t) for t in ("a", "b", "c"))
    order = lambda: [r["id"] for r in queue.view()["worker"]["pending"]]   # noqa: E731
    assert order() == [a, b, c]
    u = queue.add("worker", "urgent one", urgent=True)
    assert order() == [u, a, b, c]
    assert queue.signal(c, "move", by="him", before=a) and order() == [u, c, a, b]
    assert queue.signal(b, "move", by="him", before="first") and order()[0] == b
    assert not queue.signal(a, "move", by="him", before="not-a-task")
    assert queue.signal(a, "start", by="pulse") and queue.signal(a, "wait", by="owner", ask="?")
    assert queue.signal(a, "back", by="him") and order()[0] == a, "his answer puts it back at the head of its lane"


def test_every_task_has_a_short_number_that_is_never_given_again():
    """`#n` is how the model and his screen name a task alike: one per install, in order, never reused — not even once
    the task with the highest number left the queue (its row is deleted, so the highest number on disk goes back)."""
    a = queue.add("worker", "first")
    b = queue.add("send", "second")
    na, nb = ts.task_get(a)["num"], ts.task_get(b)["num"]
    assert nb == na + 1, "one counter for every lane"
    assert queue.signal(b, "cancelled", by="him") and ts.task_get(b) is None
    c = queue.add("processor", "third")
    assert ts.task_get(c)["num"] == nb + 1, "the number of a task that left is never given again"
    assert [r["num"] for r in queue.view()["worker"]["pending"]] == [na]

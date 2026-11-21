"""OPEN is the queue, each task by its #number, and the model acts on a task by that number (INI-078 segregation S3).

The block the model reads and the column he looks at are two views of ONE queue in ONE order: each task by its `#n`,
its owner, its state and what it does; a task waiting for him with its question word for word and its declared
answers; at most twelve lines and the rest counted. The acts name a task by its number — `task_say` (his words to
what it does), `task_priority`, `task_move`, `stop_task` — and a number that is not open fails and gives OPEN back,
never a guess. A widget's held row resumes through the widget's own act.
"""
from __future__ import annotations

import pytest

from memory import tasks_store as ts
from nucleo import queue
from nucleo.conversation_host import acts_tasks, open_block


def _task(title, state="pending", **ask):
    tid = queue.add("worker", title)
    if state in ("running", "waiting"):
        queue.signal(tid, "start", by="pulse")
    if state == "waiting":
        queue.signal(tid, "wait", by="owner", **ask)
    return tid, ts.task_get(tid)["num"]


def test_open_shows_each_task_by_its_number_and_its_question_word_for_word():
    _, n1 = _task("flights Madrid-Rome", "running")
    _, n2 = _task("a table for four", "waiting", ask="9:00 or 9:30?", waiting_for="user_answer")
    _, n3 = _task("tidy the agenda")
    lines = open_block.text().split("\n")
    assert lines[0].startswith(f"#{n1} · worker · running · flights Madrid-Rome")
    assert lines[1].startswith(f"#{n2} · worker · waiting · a table for four · ASKED (") and "«9:00 or 9:30?»" in lines[1]
    assert lines[2] == f"#{n3} · worker · pending · tidy the agenda · 1st in line"


def test_fifty_pending_are_twelve_lines_and_the_rest_counted():
    for i in range(50):
        queue.add("worker", f"w{i}")
    lines = open_block.text().split("\n")
    assert len(lines) == 13 and lines[-1] == "… and 38 more pending"


def test_a_number_that_is_not_open_fails_and_gives_open_back():
    _task("w1")
    for args, act in (({"task": "#999"}, acts_tasks._stop), ({"task": "#999"}, acts_tasks._priority),
                      ({"task": "#999", "before": "first"}, acts_tasks._move), ({"task": "#999"}, acts_tasks._say)):
        r = act(args)
        assert r.status == "failed" and r.data["reason"] == "not_open" and "w1" in r.data["open"]


def test_urgent_and_move_and_stop_by_number():
    _, a = _task("a")
    tb, b = _task("b")
    _, c = _task("c")
    assert acts_tasks._priority({"task": f"#{c}", "urgent": True}).status == "ok"
    order = lambda: [r["num"] for r in queue.view()["worker"]["pending"]]   # noqa: E731
    assert order() == [c, a, b]
    assert acts_tasks._move({"task": f"#{b}", "before": f"#{a}"}).status == "ok" and order() == [c, b, a]
    assert acts_tasks._stop({"task": f"#{b}"}).status == "ok" and ts.task_get(tb)["state"] in ts.DONE_STATES and order() == [c, a]


def test_his_words_reach_the_task_he_numbered(monkeypatch):
    from nucleo.switchboard import act, board
    tid, n = _task("a table for four", "waiting", ask="9:00 or 9:30?", waiting_for="user_answer")
    monkeypatch.setattr(board, "open_processes", lambda: [{"key": tid, "dispatch": "", "title": "a table for four",
                                                           "state": "waiting", "question": "9:00 or 9:30?"}])
    got = []
    monkeypatch.setattr(act, "deliver", lambda p, text, kind: got.append((p["key"], text, kind)) or True)
    r = acts_tasks._say({"task": f"#{n}", "text": "9:30", "is": "answer"})
    assert r.status == "ok" and got == [(tid, "9:30", act.OTHER)]
    acts_tasks._say({"task": str(n), "text": "yes", "is": "yes"})
    assert got[-1][2] == act.YES


def test_his_column_is_the_queue_in_opens_order_with_its_numbers():
    from nucleo.circuit import ledger
    _task("runs", "running")
    _task("later")
    _task("first", "pending")
    queue.signal(queue.view()["worker"]["pending"][-1]["id"], "priority", by="him", urgent=True)
    nums = [r["num"] for r in ledger.board("live")]
    assert nums == [r["num"] for r in queue.ordered()] and [line.split(" ·")[0] for line in
                                                           open_block.text().split("\n")] == [f"#{x}" for x in nums]


def test_a_widgets_held_row_resumes_through_its_own_act(monkeypatch):
    from nucleo import pending_work
    from nucleo.acts import data_ops
    row = {"id": "mail:1", "source": "widget", "widget": "w_mail", "title": "a held draft",
           "resume": {"action": "send_draft", "payload": {"id": 1}}}
    monkeypatch.setattr(pending_work, "by_ids", lambda ids: [row])
    ran = []

    async def dispatch_and_report(widget, action, payload):
        ran.append((widget, action, payload))
    monkeypatch.setattr(data_ops, "dispatch_and_report", dispatch_and_report)
    monkeypatch.setattr("nucleo.conversation_host.acts_widget._on_engine_loop", lambda coro: coro)
    r = acts_tasks._resume({"ids": ["mail:1"]})
    assert ran == [("w_mail", "send_draft", {"id": 1})] and r.status == "ok"


@pytest.fixture(autouse=True)
def _no_live_sessions(monkeypatch):
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    monkeypatch.setattr("nucleo.conversation_host.route.last_said", lambda: ("", 0.0))

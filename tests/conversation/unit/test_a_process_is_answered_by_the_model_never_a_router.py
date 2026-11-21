"""A process of his is answered by the model, never by a router before it (node 13.143, E7d-7, R-3).

With a process in course or waiting on his answer, his words are no longer routed before the model: the host's
`Route` only lets an open message draft read them first. The model sees the processes in TASKS and answers one with
`task_answer`, naming it by an id TASKS gave (its row, its session or its question): his words go by the one delivery
door, a plain yes or no deciding what it held; an id nobody holds fails naming the open ones.
"""
from __future__ import annotations

import asyncio

from nucleo.conversation_host import acts_tasks, routing


def test_with_a_process_open_and_no_draft_the_route_takes_nothing(monkeypatch):
    from nucleo.send import draft
    from nucleo.switchboard import board, route
    monkeypatch.setattr(draft, "current", lambda: None)
    monkeypatch.setattr(board, "open_processes", lambda: [{"key": "u1", "state": "waiting", "ask_id": "a1"}])
    monkeypatch.setattr(route, "take", lambda *a, **k: (_ for _ in ()).throw(AssertionError("routed before the model")))
    assert asyncio.run(routing.HostRoute().take("acct", "w_yes do it")) is None


def test_the_model_answers_the_process_it_names_by_the_one_delivery_door(monkeypatch):
    from nucleo.switchboard import act, board
    procs = [{"key": "u1", "dispatch": "d7", "title": "w_flat", "state": "waiting", "ask_id": "a1"},
             {"key": "u2", "dispatch": "", "title": "w_car", "state": "running", "ask_id": ""}]
    delivered = []
    monkeypatch.setattr(board, "open_processes", lambda: procs)
    monkeypatch.setattr(act, "deliver", lambda p, text, kind: delivered.append((p["key"], text, kind)) or True)
    monkeypatch.setitem(routing._last, "said", "w_yes book it")
    assert acts_tasks.run("answer", {"task": "d7", "decision": "yes"}).data["task"] == "u1"
    assert acts_tasks.run("answer", {"task": "u2", "text": "w_cheaper"}).status == "ok"
    assert delivered == [("u1", "w_yes book it", act.YES), ("u2", "w_cheaper", act.OTHER)]
    other = acts_tasks.run("answer", {"task": "w_invented"})
    assert other.status == "failed" and [p["id"] for p in other.data["open"]] == ["u1", "u2"] and len(delivered) == 2

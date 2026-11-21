"""A task that ENDED a moment ago is still listed with what is open, and his words to it bring the SAME task back
(INI-078 #5, commit b).

An ended task is archived in place; for a while — the recent window, a rule with readers (genesis
`tasks.recent_window_min`) — OPEN lists it by its #n with how it ended. His words to it («not these, others») are the
model's `task_say(#n)`: the same task is relaunched on its own row by the one continuation door (`task_uid`), and the
queue reopens it at the head of its lane — its sheet, its brief, what it kept. A message that went is not brought
back; a task older than the window is not listed, so no number reaches it.
"""
from __future__ import annotations

import time

import pytest

from memory import tasks_store as ts
from nucleo import circuit, queue
from nucleo.conversation_host import acts_tasks, open_block


def _ended(title="w_ski boots under 300", outcome="five found", owner="worker"):
    tid = queue.add(owner, title, goal=title)
    queue.signal(tid, "start", by="pulse")
    circuit.settle(row=tid, state="done", outcome=outcome)
    return tid, ts.task_get(tid)["num"]


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    from memory import api as memory
    from nucleo import dispatch
    monkeypatch.setattr(memory, "write", lambda *a, **k: None)
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    monkeypatch.setattr("nucleo.conversation_host.route.last_said", lambda: ("", 0.0))


def test_a_task_that_ended_a_moment_ago_is_listed_in_OPEN_by_its_number():
    _, n = _ended()
    assert [r["num"] for r in queue.recent()] == [n]
    line = open_block.text().split("\n")[-1]
    assert line.startswith(f"#{n} · worker · ended done (") and "w_ski boots under 300" in line and "«five found»" in line
    later = time.time() + queue.recent_window_s() + 60
    assert queue.recent(later) == [] and open_block.text(later) == "", "past the window it is no longer listed"


def test_his_words_to_it_bring_the_same_task_back_at_the_head_of_its_lane(monkeypatch):
    from nucleo.acts import errand
    from nucleo.circuit import ledger
    from nucleo.conversation_host import routing
    tid, n = _ended()
    other = queue.add("worker", "w_next in line")
    seen = {}

    def escalate(request, context=None):                       # the one errand door: here, only its ledger half
        seen.update(request=request, context=dict(context or {}))

        class Rec:
            task_id, title, kind, surface, sheet, goal = "9", "", "research", "", "", request
        ledger.opened(Rec(), context)
        return 9
    monkeypatch.setattr(errand, "escalate_to_slowbrain", escalate)
    monkeypatch.setitem(routing._last, "said", "w_not these, cheaper ones")
    r = acts_tasks._say({"task": f"#{n}", "text": "w_model words", "is": "add"})
    assert r.status == "ok" and r.data == {"task": f"#{n}", "reopened": True, "title": "w_ski boots under 300"}
    assert seen["context"]["task_uid"] == tid and "w_not these, cheaper ones" in seen["request"], "his own words"
    row = ts.task_get(tid)
    assert (row["state"], row["outcome"], row["finished_at"]) == ("pending", "", None), "the SAME row, reopened"
    assert [r["id"] for r in queue.view()["worker"]["pending"]] == [tid, other], "…at the head of its lane"
    assert queue.recent() == []


def test_a_message_that_went_is_not_brought_back_and_an_old_task_has_no_number():
    _, n = _ended("✉ w_ana · «w_late»", "sent", owner="send")
    r = acts_tasks._say({"task": f"#{n}", "is": "add"})
    assert r.status == "failed" and r.data["reason"] == "archived" and r.data["outcome"] == "sent"
    tid, old = _ended("w_flights last month")
    ts._db_mod.get_db().execute("UPDATE tasks SET finished_at=? WHERE id=?",
                                (int(time.time() - queue.recent_window_s() - 60), tid))
    assert acts_tasks._say({"task": f"#{old}", "is": "add"}).data["reason"] == "not_open"

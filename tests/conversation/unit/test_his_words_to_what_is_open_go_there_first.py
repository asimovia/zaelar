"""His words to something of his that is open go there first, by the host's doors (node 13.128, INI-078 F2 step 3).

Before any model is called, the batch's words are offered to the host's `Route` (plan F2 §3): the doors that already
decide whose they are — the switchboard over the processes in course and the rows waiting on his answer. One that
takes them answers with its line: said, the request closed, no model paid. Nobody takes them, the doors fail or are
late: the model answers, as always. And the task acts reach their own doors: an errand by the one errand gateway, a
stop by the one cancel door, a resume only among the DECLARED pending rows.
"""
from __future__ import annotations

import pytest

from conversation.testing.scripted_model import reply
from conversation.ports import Done
from tests.conversation.unit.convkit import Harness


class _Route:
    def __init__(self, line):
        self.line, self.seen = line, []

    async def take(self, account, text):
        self.seen.append(text)
        if isinstance(self.line, Exception):
            raise self.line
        return self.line


def _with(store, route):
    h = Harness(store, grace=False)
    h.conv.route = route
    h.model.default = lambda ids: [reply("w9"), Done()]
    return h


def test_words_an_open_process_takes_are_answered_by_its_door_and_no_model(store):
    route = _Route("w_heard")
    h = _with(store, route)
    h.utter([(["w1", "w2"], 0)])
    h.settle(3000)
    assert route.seen == ["w1 w2"] and not h.model.calls
    assert [o.text for o in h.mouth.orders] == ["w_heard"] and [lab for lab, _ in h.closes()] == ["answered"]


@pytest.mark.parametrize("line", [None, OSError("w_down")], ids=["nobody", "failing"])
def test_words_nobody_takes_or_a_failing_door_go_to_the_model(store, line):
    route = _Route(line)
    h = _with(store, route)
    h.typed("w1", 0)
    h.settle(3000)
    assert route.seen == ["w1"] and len(h.model.calls) == 1 and [o.text for o in h.mouth.orders] == ["w9"]


def test_the_task_acts_reach_their_one_doors(monkeypatch):
    from nucleo import dispatch, pending_work
    from nucleo.acts import errand
    from nucleo.conversation_host import acts_tasks
    from nucleo.flash import resume_turn
    from nucleo.request import stop_row
    seen = {}
    monkeypatch.setattr(errand, "escalate_to_slowbrain", lambda req, context=None: seen.setdefault("errand", req) and 7)
    monkeypatch.setattr(dispatch, "cancel_soon", lambda which: seen.setdefault("stop", which) and ["t3"])
    monkeypatch.setattr(stop_row, "stopped_by_his_turn", lambda tids: seen.setdefault("ended", tids))
    monkeypatch.setattr(pending_work, "rows", lambda: [{"id": "p1", "title": "w_flat"}])
    monkeypatch.setattr(pending_work, "by_ids", lambda ids: [r for r in [{"id": "p1"}] if r["id"] in ids])
    monkeypatch.setattr(resume_turn, "resume", lambda rows, **kw: [r["id"] for r in rows])
    assert acts_tasks.run("start", {"request": "w_find_a_flat"}).data == {"task": 7, "started": "w_find_a_flat"}
    assert acts_tasks.run("stop", {"task": "t3"}).data == {"stopped": ["t3"]} and seen["ended"] == ["t3"]
    assert acts_tasks.run("resume", {"ids": ["p1"]}).data == {"resumed": ["p1"]}
    other = acts_tasks.run("resume", {"ids": ["w_invented"]})                   # only a DECLARED pending row
    assert other.status == "failed" and other.data["pending"] == [{"id": "p1", "title": "w_flat"}]


def test_an_open_draft_reads_his_words_first_and_a_message_goes_to_its_owner(monkeypatch):
    """A message has ONE owner: with a draft open, his sentence is read against it before the switchboard; the model's
    message call — or a widget's message act — is handed to the owner with HIS words, and its line is what is said."""
    import asyncio

    from nucleo.conversation_host import acts, routing
    from nucleo.send import draft, owner, turn
    from nucleo.switchboard import board
    seen = {}

    async def take(text, **kw):
        seen["take"] = text
        return True, "w_to_whom?"

    async def intake(said, hint=None, last_line="", before=None, by="call"):
        seen["intake"] = (said, dict(hint or {}), by)
        return "w_read_back?"
    monkeypatch.setattr(owner, "take", take)
    monkeypatch.setattr(owner, "intake", intake)
    monkeypatch.setattr(board, "open_processes", lambda: [])
    monkeypatch.setattr(draft, "current", lambda: object())
    assert asyncio.run(routing.HostRoute().take("a", "w_tell_her_yes")) == "w_to_whom?"
    got = asyncio.run(routing.send({"to": "w_ana", "text": "w_late"}))
    assert got.data == {"say": "w_read_back?"} and seen["intake"] == ("w_tell_her_yes", {"to": "w_ana", "text": "w_late"},
                                                                      "call")
    monkeypatch.setattr(turn, "is_message", lambda w, a, p=None: True)
    from nucleo.flash import widget_read
    monkeypatch.setattr(widget_read, "resolve", lambda named, text="": "w_chat")
    monkeypatch.setattr(acts, "_offered", lambda base: {"reply": {}})
    monkeypatch.setattr(acts, "_open", lambda: [])
    asyncio.run(acts.widget_act({"widget": "w_chat", "action": "reply", "payload": {"text": "w_ok"}}, "x1"))
    assert seen["intake"][1] == {"text": "w_ok", "_act": "reply"}               # handed over, never run by the card


def test_a_note_for_support_keeps_his_words_and_does_nothing_else(monkeypatch):
    from nucleo.conversation_host import acts_tasks, routing
    from nucleo.input import support_note
    kept = []
    monkeypatch.setattr(support_note, "_write", lambda note, label, **kw: kept.append(note))
    monkeypatch.setitem(routing._last, "said", "w_the_latency_again")
    assert acts_tasks.run("note", {"note": "w_model_words"}).data == {"kept": True}
    assert kept == ["w_the_latency_again"]                                   # his words, never the model's rewording

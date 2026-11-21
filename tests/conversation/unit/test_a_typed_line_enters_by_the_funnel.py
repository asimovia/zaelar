"""A typed line of a switched session enters by the funnel (node 13.44, v3.1 B5).

The manager is the only path (INI-078 F2): the voice holder's data channel and `/api/chat` (`receive_typed`) hand the
line to the manager's funnel and NOT to the old typed lane — no second wait behind a voice: the inbox orders it — and
the text channel (`run_turn`) answers in its own shape with the request's ids. When the manager may not run, nothing
else answers: the line is not routed anywhere and the reason is on his screen. The funnel's guards
hold for every entry: a `LOG:` line is a note, a stopped engine takes nothing. The net: a line that still reaches
the old turn's reply in a switched session opens no turn, is counted and handed to the funnel. End to end, a typed
line is answered by the manager in its own thread, on the wall, and the proof counts its run.
"""
from __future__ import annotations

import asyncio

import pytest

from conversation.ports import Done
from conversation.testing.scripted_model import ScriptedModel, reply
from nucleo.conversation_host import entry, proof, sessions, switch
from voice.engine.pipeline import agent_events


class _Session:
    pass


@pytest.fixture
def switched(monkeypatch):
    monkeypatch.setenv("ZAELAR_HOLD_OUTBOUND", "all")
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    from config import settings
    monkeypatch.setattr(settings, "_read", lambda: {})
    yield monkeypatch
    sessions.close_all()


@pytest.fixture
def refused(monkeypatch):
    monkeypatch.delenv("ZAELAR_HOLD_OUTBOUND", raising=False)          # too little held: the manager may not run
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    return monkeypatch


def _doors(monkeypatch):
    seen = {"old": [], "new": []}
    monkeypatch.setattr(agent_events, "_route_typed", lambda txt, **kw: seen["old"].append(txt))
    monkeypatch.setattr(entry, "typed", lambda txt, dev="", **kw: seen["new"].append(txt) or {"ok": True})
    return seen


def test_refused_the_data_channel_line_goes_nowhere_else(refused):
    seen = _doors(refused)
    agent_events.receive_typed("w1", _emit=lambda *a, **k: None, session=_Session())
    assert seen == {"old": [], "new": []}, "no old path: the reason is on his screen, and silence"


def test_on_it_enters_by_the_funnel_and_never_by_the_old_lane(switched):
    seen = _doors(switched)
    s = _Session()
    agent_events.receive_typed("w1", _emit=lambda *a, **k: None, session=s)
    agent_events.receive_typed("w2", _emit=lambda *a, **k: None, session=s)
    assert seen == {"old": [], "new": ["w1", "w2"]}


def test_the_decision_is_read_once_per_session(switched):
    seen = _doors(switched)
    s = _Session()
    agent_events.receive_typed("w1", _emit=lambda *a, **k: None, session=s)
    switched.delenv("ZAELAR_HOLD_OUTBOUND")                  # the install changes halfway: not this session
    agent_events.receive_typed("w2", _emit=lambda *a, **k: None, session=s)
    assert seen["new"] == ["w1", "w2"]


def test_the_guards_hold_for_every_entry(switched):
    """Checked off the caller's loop: in a worker thread for the text channel, which answers with them, and on the
    conversation's side for the data channel, where a guarded line is never heard."""
    from nucleo import runstate
    from nucleo.input import support_note
    switched.setattr(support_note, "record", lambda text, dev: text.startswith("LOG:"))
    assert asyncio.run(entry.typed_and_wait("LOG: w1")) == {"ok": True, "note": True}
    switched.setattr(runstate, "stopped", lambda: True)
    assert asyncio.run(entry.typed_and_wait("w1")) == {"ok": False, "reason": "stopped"}

    class _Conv:
        heard: list = []

        def hear(self, sig):
            self.heard.append(sig)

    conv = _Conv()
    switched.setattr(entry, "_hand", lambda fn: fn(conv))
    entry.typed("w2")
    assert conv.heard == []                                             # stopped: the line is not heard
    switched.setattr(runstate, "stopped", lambda: False)
    entry.typed("w3")
    assert [s.text for s in conv.heard] == ["w3"]


class _Client:
    def __init__(self):
        self.posts = []

    def post_soon(self, path, body):
        self.posts.append(path)

    def env_diff(self):
        return {}


def test_the_net_opens_no_old_turn_and_hands_the_line_over(switched):
    from voice.remote_session import RemoteSession
    got = []
    switched.setattr(entry, "typed", lambda txt, dev="", **kw: got.append(txt) or {"ok": True})
    proof._reset_for_tests()
    rs = RemoteSession(_Client())
    rs.generate_reply("w1")
    from nucleo.conversation_host import boot
    assert rs.client.posts == [] and got == ["w1"]
    assert proof.report(boot.account())["counters"]["legacy_turn_attempts"] == 1


def test_refused_the_net_opens_no_old_reply_either(refused):
    from voice.remote_session import RemoteSession
    rs = RemoteSession(_Client())
    rs.generate_reply("w1")
    assert rs.client.posts == []


class _Model:
    """The voice's model, scripted: a reply, through the Model port's own shape."""

    def __init__(self, *a, **k):
        self._m = ScriptedModel(default=lambda ids: [reply("w9"), Done()])

    def stream(self, prompt, tools, *, run_id, model_id):
        return self._m.stream(prompt, tools, run_id=run_id, model_id=model_id)


def test_end_to_end_the_text_channel_is_answered_by_the_manager(switched):
    from nucleo.cli import turn
    from nucleo.conversation_host import boot, model
    switched.setattr(model, "FastModel", _Model)
    proof._reset_for_tests()
    got = asyncio.run(turn.run_turn("w1", sid="t1", door=True))
    assert got["ok"] and got["reply"] == "w9" and got["conv"]["close"] == "answered", got
    again = asyncio.run(turn.run_turn("w2", sid="t1", door=True))
    assert again["reply"] == "w9"
    assert proof.report(boot.account())["counters"]["manager_runs"] == 2
    assert sessions.get(boot.account()) is not None                  # one conversation, kept for the account


def test_opening_the_conversation_never_waits_on_the_callers_loop(switched):
    """Opening takes the lease — a write on the shared database, under a lock other writers have held for seconds. With
    that lock held, a typed line is handed over at once; the conversation opens on a thread of its own and every line
    handed meanwhile is answered, in order."""
    import threading
    import time

    from memory import db as memdb
    from nucleo.cli import turn
    from nucleo.conversation_host import boot, model
    switched.setattr(model, "FastModel", _Model)
    sessions.close_all()
    lock, held = memdb.get_db()._lock, threading.Event()
    from nucleo import runstate

    def stopped_reading_the_database() -> bool:      # what an uncached read of the engine's state does
        with lock:
            return False

    switched.setattr(runstate, "stopped", stopped_reading_the_database)

    def hold():
        with lock:
            held.set()
            time.sleep(1.5)

    t = threading.Thread(target=hold)
    t.start()
    held.wait(2)
    t0 = time.monotonic()
    entry.typed("w1", "d9")
    entry.typed("w2", "d9")
    assert time.monotonic() - t0 < 0.3                                  # handed over, not waited for
    t.join()
    got = asyncio.run(turn.run_turn("w3", sid="t2", door=True))
    assert got["ok"] and proof.report(boot.account())["counters"]["manager_runs"] >= 1

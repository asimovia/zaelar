"""With the manager for his text only, a typed line still cuts the voice, and his «stop» stops it (node 13.104, V2-941,
v3.1 B7l — the audit of B7j–B8g, TJ-1).

On the old path a typed line is a barge-in: the speech in course stops and a turn still composing is superseded before
it is answered (the 2026-11-14 audit, failures 8 and 9). With `conversation_manager: "text"` the line went to the
manager BEFORE that, so the old voice went on talking while the manager answered on the wall — two brains at once —
and the manager's stop found no voice of its own to stop. Now, with the voice on the old path:

  · the typed line cuts the speech in course first — locally, or in the voice process by the stop door (`/voice/say`,
    `cut`, no text) — supersedes a turn still composing, and only then goes to the manager;
  · the manager's stop goes to the old voice through the same door;
  · with the voice the manager's too, the manager does both itself: the line is not cut twice.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nucleo.conversation_host import entry, switch, voice_mouth, voice_session
from voice.engine.pipeline import agent_events


class _Speech:
    allow_interruptions, interrupted = True, False

    def __init__(self, log):
        self.log = log

    def done(self):
        return False

    def interrupt(self):
        self.log.append("cut")
        self.interrupted = True


class _Client:
    _loop = object()

    def __init__(self, log):
        self.log = log

    def post_soon(self, path, payload=None):
        self.log.append((path, payload))


@pytest.fixture
def text_only(monkeypatch):
    from nucleo.input import typed
    log: list = []
    monkeypatch.setattr(switch, "typed_on", lambda session=None: True)
    monkeypatch.setattr(entry, "typed", lambda txt, dev="", **kw: log.append(("manager", txt)))
    monkeypatch.setattr(typed, "note_typed_cut", lambda: log.append("superseded"))
    return log


def _session(log, voice_on=False):
    s = SimpleNamespace(current_speech=_Speech(log))
    voice_session.started(s, {"conv": voice_on, "conv_by": "account", "conv_why": "" if voice_on else switch.TEXT_ONLY})
    return s


def test_a_typed_line_cuts_the_old_voice_before_the_manager_takes_it(text_only):
    agent_events.receive_typed("w1", _emit=lambda *a, **k: None, session=_session(text_only))
    assert text_only == ["superseded", "cut", ("manager", "w1")]


def test_in_the_voice_process_the_cut_is_the_stop_door(text_only):
    remote = SimpleNamespace(CUTS_IN_VOICE_PROCESS=True, client=_Client(text_only))
    voice_session.started(remote, {"conv": False, "conv_by": "account", "conv_why": switch.TEXT_ONLY})
    agent_events.receive_typed("w1", _emit=lambda *a, **k: None, session=remote)
    assert text_only == ["superseded", ("/voice/say", {"text": "", "cut": True}), ("manager", "w1")]


def test_with_the_voice_the_managers_too_the_line_is_not_cut_here(text_only):
    agent_events.receive_typed("w1", _emit=lambda *a, **k: None, session=_session(text_only, voice_on=True))
    assert text_only == [("manager", "w1")]


def test_the_managers_stop_stops_the_old_voice(monkeypatch):
    from voice import remote_session as rs
    log: list = []
    old = SimpleNamespace()
    voice_session.started(old, {"conv": False, "conv_by": "account", "conv_why": switch.TEXT_ONLY})
    monkeypatch.setitem(rs._M, "session", old)
    monkeypatch.setitem(rs._M, "client", _Client(log))
    assert voice_mouth.stop() and log == [("/voice/say", {"text": "", "cut": True})]
    monkeypatch.setitem(rs._M, "session", None)                          # no voice at all: nothing to stop
    assert not voice_mouth.stop()

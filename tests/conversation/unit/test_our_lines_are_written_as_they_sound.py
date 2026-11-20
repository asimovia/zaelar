"""Our lines are written as they sound, with the old turn's rows (node 13.114, V2-941, plan v3.2 C2/C4/C5).

  · a line SHOWN (no voice session of the manager) is the `transcript` row, role assistant, at once and whole;
  · a line SAID is announced owed (`brain` reply, role assistant, its trace) and no row yet; when its voice starts the
    line's trace is the voice's, so the `bot_speech` the body replays for it carries it (the wall paints the line
    then); when it ends its `transcript` row is written with what SOUNDED — cut to `heard_chars`, whole when unknown —
    and every ack still reaches the conversation, in order;
  · a notice the manager says is written by the mouth alone (the claimed `notify` paints nothing: 13.47).

Disarms seen red: the owed announcement written as the row; the trace not adopted at the start; the row written whole
whatever sounded.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from conversation.mouth import SayEnded, SayStarted
from nucleo.conversation_host import mouth as M


@pytest.fixture
def log(monkeypatch):
    from voice import observer
    out = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None, piece=None:
                        out.append((kind, label, text, role, dict(extra or {}))))
    return out


def _order(text="w1 w2 w3 w4", channels=frozenset({"voice", "text"})):
    return SimpleNamespace(say_id="s_000001", text=text, channels=channels, endpoint="holder",
                           request_id="r_iv_000001")


class _Voice:
    def __init__(self):
        self.ack = None

    def speak(self, order, ack):
        self.ack = ack
        return True


def _mouth(voice=None):
    acks = []
    m = M.WallMouth(SimpleNamespace(now_ms=lambda: 5), voice=voice, ack_later=acks.append)
    m.ack = acks.append
    return m, acks


def test_a_line_shown_is_its_row_at_once(log):
    m, acks = _mouth()
    asyncio.run(m.say(_order(channels=frozenset({"text"}))))
    assert [(k, t, x["trace"]) for k, _l, t, _r, x in log] == [("transcript", "w1 w2 w3 w4", "iv_000001")]
    assert [a.source for a in acks if isinstance(a, SayEnded)] == ["shown"]


@pytest.mark.parametrize("heard, outcome, row", [(5, "cut", "w1 w2"), (None, "unknown", "w1 w2 w3 w4"),
                                                 (11, "played", "w1 w2 w3 w4")])
def test_a_line_said_is_owed_then_written_with_what_sounded(log, heard, outcome, row):
    from voice import trace
    voice = _Voice()
    m, acks = _mouth(voice)
    asyncio.run(m.say(_order()))
    assert [(k, r, x["trace"]) for k, _l, _t, r, x in log] == [("brain", "assistant", "iv_000001")]
    assert "reply" in log[0][1] and log[0][2] == "w1 w2 w3 w4"
    voice.ack(SayStarted("s_000001", 10))
    assert trace.active() == "iv_000001", "the voice's own state events carry the line's trace from its start"
    voice.ack(SayEnded("s_000001", outcome, heard, 20, "holder"))
    rows = [(t, x["outcome"]) for k, _l, t, r, x in log if k == "transcript"]
    assert rows == [(row, outcome)]
    assert [type(a).__name__ for a in acks] == ["SayStarted", "SayEnded"]


def test_the_bot_speech_the_body_replays_carries_the_lines_trace(log, monkeypatch):
    from nucleo.conversation_host import switch
    from voice import remote_session as rs
    monkeypatch.setitem(rs._M, "session", SimpleNamespace(_conversation_switch=switch.Decision(True, "voice")))
    voice = _Voice()
    m, _acks = _mouth(voice)
    asyncio.run(m.say(_order()))
    voice.ack(SayStarted("s_000001", 10))
    rs.handle({"k": "state", "state": "speaking"})
    speaking = [x for k, lab, _t, _r, x in log if k == "bot_speech" and lab == "speaking"]
    assert speaking and speaking[0].get("trace") == "iv_000001"

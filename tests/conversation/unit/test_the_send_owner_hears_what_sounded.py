"""The send owner hears what of our line SOUNDED, and reads his answer against it (node 13.144, C1).

A message draft's go-ahead answers only a confirmation he HEARD (`send.heard`). The manager's mouth tells the owner,
at each line's end, what of it sounded (or that it was shown whole on his screen): a confirmation heard to its end is
heard, one his voice cut before it is not. And the manager hands the owner his sentence with our last line heard and his
sentences before it — what a «yes» or «I already told you I confirm» is read against.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from conversation.mouth import SayEnded, SayStarted
from nucleo.conversation_host import mouth, routing

CONFIRM = "w_shall I send it to w_ana?"


def _draft(monkeypatch):
    from nucleo.send import draft, heard
    d = SimpleNamespace(confirm_line=CONFIRM, heard=False, heard_at=0, heard_mono=0)
    monkeypatch.setattr(draft, "current", lambda: d)
    monkeypatch.setattr(heard, "_talking", lambda: False)
    return d


def _say(text, heard_chars, monkeypatch):
    from nucleo.conversation_host import wall
    monkeypatch.setattr(wall, "ours", lambda *a, **k: None)
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)
    order = SimpleNamespace(say_id="s1", text=text, request_id="r_i1", channels=frozenset({"voice"}), endpoint="d1",
                            notice_key=None, trace="T1", run_id="run1")
    ack = mouth.WallMouth(clock=None)._sounded(order)
    ack(SayStarted("s1", 10))
    ack(SayEnded("s1", "played" if heard_chars is None else "cut", heard_chars, 20, "d1"))


def test_a_confirmation_heard_to_its_end_is_heard_and_one_cut_before_it_is_not(monkeypatch):
    d = _draft(monkeypatch)
    _say(f"w_the text says w_hello. {CONFIRM}", 12, monkeypatch)         # cut after 12 characters
    assert d.heard is False
    _say(f"w_the text says w_hello. {CONFIRM}", None, monkeypatch)       # played to its end
    assert d.heard is True and routing._last["ours"].endswith(CONFIRM)


def test_his_sentence_reaches_the_owner_with_our_last_line_and_his_before(monkeypatch):
    from nucleo.send import draft, owner
    seen = {}
    monkeypatch.setattr(draft, "current", lambda: object())

    async def take(text, *, last_line="", before=None):
        seen.update(text=text, last_line=last_line, before=list(before or ()))
        return True, "w_sent"
    monkeypatch.setattr(owner, "take", take)
    monkeypatch.setitem(routing._last, "his", ["w_tell ana goodnight"])
    monkeypatch.setitem(routing._last, "ours", CONFIRM)
    assert asyncio.run(routing.HostRoute().take("acct", "w_yes")) == "w_sent"
    assert seen == {"text": "w_yes", "last_line": CONFIRM, "before": ["w_tell ana goodnight"]}

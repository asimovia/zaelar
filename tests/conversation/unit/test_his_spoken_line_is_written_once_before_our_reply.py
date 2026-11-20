"""His spoken line is written once, as the old turn wrote it, before our reply to it (node 13.112, V2-941).

  · every intervention the inbox ACCEPTS from his voice (closed, incomplete, a local phrase) writes the record's and the
    wall's row — `transcript` 🗣, role user, his words, the intervention as its trace — and the directed verdict that
    releases it on the wall, before any line of ours that answers it; two phrases are two rows, in order;
  · a discard (echo, a closed microphone, not addressed) and a typed line (its own door writes it) write no such row;
  · in a session of the manager the provider's final transcript writes nothing (the ear's row is the one), its interim
    caption still goes; with the switch off the provider's final is the row, as it always was;
  · the body's conversation is opened with this listener.

Disarms seen red: the accepted event without his words; the listener not wired; the provider's final not skipped.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from conversation.ports import Done
from conversation.testing.scripted_model import reply
from nucleo.conversation_host import wall_lines
from tests.conversation.unit.convkit import Harness


@pytest.fixture
def log(monkeypatch):
    from nucleo.conversation_host import turns
    from voice import observer
    turns._reset_for_tests()
    out = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None, piece=None:
                        out.append((kind, label, text, role, dict(extra or {}))))
    return out


def _wired(store, log):
    h = Harness(store)
    port = h.tel.emit
    h.tel.emit = lambda k, lab, p: (port(k, lab, p), wall_lines.listen(k, lab, p))
    say = h.mouth.say

    async def said(order):
        log.append(("say", "", order.text, "assistant", {}))
        await say(order)
    h.mouth.say = said
    h.model.default = lambda ids: [reply("w9"), Done()]
    return h


def _rows(log):
    return [(k, text if k != "ambient" else x.get("directed")) for k, _lab, text, role, x in log
            if (k == "transcript" and role == "user") or k in ("ambient", "say")]


def test_two_spoken_phrases_are_two_rows_in_order_before_our_reply(store, log):
    h = _wired(store, log)
    h.utter([(["w1", "w2"], 0)])
    h.utter([(["w3", "w4"], 0)], at=h.clock.mono + 50)
    h.settle(9000)
    rows = _rows(log)
    assert rows[:4] == [("transcript", "w1 w2"), ("ambient", True), ("transcript", "w3 w4"), ("ambient", True)], rows
    assert rows[4:] and all(r[0] == "say" for r in rows[4:]), "our reply comes after both of his lines"
    user = [x for k, _l, _t, role, x in log if k == "transcript" and role == "user"]
    assert all(x["trace"].startswith("T") for x in user) and len({x["trace"] for x in user}) == 2   # his turns (C16)


def test_a_discard_and_a_typed_line_write_no_spoken_row(store, log):
    h = _wired(store, log)
    h.conv.ear.guard = lambda endpoint, text: "echo"
    h.utter([(["w1", "w2"], 0)])
    h.settle(6000)
    h.typed("w5", h.clock.mono + 100)
    h.settle(6000)
    assert [r for r in _rows(log) if r[0] != "say"] == []


def test_a_local_phrase_is_his_line(store, log):
    from conversation.ear import signals as S
    h = _wired(store, log)
    h.hear(S.LocalPhrase("d1", "l1", "w1 w2", 10))
    h.settle(8000)
    assert _rows(log)[:2] == [("transcript", "w1 w2"), ("ambient", True)]


@pytest.mark.parametrize("on", [True, False])
def test_the_providers_final_is_the_row_only_on_the_old_path(monkeypatch, log, on):
    from nucleo.conversation_host import switch
    from voice import remote_session as rs
    monkeypatch.setitem(rs._M, "session", SimpleNamespace(_conversation_switch=switch.Decision(on, "voice")))
    rs.handle({"k": "transcript", "final": False, "text": "w1"})
    rs.handle({"k": "transcript", "final": True, "text": "w1 w2"})
    kinds = [(k, text) for k, _l, text, role, _x in log if role == "user"]
    assert kinds == ([("interim", "w1")] if on else [("interim", "w1"), ("transcript", "w1 w2")])


def test_the_bodys_conversation_is_opened_with_the_listener(monkeypatch):
    from nucleo.conversation_host import boot, entry, sessions
    monkeypatch.setattr(sessions, "get", lambda acct: None)
    monkeypatch.setattr(sessions, "open_", lambda acct, owner, make: make)
    monkeypatch.setattr(boot, "make", lambda listeners, said=None: listeners)
    assert wall_lines.listen in entry.runtime()

"""A turn of his is one unit for the Master and the viewer (node 13.116, V2-941, plan v3.2 C16).

  · every entry of his the inbox accepts, spoken or typed, opens ONE `trace` «turno» (root, initiator user, his words
    as its title); his row and ours carry that turn's id;
  · a request's close ends its turn (`flow end`, ok unless it failed or stalled);
  · two entries one run answered together are one turn: the later is folded into the first (`trace merge`), never
    ended twice; an entry attached to an open request is folded into that request's turn;
  · the body's conversation is opened with this listener.

Disarms seen red: no turn opened at acceptance; no end at the close; the second close of one run ended instead of
merged.
"""
from __future__ import annotations

import pytest

from conversation.ports import Done
from conversation.testing.scripted_model import reply
from nucleo.conversation_host import turns, wall_lines
from tests.conversation.unit.convkit import Harness


@pytest.fixture
def log(monkeypatch):
    from voice import observer
    turns._reset_for_tests()
    out = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None, piece=None:
                        out.append((kind, label, text, role, dict(extra or {}))))
    yield out
    turns._reset_for_tests()


def _wired(store):
    h = Harness(store)
    port = h.tel.emit
    h.tel.emit = lambda k, lab, p: (port(k, lab, p), turns.listen(k, lab, p), wall_lines.listen(k, lab, p))
    from nucleo.conversation_host.mouth import WallMouth
    mouth = WallMouth(h.clock, ack_later=h.conv.ack)
    mouth.ack = h.conv.ack
    h.mouth.say = mouth.say                       # our rows, as the host writes them
    h.model.default = lambda ids: [reply("w9"), Done()]
    return h


def _roots(log):
    return [(text, x["trace"], role) for k, lab, text, role, x in log if k == "trace" and x.get("root")]


def test_each_entry_is_a_turn_and_its_close_ends_it(store, log):
    h = _wired(store)
    h.utter([(["w1", "w2"], 0)])
    h.settle(9000)
    h.typed("w5 w6", h.clock.mono + 100)
    h.settle(9000)
    roots = _roots(log)
    assert [(t, r) for t, _tid, r in roots] == [("w1 w2", "user"), ("w5 w6", "user")]
    ends = [x for k, lab, _t, _r, x in log if k == "flow" and lab == "end"]
    assert len(ends) == 2 and all(e["ok"] and e["reason"] == "turn_complete" for e in ends)
    his = [x["trace"] for k, _l, _t, role, x in log if k == "transcript" and role == "user"]
    ours = [x["trace"] for k, _l, _t, role, x in log if k == "transcript" and role == "assistant"]
    assert his == [roots[0][1]] and ours[0] == roots[0][1] and ours[-1] == roots[1][1]


def test_two_entries_one_run_answered_are_one_turn(store, log):
    h = _wired(store)
    h.utter([(["w1", "w2"], 0)])
    h.utter([(["w3", "w4"], 0)], at=h.clock.mono + 50)
    h.settle(9000)
    roots = _roots(log)
    assert len(roots) == 2
    ends = [x for k, lab, _t, _r, x in log if k == "flow" and lab == "end"]
    merges = [x for k, lab, _t, _r, x in log if k == "trace" and lab == "merge"]
    assert len(ends) == 1 and [(m["merge_into"], m["trace"]) for m in merges] == [(roots[0][1], roots[1][1])]


def test_a_failed_close_ends_its_turn_not_ok(log):
    turns.listen("conv_inbox", "accepted", {"kind": "user.text", "text": "w1", "refs": {"iv": "iv_1", "env": "e_1"}})
    turns.listen("conv_close", "failed", {"refs": {"req": "r_iv_1"}})
    end = [x for k, lab, _t, _r, x in log if k == "flow" and lab == "end"]
    assert [(e["ok"], e["reason"]) for e in end] == [(False, "failed")]


def test_an_attached_entry_is_folded_into_its_requests_turn(log):
    for iv, env in (("iv_1", "e_1"), ("iv_2", "e_2")):
        turns.listen("conv_inbox", "accepted", {"kind": "user.utterance", "text": iv, "refs": {"iv": iv, "env": env}})
    turns.listen("conv_ledger", "attached", {"ref": "e_2", "refs": {"req": "r_iv_1"}})
    merges = [x for k, lab, _t, _r, x in log if k == "trace" and lab == "merge"]
    assert [(m["merge_into"], m["trace"]) for m in merges] == [(turns.known("iv_1"), turns.known("iv_2"))]


def test_the_bodys_conversation_is_opened_with_the_turns_listener(monkeypatch):
    from nucleo.conversation_host import boot, entry, sessions
    monkeypatch.setattr(sessions, "get", lambda acct: None)
    monkeypatch.setattr(sessions, "open_", lambda acct, owner, make: make)
    monkeypatch.setattr(boot, "make", lambda listeners, said=None: listeners)
    got = entry.runtime()
    assert turns.listen in got and got.index(turns.listen) < got.index(wall_lines.listen)

"""A turn of his is one unit for the Master and the viewer (node 13.116, V2-941, plan v3.2 C16).

  · every entry of his the inbox accepts, spoken or typed, opens ONE `trace` «turno» (root, initiator user, his words
    as its title); his row and ours carry that turn's id;
  · a request's close ends its turn (`flow end`, ok unless it failed: a failed run closes `recovered`);
  · two entries one run answered together are one turn: the later is folded into the first (`trace merge`), never
    ended twice; an entry attached to an open request is folded into that request's turn;
  · the body's conversation is opened with this listener.

Disarms seen red: no turn opened at acceptance; no end at the close; the second close of one run ended instead of
merged; `recovered` counted ok (a real failed run); the run's turn taken from its first close (closes out of order);
the failure line's prefix not read; a turn opened in this thread's own context.
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


def test_a_failed_run_ends_its_turn_not_ok(store, log):
    """The review's C16-1: a run that fails closes its requests `recovered` — through the real manager, never a
    hand-fed label — and its turn ends not ok."""
    from conversation.ports import Failed
    h = _wired(store)
    h.model.default = lambda ids: [Failed("timeout", "provider")]
    h.utter([(["w1", "w2"], 0)])
    h.settle(9000)
    ends = [x for k, lab, _t, _r, x in log if k == "flow" and lab == "end"]
    assert [(e["ok"], e["reason"]) for e in ends] == [(False, "recovered")]


def test_the_run_folds_its_turns_whatever_the_order_of_its_closes(log, monkeypatch):
    from voice import observer, trace
    ended_under = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None, piece=None: (
        log.append((kind, label, text, role, dict(extra or {}))),
        kind == "flow" and ended_under.append(trace.current())))
    for iv, env in (("iv_1", "e_1"), ("iv_2", "e_2")):
        turns.listen("conv_inbox", "accepted", {"kind": "user.utterance", "text": iv, "refs": {"iv": iv, "env": env}})
    turns.listen("conv_run", "started", {"batch_envs": ["e_2", "e_1"], "refs": {"run": "run_1"}})
    turns.listen("conv_close", "answered", {"refs": {"req": "r_iv_2", "run": "run_1"}})      # the newer first
    turns.listen("conv_close", "answered", {"refs": {"req": "r_iv_1", "run": "run_1"}})
    t1, t2 = turns.known("iv_1"), turns.known("iv_2")
    ends = [x for k, lab, _t, _r, x in log if k == "flow" and lab == "end"]
    merges = [(x["merge_into"], x["trace"]) for k, lab, _t, _r, x in log if k == "trace" and lab == "merge"]
    assert len(ends) == 1 and ended_under == [t1] and merges == [(t1, t2)]   # the oldest ends, the newer folds


def test_the_failure_line_carries_its_turn_and_a_turn_never_leaks_into_the_thread(log):
    from types import SimpleNamespace

    from nucleo.conversation_host.mouth import trace_of
    from voice import trace
    before = trace.current()
    tid = turns.corr("iv_7", "w1")
    assert trace.current() == before, "opening a turn leaves this thread's own trace as it was"
    assert trace_of(SimpleNamespace(request_id="conv:failed:r_iv_7")) == tid
    assert trace_of(SimpleNamespace(request_id="task:k1")) == "task:k1"            # a notice of no turn: its own

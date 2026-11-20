"""Half a thought whose rest never came is never left unheard (node 13.110, V2-941, v3.1 B10b — the tester's 69 real
replays: bursts with no answer went from 2 % to 36 %, 123 of them fragments cut mid-idea the manager rightly waited on).

When the model reads his batch as incomplete and says nothing (`no_reply`, `complete: false`) and no continuation
comes within its grace — a voice's, or `incomplete_grace_ms` for a typed fragment — the manager says the language's
«go on, I'm listening» (`listening`), once: never twice in a row (by where our last answer came from). His voice up
again waits for its silence. A `no_reply` the model did not read as incomplete (addressed to someone else, a comment)
stays silent. P3 checks it as a property over 2000 random conversations.
"""
from __future__ import annotations

from conversation.ports import Command, Done
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness


class _Words:
    def line(self, key, near=""):
        return {"listening": "w_listening", "mute_lines": "w_lost"}.get(key, "")


def _h(store, complete=False):
    h = Harness(store)
    h.conv.words = _Words()
    h.model.default = lambda ids: [Command("no_reply", {"reason": "w0", "complete": complete}), Done()]
    return h


def _commands(h):
    return [p.get("command") for k, lab, p in h.tel.events if k == "conv_run" and lab == "command"]


def test_his_voice_left_half_a_thought_and_nothing_followed(store):
    h = _h(store)
    h.utter([(["w1", "w2"], 0)])
    h.settle(h.conv.cfg.incomplete_grace_ms + 2000)
    assert [o.text for o in h.mouth.orders] == ["w_listening"] and "listening" in _commands(h)
    rows = [row for _k, row in h.store.view(h.conv.account).recent("says", 2)]
    assert [row.get("origin") for row in rows] == ["listening"]


def test_a_typed_fragment_waits_its_grace_then_is_heard(store):
    h = _h(store)
    h.typed("w1", 0)
    h.settle(h.conv.cfg.incomplete_grace_ms - 500)
    assert h.mouth.orders == []                                                # still waiting for its rest
    h.settle(1500)
    assert [o.text for o in h.mouth.orders] == ["w_listening"]


def test_the_rest_coming_within_its_grace_is_answered_whole(store):
    h = _h(store)
    h.typed("w1", 0)
    h.settle(1000)
    h.model.default = lambda ids: [reply("w9"), Done()]
    h.typed("w2", h.clock.mono)
    h.settle(h.conv.cfg.incomplete_grace_ms + 2000)
    assert [o.text for o in h.mouth.orders] == ["w9"]                          # never «I'm listening» before it


def test_never_twice_in_a_row(store):
    h = _h(store)
    h.typed("w1", 0)
    h.settle(h.conv.cfg.incomplete_grace_ms + 2000)
    h.typed("w2", h.clock.mono + 30_000)
    h.settle(h.conv.cfg.incomplete_grace_ms + 40_000)
    assert [o.text for o in h.mouth.orders] == ["w_listening"]                 # the second half-thought: silent


def test_a_no_reply_not_read_as_incomplete_stays_silent(store):
    h = _h(store, complete=True)
    h.utter([(["w1", "w2"], 0)])
    h.settle(h.conv.cfg.incomplete_grace_ms + 2000)
    assert h.mouth.orders == [] and [lab for lab, _ in h.closes()] == ["silent"]

"""What was never pronounced does not exist for the conversation (node 13.125, V2-941, the operator's rule of
2026-11-20: the wall, the history and the memory are a faithful transcript of what was SAID).

Our reply of twelve words is cut by his voice after five: the next run's input reads our line as those five words,
and the conversation's record — what memory ingests (`Record.pair`) — carries those five words, written when the line
ended, never the whole reply. A line whose sound is unknown is nothing in either. The whole reply stays only in
observability.

Disarms seen red: the record owed with the whole reply at say time; a line of unknown sound read whole by the model.
"""
from __future__ import annotations

from types import SimpleNamespace

from conversation.mouth import SayEnded, SayStarted
from conversation.ports import Done
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness

REPLY = "w1 w2 w3 w4 w5 w6 w7 w8 w9 w10 w11 w12"
HEARD = "w1 w2 w3 w4 w5"


def _cut_after_five(store, outcome="cut", heard=len(HEARD) + 1, source="agent_estimate"):
    h = Harness(store, grace=False)
    pairs: list[tuple[str, str]] = []
    h.conv.record = SimpleNamespace(pair=lambda acct, said, answered, ref: pairs.append((said, answered)))
    h.model.default = lambda ids: [reply(REPLY), Done()]
    ack, h.mouth.ack = h.mouth.ack, None                  # the voice acknowledges by hand: it is cut mid-line
    h.utter([(["q1", "q2"], 0)])
    h.settle(2000)
    order = h.mouth.orders[-1]
    ack(SayStarted(order.say_id, h.clock.mono))
    ack(SayEnded(order.say_id, outcome, heard, h.clock.mono, "d1", source))
    h.mouth.ack = ack
    h.model.default = lambda ids: [reply("w99"), Done()]
    h.utter([(["q3"], 0)])
    h.settle(2000)
    ours = [t.text for t in h.model.calls[-1].prompt.conversation if t.role == "agent"]
    return ours, pairs


def test_a_cut_reply_is_what_he_heard_in_the_next_input_and_in_the_record(store):
    ours, pairs = _cut_after_five(store)
    assert ours[0] == HEARD, ours
    assert pairs and pairs[0] == ("q1 q2", HEARD), pairs


def test_a_reply_of_unknown_sound_is_nothing_in_either(store):
    ours, pairs = _cut_after_five(store, outcome="unknown", heard=None, source="unknown")
    assert REPLY not in ours and not any(t.startswith("w1 w2") for t in ours), ours
    assert pairs and pairs[0] == ("q1 q2", ""), pairs

"""A line owed is said once, by one channel, and never lost (node 13.30).

What the engine owes the person — a worker's result, a contact's message, a reminder, the line that says a run failed —
is not an entry of the inbox: it lives in its own ledger (`ports.Owed`), already worded and already on the wall. The
manager asks for the next line held for the voice only when it is free and nobody is speaking, says it AS IT IS (no
model) and only by voice, and reports back: it sounded → spoken; it did not (no ack, a cut before any sound, no
device that can speak) → back to the ledger, which takes its other ways. A claim past its deadline goes back too.
"""
from __future__ import annotations

from conversation.ear import signals as S
from conversation.mouth import SayEnded
from tests.conversation.unit.convkit import Harness


def test_a_line_owed_is_said_as_it_is_by_voice_once_when_the_manager_is_free(store):
    h = Harness(store)
    h.owed.add("n1", "w5 w6")
    for _ in range(3):
        h.pump()
    assert [(o.text, tuple(sorted(o.channels)), o.notice_key) for o in h.mouth.orders] == [("w5 w6", ("voice",), "n1")]
    assert not h.model.calls and h.owed.rows["n1"]["state"] == "spoken"


def test_never_while_the_person_speaks_or_a_run_is_on(store):
    h = Harness(store)
    t = h.clock.mono + 10
    h.hear(S.VadEdge("d1", "rise", t))                       # he starts speaking
    h.owed.add("n1", "w5")
    h.pump()
    assert not h.mouth.orders
    h.hear(S.VadEdge("d1", "fall", t + 200), S.Tick(t + 3000))   # a cough: discarded, nobody speaks any more
    h.pump()
    assert [o.notice_key for o in h.mouth.orders] == ["n1"]


def test_a_line_that_never_sounded_goes_back_to_its_ledger_and_is_not_said_again(store):
    h = Harness(store)
    h.mouth.ack = None                                       # no ack comes back on its own
    h.owed.add("n1", "w5")
    h.pump()
    sid = h.mouth.orders[0].say_id
    h.conv.ack(SayEnded(sid, "unknown", None, h.clock.now_ms(), "d1"))
    for _ in range(3):
        h.pump()
    assert h.owed.rows["n1"]["state"] == "owed" and len(h.mouth.orders) == 1


def test_with_no_device_that_can_speak_the_line_goes_its_other_ways(store):
    h = Harness(store)
    h.conv.devices.clear()
    h.owed.add("n1", "w5")
    h.pump()
    assert not h.mouth.orders and h.owed.rows["n1"]["state"] == "owed"


def test_a_claim_past_its_deadline_goes_back(store):
    h = Harness(store)
    h.conv.devices.clear()
    h.owed.claim_ms = 1000
    h.owed.add("n1", "w5", now=0)
    h.owed.rows["n1"]["out"] = True                          # handed to a consumer that never answered
    assert h.owed.expire(999) == [] and h.owed.expire(1000) == ["n1"] and h.owed.rows["n1"]["state"] == "owed"

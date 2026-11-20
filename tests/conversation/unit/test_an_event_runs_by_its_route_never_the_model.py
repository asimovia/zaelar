"""An event of the world enters the manager and runs by its route, never by the model (node 13.137, E7d-1, R-2).

An EVENT envelope carries its source's authority, comes only from an `event:` producer, and opens a request of its
own. Free, it runs alone: the host's `Events` door carries out the route the router already decided, and the event is
accounted and its request closed exactly once — `answered` when the door did something, `silent` when nothing,
`failed` when the door failed, owing him no line. It never joins nor goes ahead of his words: with his entry queued,
his batch runs first, the event after it, in a batch of its own; with a voice of his open, it waits.
"""
from __future__ import annotations

from conversation import envelopes as E
from conversation.ear import signals as S
from conversation.ports import Done
from conversation.testing.scripted_model import reply
from conversation.types import Authority, EnvelopeKind
from tests.conversation.unit.convkit import ACCT, Harness


class _Events:
    def __init__(self, outcome="noticed"):
        self.outcome, self.seen = outcome, []

    async def run(self, account, env):
        self.seen.append((env.body.event_id, env.body.route))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _event(n: int, t: int, producer: str = "event:w_router") -> E.Envelope:
    return E.make(EnvelopeKind.EVENT, E.EventBody(f"ev{n}", "connector.msg", "w_source", "w_text", {}, {"as": "w_route"}),
                  producer=producer, producer_id=f"x{n}", account=ACCT, onset_ms=t, sealed_ms=t)


def _with(store, events):
    h = Harness(store, grace=False)
    h.conv.events = events
    h.model.default = lambda ids: [reply("w9"), Done()]
    return h


def test_an_event_runs_its_route_by_the_hosts_door_and_never_the_model(store):
    events = _Events("noticed")
    h = _with(store, events)
    h.at(100)
    h.conv.give(_event(1, 100))
    h.settle(2000)
    assert events.seen == [("ev1", {"as": "w_route"})] and not h.model.calls and not h.mouth.orders
    assert [(lab, p["refs"]["req"]) for lab, p in h.closes()] == [("answered", h.closes()[0][1]["refs"]["req"])]
    assert h.closes()[0][1]["refs"]["req"].startswith("ev_")
    assert _event(1, 0).authority is Authority.SOURCE


def test_a_door_with_nothing_to_do_closes_silent_and_one_that_fails_owes_him_nothing(store):
    h = _with(store, _Events("nothing"))
    h.at(100)
    h.conv.give(_event(1, 100))
    h.settle(2000)
    assert [lab for lab, _p in h.closes()] == ["silent"]
    h2 = _with(store, _Events(OSError("w_down")))
    h2.at(100)
    h2.conv.give(_event(2, 100))
    h2.settle(2000)
    assert [lab for lab, _p in h2.closes()] == ["failed"] and not h2.owed.rows


def test_his_words_go_first_and_an_event_never_joins_his_batch(store):
    events = _Events("noticed")
    h = _with(store, events)
    h.at(100)
    h.conv.give(_event(1, 100))
    h.typed("w1", 100)
    h.settle(3000)
    runs = [p for k, lab, p in h.tel.events if k == "conv_run" and lab == "started"]
    assert len(h.model.calls) == 1 and events.seen == [("ev1", {"as": "w_route"})]
    assert [p.get("origin") for p in runs] == [None, "connector.msg"]       # his batch first, the event on its own


def test_an_event_waits_while_his_voice_is_open(store):
    events = _Events("noticed")
    h = _with(store, events)
    h.at(100)
    h.hear(S.VadEdge("d1", "rise", 100))
    h.conv.give(_event(1, 150))
    h.pump()
    assert events.seen == []


def test_a_producer_that_is_not_an_event_source_is_refused(store):
    events = _Events("noticed")
    h = _with(store, events)
    h.conv.give(_event(1, 100, producer="chat:w_x"))
    h.settle(1000)
    assert events.seen == [] and not h.closes()

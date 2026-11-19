"""I1/I3: a seal and a substitution exclude each other; no action rests on an unsealed intervention (node 13.5).

The intervention is the unit. A closed one is sealed by its first effect or publication, and then nothing changes it:
what the person says next is another intervention. While the run has neither published nor acted, a continuation
that closes SUBSTITUTES the run — its batch goes back and the next run carries both, so the first is sealed only with
its continuation; once sealed, a continuation never enters that run, it follows up. An incomplete or discarded
intervention never seals; how the ear ended one is noted once, and a re-delivered note changes nothing.
"""
from __future__ import annotations

from conversation import envelopes as E
from conversation.gateway import seal as S
from conversation.gateway.outbox import Claimed, Refused
from conversation.ports import Done, ToolCall
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import ACCT, Harness
from tests.conversation.unit.gatekit import Kit

ADD = ToolCall("c", "agenda_add", {"what": "w0001"})


def _phase(store, iv):
    return store.snapshot(ACCT).get(S.T, iv)["phase"]


def test_a_sealed_intervention_stays_sealed_and_an_unended_one_never_seals(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    a = k.utterance("iv1")
    with store.tx(k.lease) as tx:
        assert S.seal(tx, "iv1", 10) and S.seal(tx, "iv1", 12)              # sealing again: still sealed
        S.finish(tx, "iv1", 13)                                            # its request ended: still sealed
        assert not S.seal(tx, "iv9", 14)                                   # never closed: never sealed
        S.note(tx, "iv2", "incomplete", 15)
        S.note(tx, "iv3", "discarded", 15)
        assert not S.seal(tx, "iv2", 16) and not S.seal(tx, "iv3", 16)
    assert (_phase(store, "iv1"), _phase(store, "iv2"), _phase(store, "iv3")) == ("sealed", "incomplete",
                                                                                    "discarded")
    assert isinstance(k.gw.request(k.ctx(a), ADD), Claimed)


def test_an_action_never_rests_on_an_incomplete_intervention(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    env = k.utterance("iv1", closed=False)
    with store.tx(k.lease) as tx:
        S.note(tx, "iv1", "incomplete", 5)
    assert k.gw.request(k.ctx(env), ADD) == Refused("unsealed") and not k.items("effect")


def test_how_it_ended_is_noted_once_and_nothing_moves_a_seal(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    with store.tx(k.lease) as tx:
        assert S.note(tx, "iv0", "closed", 1)
        assert not S.note(tx, "iv0", "discarded", 2)                       # a later note changes nothing
        assert S.seal(tx, "iv0", 3)
        assert not S.note(tx, "iv0", "closed", 4)
    assert _phase(store, "iv0") == "sealed"


def test_a_continuation_before_publication_substitutes_the_run_and_both_seal_together(store):
    h = Harness(store)

    def goes_on():
        if len(h.model.calls) > 1:
            return
        t = h.clock.mono + 50
        h.utter([(["w3", "w4"], 0)])                                       # closes while the first run thinks

    h.model.script["iv_000001"] = [[goes_on, reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    last = h.model.calls[-1].prompt.input
    assert "«w1 w2»" in last and "«w3 w4»" in last                         # one prompt, both entries
    assert len(h.mouth.orders) == 1
    assert {"conv_run/superseded", "conv_run/held"} & set(h.tel.labels())   # the first run gave its batch back
    sealed = [p["refs"]["iv"] for k, lab, p in h.tel.events if k == "conv_effect" and lab == "sealed"]
    assert sorted(sealed) == sorted(["iv_000001", next(iv for iv in sealed if iv != "iv_000001")])
    assert [lab for lab, _ in h.closes()] == ["answered", "answered"]


def test_after_the_seal_a_continuation_never_enters_the_sealed_run(store):
    h = Harness(store)
    h.model.default = lambda ids: [reply("ok " + "+".join(ids)), Done()]
    h.utter([(["w1", "w2"], 0)])
    assert _phase(store, "iv_000001") == "sealed"
    h.utter([(["w3"], 0)])
    second = h.model.calls[-1].prompt.input
    assert "«w3»" in second and "«w1 w2»" not in second.split("INPUT")[-1]
    assert _phase(store, "iv_000001") == "sealed" and len(h.model.calls) == 2


def test_a_redelivered_entry_through_the_manager_is_a_duplicate_and_writes_nothing(store):
    h = Harness(store)
    h.live = False
    h.utter([(["w1", "w2"], 0)])
    first = [r for _k, r in store.snapshot(ACCT).scan("inbox") if r["kind"] == "user.utterance"][0]
    h.conv.give(E.from_json({**first["env"], "id": ""}))                   # the adapter retries
    assert _phase(store, "iv_000001") == "closed"
    assert "conv_inbox/duplicate" in h.tel.labels()

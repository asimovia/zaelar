"""I1/I3: a seal and a reopen exclude each other; no action effect rests on an unsealed revision (node 13.5).

A closed revision can be sealed (its first effect) or reopened (the person went on) — never both. After the seal there is no
reopen (the ear amends instead); an incomplete revision is never sealed. Proved on both stores and, on sqlite, with
TWO REAL WRITERS racing on one file: for every intervention exactly one of the two wins, and every effect row of the
gateway rests on a revision that is sealed.
"""
from __future__ import annotations

import threading

from conversation.gateway.outbox import Claimed, Refused
from conversation.gateway import seal as S
from conversation.ports import ToolCall
from conversation.store import SqliteStore
from tests.conversation.unit.gatekit import ACCT, Kit

ADD = ToolCall("c", "agenda_add", {"what": "w0001"})


def _phase(store, iv):
    return store.snapshot(ACCT).get(S.T, iv)["phase"]


def test_a_sealed_revision_does_not_reopen_and_a_reopened_one_does_not_seal(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    a, b = k.utterance("iv1"), k.utterance("iv2")
    with store.tx(k.lease) as tx:
        assert S.seal(tx, "iv1", 1, 10) and not S.reopen(tx, "iv1", 1, 11)
        assert S.reopen(tx, "iv2", 1, 10) and not S.seal(tx, "iv2", 1, 11)
        assert S.seal(tx, "iv1", 1, 12)                                   # sealing again is a no-op, still sealed
    assert (_phase(store, "iv1"), _phase(store, "iv2")) == ("1:sealed", "2:open")
    assert isinstance(k.gw.request(k.ctx(b), ADD), Refused)                 # rests on revision 1, now reopened
    assert not k.items("effect")
    assert isinstance(k.gw.request(k.ctx(a), ADD), Claimed)


def test_an_incomplete_revision_is_never_sealed(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    env = k.utterance("iv1", closed=False)
    with store.tx(k.lease) as tx:
        S.note(tx, "iv1", 1, "incomplete", 5)
        assert not S.seal(tx, "iv1", 1, 6)
    assert k.gw.request(k.ctx(env), ADD) == Refused("unsealed") and not k.items("effect")


def test_two_real_writers_race_a_seal_against_a_reopen_and_exactly_one_wins(tmp_path, clock, telemetry):
    path = tmp_path / "c.db"
    first = SqliteStore(path)
    k = Kit(first, clock, telemetry)
    second = SqliteStore(path)                                             # another connection, same lease
    ivs = [f"iv{i}" for i in range(40)]
    for iv in ivs:
        k.utterance(iv)
    results: dict[str, list] = {iv: [] for iv in ivs}

    def sealer():
        for iv in ivs:
            with first.tx(k.lease) as tx:
                if S.seal(tx, iv, 1, 1):
                    results[iv].append("seal")

    def reopener():
        for iv in ivs:
            with second.tx(k.lease) as tx:
                if S.reopen(tx, iv, 1, 1):
                    results[iv].append("reopen")

    threads = [threading.Thread(target=sealer), threading.Thread(target=reopener)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert all(len(r) == 1 for r in results.values()), {iv: r for iv, r in results.items() if len(r) != 1}
    for iv, (won,) in results.items():
        assert _phase(first, iv) == ("1:sealed" if won == "seal" else "2:open")
    first.close()
    second.close()


def test_the_gateway_racing_a_reopen_never_leaves_an_effect_on_an_unsealed_revision(tmp_path, clock, telemetry):
    path = tmp_path / "c.db"
    first = SqliteStore(path)
    k = Kit(first, clock, telemetry)
    second = SqliteStore(path)
    envs = [k.utterance(f"iv{i}") for i in range(30)]

    def claimer():
        for env in envs:
            k.gw.request(k.ctx(env, run=f"r-{env.body.intervention_id}"),
                         ToolCall("c", "agenda_add", {"what": env.body.intervention_id}))

    def reopener():
        for env in envs:
            with second.tx(k.lease) as tx:
                S.reopen(tx, env.body.intervention_id, 1, 1)

    threads = [threading.Thread(target=claimer), threading.Thread(target=reopener)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    for row in k.items("effect"):
        for iv, rev in row["data"]["ivs"]:
            assert _phase(first, iv) == f"{rev}:sealed", (iv, _phase(first, iv))
    first.close()
    second.close()


def test_b5_note_only_moves_forward_and_a_redelivered_older_revision_cannot_make_a_reopen_sealable(store, clock,
                                                                                                  telemetry):
    """Revision 1 closed, the voice went on (2:open); an adapter re-delivers revision 1. The phase stays 2:open and
    revision 1 cannot be sealed: an action cannot rest on what the person is still extending (audit B5)."""
    k = Kit(store, clock, telemetry)
    with store.tx(k.lease) as tx:
        S.note(tx, "iv1", 1, "closed", 1)
        assert S.reopen(tx, "iv1", 1, 2)
        assert not S.note(tx, "iv1", 1, "closed", 3)                     # older: ignored
        assert not S.seal(tx, "iv1", 1, 4)
        S.note(tx, "iv0", 1, "closed", 5)
        assert S.seal(tx, "iv0", 1, 5)
        assert not S.note(tx, "iv0", 1, "closed", 6)                     # nothing moves off a seal
    assert _phase(store, "iv1") == "2:open"


def test_b5_a_redelivered_revision_through_the_manager_is_a_duplicate_and_writes_nothing(store):
    from conversation import envelopes as E
    from conversation.ear import signals as Sg
    from tests.conversation.unit.convkit import Harness
    h = Harness(store)
    h.live = False
    h.utter([(["w1", "w2"], 0)])
    first = [r for _k, r in store.snapshot("acct-test").scan("inbox") if r["kind"] == "user.utterance"][0]
    t = h.clock.mono + 100
    h.hear(Sg.WordSpan("d1", 50, 1, False, h.words(["w3"], t), (t, t + 180)))          # reopened: 2:open
    assert store.snapshot("acct-test").get(S.T, "iv_000001")["phase"] == "2:open"
    h.conv.give(E.from_json({**first["env"], "id": ""}))                              # the adapter retries rev 1
    assert store.snapshot("acct-test").get(S.T, "iv_000001")["phase"] == "2:open"
    assert "conv_inbox/duplicate" in h.tel.labels()

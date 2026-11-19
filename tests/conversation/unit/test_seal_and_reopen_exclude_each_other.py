"""I1/I3: a seal and a reopen exclude each other; no action effect rests on an unsealed revision (node 13.5).

A closed revision can be sealed (its first effect) or reopened (he went on) — never both. After the seal there is no
reopen (the ear amends instead); an incomplete revision is never sealed. Proved on both stores and, on sqlite, with
TWO REAL WRITERS racing on one file: for every intervention exactly one of the two wins, and every effect row of the
gateway rests on a revision that is sealed.
"""
from __future__ import annotations

import threading

from conversation.gateway import Claimed, Refused
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

"""One writer per account, fenced by an epoch; the Store contract both stores keep (node 13.19, I5).

The battery runs over BOTH stores (in memory and sqlite): acquiring bumps the epoch, a transaction under a lease that
was taken writes nothing (not even half), a failed transaction leaves nothing behind, `cas` and `insert_unique` are
the atomic primitives the invariants rest on, a snapshot is a detached coherent copy. On sqlite, two REAL writers on
one file: the moment the second acquires, the first one's writes stop landing; and everything survives a reopen.
"""
from __future__ import annotations

import threading
import time

import pytest

from conversation.ports import Conflict, StaleEpoch
from conversation.store import SqliteStore


def test_acquire_bumps_the_epoch_and_names_the_owner(store):
    a = store.acquire("acct", "proc-a")
    b = store.acquire("acct", "proc-b")
    assert (a.epoch, b.epoch) == (1, 2) and store.current("acct") == b
    assert store.acquire("other", "proc-a").epoch == 1


def test_a_stale_lease_writes_nothing_and_says_so(store):
    a = store.acquire("acct", "proc-a")
    with store.tx(a) as tx:
        tx.put("items", "r1", {"state": "open"})
    b = store.acquire("acct", "proc-b")
    with pytest.raises(StaleEpoch):
        with store.tx(a) as tx:
            tx.put("items", "r1", {"state": "answered"})
            tx.put("items", "r2", {"state": "open"})
    with pytest.raises(StaleEpoch):
        store.check(a)
    snap = store.snapshot("acct")
    assert snap.get("items", "r1") == {"state": "open"} and snap.get("items", "r2") is None
    store.check(b)
    with store.tx(b) as tx:
        tx.put("items", "r1", {"state": "answered"})
    assert store.snapshot("acct").get("items", "r1") == {"state": "answered"}


def test_a_failed_transaction_leaves_nothing(store):
    lease = store.acquire("acct", "p")
    with pytest.raises(RuntimeError):
        with store.tx(lease) as tx:
            tx.put("items", "x", {"v": 1})
            tx.next_seq("turns")
            raise RuntimeError("boom")
    assert store.snapshot("acct").get("items", "x") is None
    with store.tx(lease) as tx:
        assert tx.next_seq("turns") == 1


def test_cas_moves_a_row_only_from_the_expected_value(store):
    lease = store.acquire("acct", "p")
    with store.tx(lease) as tx:
        assert tx.cas("iv", "i1", "state", None, {"state": "closed", "rev": 1})       # absent → created
        assert not tx.cas("iv", "i1", "state", None, {"state": "open"})
        assert tx.cas("iv", "i1", "state", "closed", {"state": "sealed"})
        assert not tx.cas("iv", "i1", "state", "closed", {"state": "open", "rev": 2})  # the seal won
        assert tx.get("iv", "i1") == {"state": "sealed", "rev": 1}
        assert tx.cas("flags", "f", "on", None, {"on": True}) and tx.cas("flags", "f", "on", True, {"on": False})


def test_insert_unique_returns_the_same_row_on_a_repeat(store):
    lease = store.acquire("acct", "p")
    with store.tx(lease) as tx:
        row, new = tx.insert_unique("effects", "x1", {"state": "claimed"}, "g1|e1|send")
        again, new2 = tx.insert_unique("effects", "x2", {"state": "claimed"}, "g1|e1|send")
        assert new and not new2 and again == row and tx.get("effects", "x2") is None
        with pytest.raises(Conflict):
            tx.insert_unique("effects", "x1", {"state": "claimed"}, "g2|e1|send")


def test_scan_is_ordered_and_a_snapshot_is_detached(store):
    lease = store.acquire("acct", "p")
    with store.tx(lease) as tx:
        for k in ("b", "a", "c"):
            tx.put("t", k, {"k": k})
    snap = store.snapshot("acct")
    assert [k for k, _ in snap.scan("t")] == ["a", "b", "c"]
    snap.get("t", "a")["k"] = "mutated"
    with store.tx(lease) as tx:
        tx.put("t", "d", {"k": "d"})
    assert snap.get("t", "a") == {"k": "a"} and snap.get("t", "d") is None
    assert store.snapshot("other").scan("t") == []


def test_sqlite_survives_a_reopen(tmp_path):
    path = tmp_path / "c.db"
    s = SqliteStore(path)
    lease = s.acquire("acct", "p")
    with s.tx(lease) as tx:
        tx.put("inbox", "e1", {"state": "queued"})
        tx.next_seq("inbox")
    s.close()
    s2 = SqliteStore(path)
    assert s2.current("acct") == lease
    assert s2.snapshot("acct").get("inbox", "e1") == {"state": "queued"}
    with s2.tx(lease) as tx:
        assert tx.next_seq("inbox") == 2
    s2.close()


def test_two_real_writers_on_one_file_the_old_one_stops_at_the_takeover(tmp_path):
    path = tmp_path / "c.db"
    first, second = SqliteStore(path), SqliteStore(path)
    lease_a = first.acquire("acct", "proc-a")
    stop = threading.Event()

    def writer_a():
        while not stop.is_set():
            try:
                with first.tx(lease_a) as tx:
                    n = tx.next_seq("log")
                    tx.put("log", f"{n:06d}", {"who": "a"})
            except StaleEpoch:
                return
            time.sleep(0.001)          # a writer between two transactions, not a spin on the lock

    t = threading.Thread(target=writer_a, daemon=True)
    t.start()
    try:
        deadline = time.monotonic() + 10
        while first.snapshot("acct").get("log", "000020") is None and time.monotonic() < deadline:
            time.sleep(0.001)
        lease_b = second.acquire("acct", "proc-b")
        with second.tx(lease_b) as tx:
            n_b = tx.next_seq("log")
            tx.put("log", f"{n_b:06d}", {"who": "b"})
        t.join(timeout=10)
        assert not t.is_alive(), "the old writer kept writing after the takeover"
    finally:
        stop.set()
    rows = second.snapshot("acct").scan("log")
    landed_after = [k for k, r in rows if r["who"] == "a" and int(k) > n_b]
    assert not landed_after and n_b > 20
    first.close()
    second.close()

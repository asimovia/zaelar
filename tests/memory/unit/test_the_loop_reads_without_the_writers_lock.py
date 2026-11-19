"""The event loop's reads never wait for another thread's database lock, and a wait names its holder (INI-042 #34).

`zaelar.db` was one connection behind one lock: a thread that held it for seconds (a write waiting on SQLite's own
writer, a checkpoint on a slow disk) stopped the loop at its next `SELECT` — «held 7.1 s at `state.read`», with the
loop waiting, not computing. A thread that runs an event loop now reads through its own read-only WAL connection, and
the lock keeps who holds it: whoever still waits ≥ `SLOW_S` is told the holder's thread and stack.
"""
import asyncio
import threading
import time

import pytest

from memory import db as memdb
from memory import lock_watch
from memory import state as memstate


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    d = memdb.get_db()
    d.execute("CREATE TABLE IF NOT EXISTS probe (id INTEGER PRIMARY KEY, v TEXT)")
    d.execute("INSERT INTO probe (v) VALUES ('committed')")
    yield d
    memdb.reset_db()


def _hold(db, seconds: float, started: threading.Event):
    """A writer thread that keeps the lock, mid-transaction, for `seconds`."""
    def writer_that_waits():
        with db.cursor() as cur:
            cur.execute("INSERT INTO probe (v) VALUES ('not yet')")
            started.set()
            time.sleep(seconds)
    t = threading.Thread(target=writer_that_waits, name="slow-writer", daemon=True)
    t.start()
    return t


def test_a_read_on_the_loop_does_not_wait_for_a_writer_in_another_thread(db):
    started = threading.Event()
    holder = _hold(db, 1.0, started)

    async def read():
        started.wait(2)
        t0 = time.monotonic()
        rows = db.query("SELECT v FROM probe ORDER BY id")
        one = db.query_one("SELECT COUNT(*) c FROM probe")
        st = memstate.read()                                   # the read the prompt makes on every turn
        return time.monotonic() - t0, [r["v"] for r in rows], one["c"], st

    took, rows, count, st = asyncio.run(read())
    holder.join()
    assert took < 0.3, f"the loop waited {took:.2f} s for another thread's write"
    assert rows == ["committed"] and count == 1                # what is committed, never the half-written row
    assert "language" in st
    assert [r["v"] for r in db.query("SELECT v FROM probe ORDER BY id")] == ["committed", "not yet"]


def test_the_loop_sees_a_write_as_soon_as_it_is_committed_and_its_own_before(db):
    async def main():
        db.execute("INSERT INTO probe (v) VALUES ('by the loop')")
        after_commit = [r["v"] for r in db.query("SELECT v FROM probe ORDER BY id")]
        with db.cursor() as cur:                               # its own open transaction: it reads what it wrote
            cur.execute("INSERT INTO probe (v) VALUES ('mine, open')")
            inside = db.query_one("SELECT COUNT(*) c FROM probe")["c"]
        t = threading.Thread(target=lambda: db.execute("INSERT INTO probe (v) VALUES ('by a thread')"))
        t.start()
        t.join()
        return after_commit, inside, db.query_one("SELECT COUNT(*) c FROM probe")["c"]

    after_commit, inside, final = asyncio.run(main())
    assert after_commit == ["committed", "by the loop"] and inside == 3 and final == 4


def test_only_a_select_on_a_loop_thread_takes_the_read_only_connection(db):
    assert db._reader("SELECT 1") is None                      # no event loop in this thread: the shared connection

    async def main():
        reader = db._reader("  select v FROM probe")
        assert reader is not None and reader is db._reader("SELECT 1")          # one per loop thread, reused
        assert db._reader("PRAGMA user_version") is None and db._reader("INSERT INTO probe (v) VALUES ('x')") is None
        with pytest.raises(Exception):
            reader.execute("INSERT INTO probe (v) VALUES ('never')")            # it cannot write
        assert db.query_one("SELECT pylower('ÁRBOL') AS s")["s"] == "árbol"      # the shared connection's functions
        assert db.query_one("PRAGMA user_version")[0] == db.schema_version()
        return reader

    reader = asyncio.run(main())
    memdb.reset_db()
    with pytest.raises(Exception):
        reader.execute("SELECT 1")                             # closed with the database


def test_a_read_the_read_only_connection_refuses_is_answered_by_the_shared_one(db, monkeypatch):
    class Refuses:
        def execute(self, *a):
            raise memdb.sqlite3.OperationalError("no such module: vec0")

    monkeypatch.setattr(db, "_reader", lambda sql: Refuses())
    assert db.query_one("SELECT COUNT(*) c FROM probe")["c"] == 1


def test_a_thread_that_waits_for_the_lock_is_told_who_held_it(db, monkeypatch):
    monkeypatch.setattr(lock_watch, "SLOW_S", 0.1)
    told = []
    monkeypatch.setattr(lock_watch, "_tell", lambda what, s, holder, stack, waiter="": told.append(
        (what, s, holder, stack, waiter)))
    started = threading.Event()
    holder = _hold(db, 0.5, started)
    started.wait(2)
    t0 = time.monotonic()
    assert db.query_one("SELECT COUNT(*) c FROM probe")["c"] == 2     # no loop here: it waits, as every thread did
    waited = time.monotonic() - t0
    holder.join()
    wait = next(t for t in told if t[0] == "wait")
    assert waited >= 0.3 and wait[1] >= 0.3 and wait[2] == "slow-writer"
    assert any("writer_that_waits" in frame for frame in wait[3])     # the holder's stack, read while it held
    hold = next(t for t in told if t[0] == "hold")
    assert hold[2] == "slow-writer" and hold[1] >= 0.4


def test_a_lock_nobody_waits_for_says_nothing_and_stays_reentrant(db, monkeypatch):
    told = []
    monkeypatch.setattr(lock_watch, "_tell", lambda *a, **k: told.append(a))
    with db._lock:
        with db.cursor() as cur:
            cur.execute("INSERT INTO probe (v) VALUES ('nested')")
        assert db._lock.held_by_me()
    assert not db._lock.held_by_me() and told == []


def test_a_stall_names_the_threads_that_were_running_while_the_loop_was_held(monkeypatch):
    """The other half of «waiting, not computing»: the stall's event carries who ELSE ran (a lock's holder, a thread
    the interpreter was busy in), never a thread parked in a wait."""
    from collections import Counter

    from nucleo.pulse import loop_lag

    monkeypatch.setitem(loop_lag._state, "others", Counter())
    release, busy_in = threading.Event(), threading.Event()

    def crunching():                       # runs engine-side code (this file is under the engine root)
        busy_in.set()
        while not release.is_set():
            sum(range(200))

    def waiting():                         # engine-side code too, but parked in a wait: it held nothing
        release.wait()

    parked = threading.Thread(target=waiting, name="parked", daemon=True)
    runner = threading.Thread(target=crunching, name="cruncher", daemon=True)
    parked.start()
    runner.start()
    busy_in.wait(2)
    try:
        for _ in range(3):
            loop_lag._sample_others(loop_tid=None)
    finally:
        release.set()
        runner.join()
    said = loop_lag._busy()
    assert any(line.startswith("cruncher ×3") and "crunching" in line for line in said), said
    assert not any(line.startswith("parked") for line in said)
    assert loop_lag._busy() == []          # consumed: the next stall starts clean

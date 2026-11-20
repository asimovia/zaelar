"""The reference `Store` on sqlite3, in a file of its OWN (PA-2): the ledger, the durable inbox and the lease.

One writer per account is enforced by the lease row: `acquire` bumps the epoch in its own transaction, and every
`tx(lease)` runs `BEGIN IMMEDIATE` (the database write lock) and compares the epoch INSIDE that transaction before
the first write and again just before COMMIT — so a holder whose lease was taken writes nothing, not even half.
Two processes (or two `SqliteStore` objects) on one file are two real writers; the lock serialises them.

`cas` is a conditional UPDATE on the JSON field (`json_extract`), and `insert_unique` relies on a UNIQUE index: the
two atomic primitives the invariants rest on (a seal and a reopen exclude each other; one effect per (grant, trigger,
operation)). Rows are JSON text. Each transaction is local and short; the manager times it like any port call.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from conversation.ports import Conflict, Lease, StaleEpoch

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leases (account TEXT PRIMARY KEY, owner TEXT NOT NULL, epoch INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rows (account TEXT NOT NULL, tbl TEXT NOT NULL, key TEXT NOT NULL, row TEXT NOT NULL,
                                 uniq TEXT, PRIMARY KEY (account, tbl, key));
CREATE UNIQUE INDEX IF NOT EXISTS rows_uniq ON rows (account, tbl, uniq) WHERE uniq IS NOT NULL;
CREATE INDEX IF NOT EXISTS rows_state ON rows (account, tbl, json_extract(row, '$.state'));
CREATE TABLE IF NOT EXISTS seqs (account TEXT NOT NULL, name TEXT NOT NULL, n INTEGER NOT NULL,
                                 PRIMARY KEY (account, name));
"""


class _Read:
    def __init__(self, conn: sqlite3.Connection, account: str) -> None:
        self._c, self._a = conn, account

    def get(self, table: str, key: str) -> dict | None:
        r = self._c.execute("SELECT row FROM rows WHERE account=? AND tbl=? AND key=?",
                            (self._a, table, key)).fetchone()
        return json.loads(r[0]) if r else None

    def scan(self, table: str, states: tuple[str, ...] | None = None) -> list[tuple[str, dict]]:
        if states is None:
            return [(k, json.loads(v)) for k, v in self._c.execute(
                "SELECT key, row FROM rows WHERE account=? AND tbl=? ORDER BY key", (self._a, table))]
        marks = ",".join("?" * len(states))
        return [(k, json.loads(v)) for k, v in self._c.execute(        # by the state index: what is in course only
            f"SELECT key, row FROM rows WHERE account=? AND tbl=? AND json_extract(row, '$.state') IN ({marks}) "
            "ORDER BY key", (self._a, table, *states))]


class _Tx(_Read):
    def put(self, table: str, key: str, row: dict) -> None:
        self._c.execute("INSERT INTO rows (account, tbl, key, row) VALUES (?,?,?,?) "
                        "ON CONFLICT (account, tbl, key) DO UPDATE SET row=excluded.row",
                        (self._a, table, key, json.dumps(row)))

    def cas(self, table: str, key: str, field_name: str, expect: Any, new: dict) -> bool:
        row = self.get(table, key)
        if (None if row is None else row.get(field_name)) != expect:
            return False
        merged = json.dumps({**(row or {}), **new})
        if row is None:
            cur = self._c.execute("INSERT OR IGNORE INTO rows (account, tbl, key, row) VALUES (?,?,?,?)",
                                  (self._a, table, key, merged))
        else:   # the compare and the write are one statement: no reader in between can see a half
            cur = self._c.execute(
                "UPDATE rows SET row=? WHERE account=? AND tbl=? AND key=? "
                "AND json_extract(row, ?) IS json_extract(?, '$.v')",
                (merged, self._a, table, key, f'$."{field_name}"', json.dumps({"v": expect})))
        return cur.rowcount == 1

    def insert_unique(self, table: str, key: str, row: dict, unique: str) -> tuple[dict, bool]:
        r = self._c.execute("SELECT tbl, key FROM rows WHERE account=? AND tbl=? AND uniq=?",
                            (self._a, table, unique)).fetchone()
        if r:
            return self.get(r[0], r[1]), False
        try:
            self._c.execute("INSERT INTO rows (account, tbl, key, row, uniq) VALUES (?,?,?,?,?)",
                            (self._a, table, key, json.dumps(row), unique))
        except sqlite3.IntegrityError as e:
            raise Conflict(f"{table}/{key} exists under another unique value") from e
        return row, True

    def next_seq(self, name: str) -> int:
        self._c.execute("INSERT INTO seqs (account, name, n) VALUES (?,?,1) "
                        "ON CONFLICT (account, name) DO UPDATE SET n=n+1", (self._a, name))
        return self._c.execute("SELECT n FROM seqs WHERE account=? AND name=?", (self._a, name)).fetchone()[0]


class _Snapshot:
    def __init__(self, tables: dict) -> None:
        self._t = tables

    def get(self, table: str, key: str) -> dict | None:
        row = self._t.get(table, {}).get(key)
        return json.loads(json.dumps(row)) if row is not None else None

    def scan(self, table: str, states: tuple[str, ...] | None = None) -> list[tuple[str, dict]]:
        return [(k, json.loads(json.dumps(v))) for k, v in sorted(self._t.get(table, {}).items())
                if states is None or v.get("state") in states]


class SqliteStore:
    def __init__(self, path: str | Path, *, busy_timeout_ms: int = 5000) -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._depth = threading.local()
        self._c = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False,
                                  timeout=busy_timeout_ms / 1000)
        self._c.execute("PRAGMA journal_mode=WAL")
        self._c.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        self._c.executescript(_SCHEMA)

    def _epoch(self, account: str) -> tuple[str, int] | None:
        r = self._c.execute("SELECT owner, epoch FROM leases WHERE account=?", (account,)).fetchone()
        return (r[0], r[1]) if r else None

    def acquire(self, account: str, owner: str) -> Lease:
        with self._lock:
            self._c.execute("BEGIN IMMEDIATE")
            try:
                prev = self._epoch(account)
                epoch = (prev[1] if prev else 0) + 1
                self._c.execute("INSERT INTO leases (account, owner, epoch) VALUES (?,?,?) ON CONFLICT (account) "
                                "DO UPDATE SET owner=excluded.owner, epoch=excluded.epoch", (account, owner, epoch))
                self._c.execute("COMMIT")
            except BaseException:
                self._c.execute("ROLLBACK")
                raise
            return Lease(account, owner, epoch)

    def current(self, account: str) -> Lease | None:
        with self._lock:
            cur = self._epoch(account)
            return Lease(account, cur[0], cur[1]) if cur else None

    def _require(self, lease: Lease) -> None:
        if self._epoch(lease.account) != (lease.owner, lease.epoch):
            raise StaleEpoch(f"{lease.account}: epoch {lease.epoch} is not current")

    def check(self, lease: Lease) -> None:
        with self._lock:
            self._require(lease)

    @contextmanager
    def tx(self, lease: Lease) -> Iterator[_Tx]:
        with self._lock:
            if getattr(self._depth, "n", 0):    # refused BEFORE touching the outer one: it stays whole
                raise RuntimeError("a transaction inside a transaction: the inner one would be lost at commit")
            self._c.execute("BEGIN IMMEDIATE")
            self._depth.n = 1
            try:
                self._require(lease)
                yield _Tx(self._c, lease.account)
                self._require(lease)
                self._c.execute("COMMIT")
            except BaseException:
                self._c.execute("ROLLBACK")
                raise
            finally:
                self._depth.n = 0

    def snapshot(self, account: str) -> _Snapshot:
        with self._lock:
            self._c.execute("BEGIN")
            try:
                tables: dict = {}
                for tbl, key, row in self._c.execute("SELECT tbl, key, row FROM rows WHERE account=?", (account,)):
                    tables.setdefault(tbl, {})[key] = json.loads(row)
            finally:
                self._c.execute("COMMIT")
            return _Snapshot(tables)

    def close(self) -> None:
        with self._lock:
            self._c.close()

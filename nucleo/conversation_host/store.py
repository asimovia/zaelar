"""The `Store` port of the `conversation` package over `zaelar.db` (V2-941).

The package's contract, kept by its in-memory double too (node 13.19): a lease per account fenced by an epoch, one
transaction at a time per thread (a nested one is refused, and so is reaching another store from inside one),
`scan(table, states)` reading only what is in course, detached reads outside a transaction. The rows live in the
`conv_*` tables (`memory.api.conv`); the errors are translated into the port's own.
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Iterator

from conversation.ports import Conflict, Lease, StaleEpoch
from memory.api import conv as cs


class _Tx:
    def __init__(self, tx: cs.Tx) -> None:
        self._tx = tx

    def get(self, table, key):
        return self._tx.get(table, key)

    def put(self, table, key, row):
        self._tx.put(table, key, row)

    def cas(self, table, key, field_name, expect, new):
        return self._tx.cas(table, key, field_name, expect, new)

    def insert_unique(self, table, key, row, unique):
        try:
            return self._tx.insert_unique(table, key, row, unique)
        except cs.Conflict as e:
            raise Conflict(str(e)) from e

    def scan(self, table, states=None):
        return self._tx.scan(table, states)

    def next_seq(self, name):
        return self._tx.next_seq(name)


class _Snapshot:
    """A detached, coherent copy of the account's rows, read once outside a transaction (committed rows; on a thread
    with an event loop, by its read-only connection, which never waits for a writer)."""

    def __init__(self, rows: dict[str, dict[str, dict]]) -> None:
        self._t = rows

    def get(self, table, key):
        row = self._t.get(table, {}).get(key)
        return json.loads(json.dumps(row)) if row is not None else None

    def scan(self, table, states=None):
        return [(k, json.loads(json.dumps(v))) for k, v in sorted(self._t.get(table, {}).items())
                if states is None or v.get("state") in states]

    def recent(self, table, n):
        rows = list(self._t.get(table, {}).items())[-int(n):] if n > 0 else []      # read in the order written
        return [(k, json.loads(json.dumps(v))) for k, v in reversed(rows)]


class ZaelarStore:
    """`db`: a `memory.db.Database` (tests pass their own); None is the engine's shared one."""

    def __init__(self, db=None, clock_ms=None) -> None:
        self._db = db
        self._now = clock_ms or (lambda: int(time.time() * 1000))

    def acquire(self, account: str, owner: str) -> Lease:
        return Lease(account, owner, cs.acquire(account, owner, db=self._db))

    def current(self, account: str) -> Lease | None:
        cur = cs.current(account, db=self._db)
        return Lease(account, cur[0], cur[1]) if cur else None

    def check(self, lease: Lease) -> None:
        if cs.current(lease.account, db=self._db) != (lease.owner, lease.epoch):
            raise StaleEpoch(f"{lease.account}: epoch {lease.epoch} is not current")

    @contextmanager
    def tx(self, lease: Lease) -> Iterator[_Tx]:
        try:
            with cs.tx(lease.account, lease.owner, lease.epoch, self._now(), db=self._db) as tx:
                yield _Tx(tx)
        except cs.StaleEpoch as e:
            raise StaleEpoch(str(e)) from e

    def snapshot(self, account: str) -> _Snapshot:
        return _Snapshot(cs.read_all(account, db=self._db))

    def view(self, account: str) -> cs.Reader:
        """What a run reads: each read one indexed query — the rows in course by state, the window by time."""
        return cs.Reader(account, db=self._db)

    def close(self) -> None:
        if self._db is not None:
            self._db.close()

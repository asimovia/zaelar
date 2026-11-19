"""The `Store` in memory: the fast double for unit tests, with the SAME contract as the sqlite one (node 13.19).

A transaction holds the store's lock from start to commit, writes into a copy-on-write staging and applies it only
on a clean exit; the epoch is compared at the start and again at commit. Rows go through JSON on the way in and out, so
a row that would not survive the sqlite store does not survive this one either.
"""
from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from conversation.ports import Conflict, Lease, StaleEpoch


def _freeze(row: Any) -> str:
    return json.dumps(row)


def _thaw(text: str) -> Any:
    return json.loads(text)


class _Tables:
    """Rows are stored as JSON text (like the sqlite store), so a table can be shared between the store, a
    transaction's staging and a snapshot: nothing a reader holds can change what is stored."""

    def __init__(self, data: dict) -> None:
        self.data = data   # {table: {key: row}, "__unique__": {table: {value: key}}, "__seq__": {name: n}}

    def _table(self, table: str) -> dict:
        return self.data.get(table, {})

    def get(self, table: str, key: str) -> dict | None:
        row = self._table(table).get(key)
        return _thaw(row) if row is not None else None

    def scan(self, table: str) -> list[tuple[str, dict]]:
        return [(k, _thaw(v)) for k, v in sorted(self._table(table).items())]


class _Tx(_Tables):
    """Copy-on-write staging: a table is copied (shallowly) the first time this transaction writes it."""

    def __init__(self, base: dict) -> None:
        super().__init__(base)
        self.staged: dict[str, dict] = {}

    def _table(self, table: str) -> dict:
        return self.staged[table] if table in self.staged else self.data.get(table, {})

    def _write(self, table: str) -> dict:
        if table not in self.staged:
            self.staged[table] = dict(self.data.get(table, {}))
        return self.staged[table]

    def put(self, table: str, key: str, row: dict) -> None:
        self._write(table)[key] = _freeze(row)

    def cas(self, table: str, key: str, field_name: str, expect: Any, new: dict) -> bool:
        row = self.get(table, key)
        current = None if row is None else row.get(field_name)
        if current != expect:
            return False
        self.put(table, key, {**(row or {}), **new})
        return True

    def insert_unique(self, table: str, key: str, row: dict, unique: str) -> tuple[dict, bool]:
        idx = self._write("__unique__")
        tidx = dict(idx.get(table, {}))
        if unique in tidx:
            return self.get(table, tidx[unique]), False
        if key in self._table(table):
            raise Conflict(f"{table}/{key} exists under another unique value")
        tidx[unique] = key
        idx[table] = tidx
        self._write(table)[key] = _freeze(row)
        return self.get(table, key), True

    def next_seq(self, name: str) -> int:
        seqs = self._write("__seq__")
        seqs[name] = seqs.get(name, 0) + 1
        return seqs[name]


class MemoryStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._depth = threading.local()
        self._accounts: dict[str, dict] = {}
        self._leases: dict[str, Lease] = {}

    def acquire(self, account: str, owner: str) -> Lease:
        with self._lock:
            prev = self._leases.get(account)
            lease = Lease(account, owner, (prev.epoch if prev else 0) + 1)
            self._leases[account] = lease
            return lease

    def current(self, account: str) -> Lease | None:
        with self._lock:
            return self._leases.get(account)

    def check(self, lease: Lease) -> None:
        with self._lock:
            if self._leases.get(lease.account) != lease:
                raise StaleEpoch(f"{lease.account}: epoch {lease.epoch} is not current")

    @contextmanager
    def tx(self, lease: Lease) -> Iterator[_Tx]:
        with self._lock:
            if getattr(self._depth, "n", 0):
                raise RuntimeError("a transaction inside a transaction: the inner one would be lost at commit")
            self.check(lease)
            base = self._accounts.setdefault(lease.account, {})
            tx = _Tx(base)
            self._depth.n = 1
            try:
                yield tx
            finally:
                self._depth.n = 0
            self.check(lease)
            base.update(tx.staged)

    def snapshot(self, account: str) -> _Tables:
        with self._lock:
            return _Tables({t: dict(rows) for t, rows in self._accounts.get(account, {}).items()})

    def close(self) -> None:
        pass

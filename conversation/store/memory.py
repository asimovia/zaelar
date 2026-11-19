"""The `Store` in memory: the fast double for unit tests, with the SAME contract as the sqlite one (node 13.19).

A transaction holds the store's lock from start to commit, writes into a staging copy and applies it only on a
clean exit; the epoch is compared at the start and again at commit. Rows go through JSON on the way in and out, so
a row that would not survive the sqlite store does not survive this one either.
"""
from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from conversation.ports import Conflict, Lease, StaleEpoch


def _copy(row: Any) -> Any:
    return json.loads(json.dumps(row))


class _Tables:
    def __init__(self, data: dict) -> None:
        self.data = data   # {table: {key: row}, "__unique__": {table: {value: key}}, "__seq__": {name: n}}

    def get(self, table: str, key: str) -> dict | None:
        row = self.data.get(table, {}).get(key)
        return _copy(row) if row is not None else None

    def scan(self, table: str) -> list[tuple[str, dict]]:
        return [(k, _copy(v)) for k, v in sorted(self.data.get(table, {}).items())]


class _Tx(_Tables):
    def put(self, table: str, key: str, row: dict) -> None:
        self.data.setdefault(table, {})[key] = _copy(row)

    def cas(self, table: str, key: str, field_name: str, expect: Any, new: dict) -> bool:
        row = self.data.get(table, {}).get(key)
        current = None if row is None else row.get(field_name)
        if current != expect:
            return False
        self.put(table, key, {**(row or {}), **new})
        return True

    def insert_unique(self, table: str, key: str, row: dict, unique: str) -> tuple[dict, bool]:
        idx = self.data.setdefault("__unique__", {}).setdefault(table, {})
        if unique in idx:
            return self.get(table, idx[unique]), False
        if key in self.data.get(table, {}):
            raise Conflict(f"{table}/{key} exists under another unique value")
        idx[unique] = key
        self.data.setdefault(table, {})[key] = _copy(row)
        return self.get(table, key), True

    def next_seq(self, name: str) -> int:
        seqs = self.data.setdefault("__seq__", {})
        seqs[name] = seqs.get(name, 0) + 1
        return seqs[name]


class MemoryStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
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
            self.check(lease)
            staged = _copy(self._accounts.get(lease.account, {}))
            yield _Tx(staged)
            self.check(lease)
            self._accounts[lease.account] = staged

    def snapshot(self, account: str) -> _Tables:
        with self._lock:
            return _Tables(_copy(self._accounts.get(account, {})))

    def close(self) -> None:
        pass

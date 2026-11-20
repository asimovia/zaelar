"""memory/conversation_store.py — the conversation manager's storage: `conv_rows` and `conv_meta`, nothing else (V2-941).

Reached through the facade (`memory.api.conv`), never imported directly, and written by ONE thread: the
conversation's own (`nucleo/conversation_host/runtime.py`). The rules live in the `conversation` package; this module
only reads and writes rows, keyed by (account, the package's logical table, key), the row as JSON with its `state`
lifted out so a sweep reads what is in course and never the history.

A transaction is `memory.db.exclusive`: `BEGIN IMMEDIATE` on the shared connection and the lease's epoch compared at
its start — a process whose lease was taken writes nothing. Once it holds the write lock nobody can take the lease
until it commits, so the start is the only place to look. Inside it this thread
can neither open another one nor reach another store (`Database.cursor()` refuses), and it reads through the same
connection, so it sees what it wrote. Outside a transaction it reads through `query` (on a thread with an event loop:
its own read-only connection, which never waits for a writer).

Retention: `prune` deletes, in one bounded statement per table, rows in a FINAL state older than the horizon; a row
that is not final (a request still open, a reservation `claimed` or `submission_unknown`) stays until it ends.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

from . import db as _db

#: per logical table, the states that end a row — what the prune may drop once old
FINAL = {"inbox": ("accounted",), "voice_open": ("done",), "says": ("ended",),
         "items": ("answered", "handed_off", "silent", "recovered", "failed", "withdrawn", "provider_accepted",
                   "rejected"),
         "interventions": None, "evidence": None, "flags": (), "effect_ops": ()}
LEASE = "lease"


class StaleEpoch(Exception):
    """The lease was taken by another owner: this one writes nothing."""


class Conflict(Exception):
    """A key already used under another unique value."""


def _lease(conn, account: str) -> tuple[str, int] | None:
    r = conn.execute("SELECT value FROM conv_meta WHERE account=? AND key=?", (account, LEASE)).fetchone()
    if r is None:
        return None
    d = json.loads(r[0])
    return d["owner"], d["epoch"]


class Tx:
    """One transaction's view: get, put, compare-and-set, insert-unique, scan (by state), counters."""

    def __init__(self, conn, account: str, now_ms: int) -> None:
        self._c, self._a, self._now = conn, account, now_ms

    def get(self, table: str, key: str) -> dict | None:
        r = self._c.execute("SELECT row FROM conv_rows WHERE account=? AND tbl=? AND key=?",
                            (self._a, table, key)).fetchone()
        return json.loads(r[0]) if r else None

    def put(self, table: str, key: str, row: dict) -> None:
        self._c.execute("INSERT INTO conv_rows (account, tbl, key, state, updated_ms, row) VALUES (?,?,?,?,?,?) "
                        "ON CONFLICT (account, tbl, key) DO UPDATE SET state=excluded.state, "
                        "updated_ms=excluded.updated_ms, row=excluded.row",
                        (self._a, table, key, row.get("state"), self._now, json.dumps(row)))

    def cas(self, table: str, key: str, field_name: str, expect: Any, new: dict) -> bool:
        row = self.get(table, key)
        if (None if row is None else row.get(field_name)) != expect:
            return False
        self.put(table, key, {**(row or {}), **new})        # one transaction, one writer: the read is the compare
        return True

    def insert_unique(self, table: str, key: str, row: dict, unique: str) -> tuple[dict, bool]:
        r = self._c.execute("SELECT row FROM conv_rows WHERE account=? AND tbl=? AND uniq=?",
                            (self._a, table, unique)).fetchone()
        if r:
            return json.loads(r[0]), False
        if self.get(table, key) is not None:
            raise Conflict(f"{table}/{key} exists under another unique value")
        self._c.execute("INSERT INTO conv_rows (account, tbl, key, state, uniq, updated_ms, row) VALUES (?,?,?,?,?,?,?)",
                        (self._a, table, key, row.get("state"), unique, self._now, json.dumps(row)))
        return row, True

    def scan(self, table: str, states: tuple[str, ...] | None = None) -> list[tuple[str, dict]]:
        return scan(self._c.execute, self._a, table, states)

    def next_seq(self, name: str) -> int:
        key = f"seq:{name}"
        r = self._c.execute("SELECT value FROM conv_meta WHERE account=? AND key=?", (self._a, key)).fetchone()
        n = (int(r[0]) if r else 0) + 1
        self._c.execute("INSERT INTO conv_meta (account, key, value) VALUES (?,?,?) ON CONFLICT (account, key) "
                        "DO UPDATE SET value=excluded.value", (self._a, key, str(n)))
        return n


def scan(execute, account: str, table: str, states: tuple[str, ...] | None) -> list[tuple[str, dict]]:
    if states is None:
        rows = execute("SELECT key, row FROM conv_rows WHERE account=? AND tbl=? ORDER BY key", (account, table))
    else:
        marks = ",".join("?" * len(states))
        rows = execute(f"SELECT key, row FROM conv_rows WHERE account=? AND tbl=? AND state IN ({marks}) ORDER BY key",
                       (account, table, *states))
    return [(k, json.loads(v)) for k, v in rows]


def acquire(account: str, owner: str, db=None) -> int:
    """A new epoch for this owner: whoever held the account is fenced from now on."""
    with _db.exclusive(db or _db.get_db()) as conn:
        prev = _lease(conn, account)
        epoch = (prev[1] if prev else 0) + 1
        conn.execute("INSERT INTO conv_meta (account, key, value) VALUES (?,?,?) ON CONFLICT (account, key) DO UPDATE "
                     "SET value=excluded.value", (account, LEASE, json.dumps({"owner": owner, "epoch": epoch})))
    return epoch


def current(account: str, db=None) -> tuple[str, int] | None:
    r = (db or _db.get_db()).query_one("SELECT value FROM conv_meta WHERE account=? AND key=?", (account, LEASE))
    if r is None:
        return None
    d = json.loads(r[0])
    return d["owner"], d["epoch"]


@contextmanager
def tx(account: str, owner: str, epoch: int, now_ms: int, db=None) -> Iterator[Tx]:
    """One transaction under a lease: refused (StaleEpoch) when the lease is not current. It is checked under the
    write lock, which holds until the commit: no other writer can take the lease in between."""
    with _db.exclusive(db or _db.get_db()) as conn:
        if _lease(conn, account) != (owner, epoch):
            raise StaleEpoch(f"{account}: epoch {epoch} is not current")
        yield Tx(conn, account, now_ms)


def read_all(account: str, db=None) -> dict[str, dict[str, dict]]:
    """Every row of the account, by table — one coherent read for a snapshot (the prune bounds it)."""
    out: dict[str, dict[str, dict]] = {}
    for r in (db or _db.get_db()).query("SELECT tbl, key, row FROM conv_rows WHERE account=?", (account,)):
        out.setdefault(r[0], {})[r[1]] = json.loads(r[2])
    return out


def prune(max_age_days: int, now_ms: int, db=None) -> int:
    """Drop what is final and older than the horizon — one bounded statement per table; never a row in course.
    `interventions` and `evidence` end by age alone (their rows carry no state to wait for)."""
    cut, gone = now_ms - max_age_days * 86_400_000, 0
    d = db or _db.get_db()
    with d.cursor() as cur:
        for table, final in FINAL.items():
            if final is None:
                cur.execute("DELETE FROM conv_rows WHERE tbl=? AND updated_ms < ?", (table, cut))
            elif final:
                marks = ",".join("?" * len(final))
                cur.execute(f"DELETE FROM conv_rows WHERE tbl=? AND updated_ms < ? AND state IN ({marks})",
                            (table, cut, *final))
            else:
                continue
            gone += cur.rowcount
    return gone

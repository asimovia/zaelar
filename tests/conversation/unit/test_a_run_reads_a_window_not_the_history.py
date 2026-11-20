"""A run reads a window, never the account's history (node 13.45, v3.1 B4c — the review's TE-1).

What a run reads — the open items by state, the newest entries, lines and interventions, the newest evidence — is
bounded: the same rows with 300 exchanges of history as with 3000. On `zaelar.db` each read is one query through its
index: the scan by state through `idx_conv_rows_state` (no ORDER BY that made the planner walk the table by its key),
the window through `idx_conv_rows_recent`, the hourly prune through an index that starts by the table.
"""
from __future__ import annotations

import json

import pytest

from conversation.composer.compose import view_from
from conversation.manager import claims as CL
from memory.api import conv as cs
from memory.db import Database
from nucleo.conversation_host.store import ZaelarStore


def _history(db: Database, exchanges: int) -> None:
    rows = []
    for i in range(exchanges):
        env = {"channel": "text", "kind": "user.text",
               "body": {"text": f"w{i}", "intervention_id": f"iv{i}"}, "refs": {"intervention_id": f"iv{i}"}}
        rows.append(("a", "inbox", f"e{i:06d}", "accounted", i * 10,
                     json.dumps({"id": f"e{i:06d}", "kind": "user.text", "state": "accounted", "accepted": i * 10,
                                 "env": env})))
        rows.append(("a", "says", f"s{i:06d}", "ended", i * 10 + 5,
                     json.dumps({"say_id": f"s{i:06d}", "state": "ended", "t_ms": i * 10 + 5, "text": f"w{i}",
                                 "channels": ["text"], "heard_chars": 2})))
        rows.append(("a", "evidence", f"ev{i:06d}", None, i * 10,
                     json.dumps({"id": f"ev{i:06d}", "source": "search", "numbers": [i], "expires_ms": 0})))
        rows.append(("a", "items", f"r_iv{i}", "answered", i * 10,
                     json.dumps({"id": f"r_iv{i}", "kind": "request", "state": "answered", "data": {}})))
    with db.cursor() as cur:
        cur.executemany("INSERT INTO conv_rows (account, tbl, key, state, updated_ms, row) VALUES (?,?,?,?,?,?)", rows)


class _Counting:
    def __init__(self, view):
        self._v, self.rows = view, 0

    def scan(self, table, states=None):
        got = self._v.scan(table, states)
        self.rows += len(got)
        return got

    def recent(self, table, n):
        got = self._v.recent(table, n)
        self.rows += len(got)
        return got

    def get(self, table, key):
        return self._v.get(table, key)


def _rows_a_run_reads(tmp_path, exchanges: int) -> int:
    db = Database(tmp_path / f"z{exchanges}.db")
    try:
        _history(db, exchanges)
        v = _Counting(ZaelarStore(db).view("a"))
        view_from(v, prefix="", now_ms=10 ** 9, window=12)
        CL.valid(v, 0)
        return v.rows
    finally:
        db.close()


def test_a_run_reads_the_same_rows_whatever_the_history(tmp_path):
    small, large = _rows_a_run_reads(tmp_path, 300), _rows_a_run_reads(tmp_path, 3000)
    assert small == large and small <= 4 * 12 + 2 * 12 + 4 * 12 + CL.KEEP     # the window, not the history


def _plan(db: Database, sql: str, args: tuple) -> str:
    return " | ".join(str(r[-1]) for r in db.query("EXPLAIN QUERY PLAN " + sql, args))


@pytest.mark.parametrize("what,sql,args,index", [
    ("scan by state", "SELECT key, row FROM conv_rows WHERE account=? AND tbl=? AND state IN (?)",
     ("a", "items", "open"), "idx_conv_rows_state"),
    ("the window", "SELECT key, row FROM conv_rows WHERE account=? AND tbl=? ORDER BY updated_ms DESC, key DESC LIMIT ?",
     ("a", "inbox", 48), "idx_conv_rows_recent"),
    ("prune what is final", "DELETE FROM conv_rows WHERE tbl=? AND updated_ms < ? AND state IN (?)",
     ("items", 0, "answered"), "idx_conv_rows_prune"),
    ("prune by age", "DELETE FROM conv_rows WHERE tbl=? AND updated_ms < ?", ("evidence", 0), "USING INDEX"),
])
def test_each_read_goes_through_its_index(tmp_path, what, sql, args, index):
    db = Database(tmp_path / "z.db")
    try:
        _history(db, 200)
        with db.cursor() as cur:
            cur.execute("ANALYZE")
        plan = _plan(db, sql, args)
        assert index in plan and "SCAN conv_rows" not in plan, (what, plan)
    finally:
        db.close()


def test_the_queries_a_run_sends_go_through_their_indexes(tmp_path):
    """The SQL the store itself sends for a run, explained: the scan by state on its index, the window on its own."""
    db = Database(tmp_path / "z.db")
    try:
        _history(db, 200)
        with db.cursor() as cur:
            cur.execute("ANALYZE")
        sent, real = [], db.query
        db.query = lambda sql, args=(): sent.append((sql, tuple(args))) or real(sql, args)
        r = ZaelarStore(db).view("a")
        r.scan("items", ("open",))
        view_from(r, prefix="", now_ms=10 ** 9, window=12)
        db.query = real
        for sql, args in sent:
            plan = _plan(db, sql, args)
            want = "idx_conv_rows_state" if "state IN" in sql else "idx_conv_rows_recent"
            assert want in plan and "SCAN conv_rows" not in plan, (sql, plan)
    finally:
        db.close()


def test_the_store_reads_by_state_and_window_with_those_queries(tmp_path):
    db = Database(tmp_path / "z.db")
    try:
        _history(db, 50)
        r = ZaelarStore(db).view("a")
        assert [k for k, _r in r.recent("inbox", 3)] == ["e000049", "e000048", "e000047"]
        assert r.scan("items", ("open",)) == [] and len(r.scan("items", ("answered",))) == 50
        assert cs.prune(30, 10 ** 13, db=db) > 0
    finally:
        db.close()

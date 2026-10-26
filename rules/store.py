"""rules/store.py — the `rules` table: one row per standing rule or preference (V2-806).

It lives in the same SQLite file as memory (`ZAELAR_DB`, else `<workspace>/memory/_data/zaelar.db` — the path
`bus/log.py` and `memory/db.py` resolve the same way), but this module owns it: memory neither reads nor writes
it. The path is resolved PER CALL, so a test that points `ZAELAR_DB` somewhere else is honoured at once.

The table is small (tens of rows), so a read loads every row and the cascade filters in Python. A read is cached
until this process writes or SQLite's `data_version` says another connection did.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rules (
    id            TEXT PRIMARY KEY,
    scope         TEXT NOT NULL,
    kind          TEXT NOT NULL,
    key           TEXT NOT NULL,
    value         TEXT NOT NULL,
    except_scopes TEXT NOT NULL DEFAULT '[]',
    source        TEXT NOT NULL DEFAULT 'user',
    text          TEXT NOT NULL DEFAULT '',
    created_at    REAL NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1,
    until         REAL,
    origin        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS rules_scope ON rules(scope);
CREATE TABLE IF NOT EXISTS rules_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

_lock = threading.RLock()
_conns: dict[str, sqlite3.Connection] = {}
_cache: dict = {"path": None, "version": None, "rows": None}


def db_path() -> Path:
    env = os.getenv("ZAELAR_DB")
    if env:
        return Path(env)
    from nucleo import workspace as _ws
    return _ws.root() / "memory" / "_data" / "zaelar.db"


def _conn() -> sqlite3.Connection:
    p = str(db_path())
    c = _conns.get(p)
    if c is None:
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(p, check_same_thread=False, timeout=5.0, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(_SCHEMA)
        _conns[p] = c
    return c


def _to_row(r: sqlite3.Row) -> dict:
    return {"id": r["id"], "scope": r["scope"], "kind": r["kind"], "key": r["key"],
            "value": json.loads(r["value"]), "except": json.loads(r["except_scopes"] or "[]"),
            "source": r["source"], "text": r["text"], "created_at": r["created_at"], "active": bool(r["active"]),
            "until": r["until"], "origin": r["origin"]}


def rows() -> list[dict]:
    """Every stored row (active or not), oldest first. Cached until a write or another connection's write."""
    with _lock:
        c = _conn()
        ver = (str(db_path()), c.execute("PRAGMA data_version").fetchone()[0])
        if _cache["rows"] is not None and _cache["version"] == ver:
            return [dict(r) for r in _cache["rows"]]
        out = [_to_row(r) for r in c.execute("SELECT * FROM rules ORDER BY created_at, id")]
        _cache.update(version=ver, rows=out)
        return [dict(r) for r in out]


def get(rule_id: str) -> dict | None:
    return next((r for r in rows() if r["id"] == rule_id), None)


def _invalidate() -> None:
    _cache.update(version=None, rows=None)


_COLS = "id, scope, kind, key, value, except_scopes, source, text, created_at, active, until, origin"


def _values(row: dict) -> tuple:
    return (row["id"], row["scope"], row["kind"], row["key"], json.dumps(row["value"], ensure_ascii=False),
            json.dumps(list(row.get("except") or []), ensure_ascii=False), row.get("source") or "user",
            row.get("text") or "", float(row.get("created_at") or time.time()), 1 if row.get("active", True) else 0,
            row.get("until"), row.get("origin") or "")


def put(row: dict) -> dict:
    """Insert or replace one row (the caller built a complete row)."""
    with _lock:
        _conn().execute(f"INSERT OR REPLACE INTO rules ({_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", _values(row))
        _invalidate()
    return row


def insert_new(row: dict) -> bool:
    """Insert only if the id is not there yet — the one-time migrations' door. True = it was inserted."""
    with _lock:
        cur = _conn().execute(f"INSERT OR IGNORE INTO rules ({_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                              _values(row))
        _invalidate()
        return cur.rowcount > 0


def delete(rule_id: str) -> bool:
    with _lock:
        cur = _conn().execute("DELETE FROM rules WHERE id=?", (rule_id,))
        _invalidate()
        return cur.rowcount > 0


def meta_get(key: str) -> str | None:
    with _lock:
        r = _conn().execute("SELECT value FROM rules_meta WHERE key=?", (key,)).fetchone()
        return r["value"] if r else None


def meta_set(key: str, value: str) -> None:
    with _lock:
        _conn().execute("INSERT OR REPLACE INTO rules_meta (key, value) VALUES (?, ?)", (key, value))


def _reset_for_tests() -> None:
    """Empty the table of the CURRENT database (the suite's temp file) — never called by the product."""
    with _lock:
        c = _conn()
        c.execute("DELETE FROM rules")
        c.execute("DELETE FROM rules_meta")
        _invalidate()

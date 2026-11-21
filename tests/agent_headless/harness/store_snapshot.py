"""One comparable picture of everything a turn could have written: `take()` before, `take()` after, and `==`.

«Nothing was written» is only worth asserting when the picture covers every place a write could land:
  · the engine's database, as a LOGICAL dump — every table's rows, sorted. Never the file's bytes: SQLite rewrites
    pages and its write-ahead log without any row changing. The derived tables of the search indexes (`fts_*_*`,
    `vec_*_*`) and SQLite's own are left out, each by name below: they follow the tables they index;
  · every widget's store on disk (the messaging queues among them), file by file;
  · the state a send keeps in MEMORY, which no database shows: the open draft and the ones queued behind it, and the
    confirmations waiting for his yes.

It is bytes, so two pictures compare exactly; `diff()` names what changed when they do not.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3

#: Tables that are not a source of truth: the search indexes' shadow tables and SQLite's own sequence counter.
DERIVED = re.compile(r"^(fts_\w+_(config|data|docsize|idx|content)|vec_\w+_(chunks|info|rowids|vector_chunks\d+)"
                     r"|sqlite_\w+)$")


def _database() -> dict:
    from memory import db
    path = str(db.db_path())
    if not os.path.isfile(path):
        return {}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        names = sorted(r[0] for r in con.execute("select name from sqlite_master where type='table'"))
        out = {}
        for name in names:
            if DERIVED.match(name):
                continue
            try:
                out[name] = sorted(repr(tuple(row)) for row in con.execute(f'select * from "{name}"'))
            except sqlite3.Error as e:          # a virtual table whose module is not loaded here: named, not hidden
                out[name] = [f"<unread: {type(e).__name__}>"]
        return out
    finally:
        con.close()


def _widgets() -> dict:
    from widgets import store
    root = str(store.DATA_DIR)
    out = {}
    for d, _dirs, files in os.walk(root):
        for f in sorted(files):
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def _memory() -> dict:
    from nucleo.send import draft
    from widgets import confirm
    d = draft._open["draft"]
    return {"draft": None if d is None else {**d.snapshot(), "confirm_line": d.confirm_line, "heard": d.heard,
                                             "extra": d.extra},
            # the messages queued behind it are pending rows of the send lane: the database part holds them
            "confirmations": {k: {x: v[x] for x in sorted(v) if x != "ts"} for k, v in sorted(confirm._PENDING.items())}}


def parts() -> dict:
    return {"database": _database(), "widgets": _widgets(), "memory": _memory()}


def take() -> bytes:
    return json.dumps(parts(), sort_keys=True, default=repr, ensure_ascii=False).encode("utf-8")


def diff(before: bytes, after: bytes) -> list[str]:
    """What changed between two pictures, as `part/key` names; [] when they are the same bytes."""
    if before == after:
        return []
    a, b = json.loads(before), json.loads(after)
    return sorted(f"{part}/{k}" for part in a for k in set(a[part]) | set(b.get(part, {}))
                  if a[part].get(k) != b.get(part, {}).get(k))

"""Shared fixtures for the genome tests (V2-859): a private memory file and workspace per test."""
from __future__ import annotations

import pytest

from memory import db as memdb


@pytest.fixture
def mem(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path / "ws"))
    memdb.reset_db()
    db = memdb.get_db()
    yield db
    memdb.reset_db()


def learned_alias(db, lang, phrase, action_json, *, status="active", hits=5, agree=4, disagree=0, source="learned"):
    db.execute("INSERT INTO action_map (lang, phrase, action, source, status, hits, agree, disagree, created_at) "
               "VALUES (?,?,?,?,?,?,?,?,1)", (lang, phrase, action_json, source, status, hits, agree, disagree))
    return db.query_one("SELECT id FROM action_map WHERE lang=? AND phrase=?", (lang, phrase))["id"]


@pytest.fixture
def alias_row(mem):
    """`alias_row(lang, phrase, action_json, **kw)` writes one action-map row into this test's memory."""
    return lambda *a, **kw: learned_alias(mem, *a, **kw)

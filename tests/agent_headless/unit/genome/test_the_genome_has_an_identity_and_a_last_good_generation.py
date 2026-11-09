"""V2-859 T563 · the genome has a name, a generation, and a last good generation to fall back to.

`genome.identity()` names the genome on disk (`nucleo/genesis.json` + `i18n/genesis/<lang>/`) by a hash of its
canonical content — documentation keys stripped, so a comment edit is the same genome and a value edit is not. A
genesis that fails the schema check is refused LOUD and every reader gets the last generation that passed, never a
half-read file. `version` became `generation`. And the V2-594 «workflow table» is the playbook's ROUTE: an install
that still has the old table keeps its rows under the new name.
"""
from __future__ import annotations

import json

import genome

GOOD = {"generation": 3, "style": {"max_sentences": 2, "_why": "doc"}, "consent": {}, "library": {"x": 1},
        "errands": {}, "playbooks": {"meeting": {"done_when": "agreed"}}, "contacts": {}, "circuit": {},
        "tasks": {}, "genome": {"evidence": {}, "thresholds": {}}}


def test_the_shipped_genesis_passes_its_own_check_and_names_its_generation():
    data = json.loads(genome.GENESIS.read_text(encoding="utf-8"))
    assert genome.check(data) == []
    assert "version" not in data, "`version` is now `generation`"
    ident = genome.identity(data)
    assert ident["generation"] == data["generation"] >= 1
    assert len(ident["hash"]) == 16 and set(ident["langs"]) >= {"en", "es"}


def test_a_comment_is_the_same_genome_and_a_value_is_not():
    base = genome.identity(GOOD, packs={})
    commented = json.loads(json.dumps(GOOD))
    commented["style"]["_why"] = "another explanation entirely"
    commented["_comment"] = "new header"
    assert genome.identity(commented, packs={})["hash"] == base["hash"]
    moved = json.loads(json.dumps(GOOD))
    moved["style"]["max_sentences"] = 3
    assert genome.identity(moved, packs={})["hash"] != base["hash"]
    assert genome.identity(GOOD, packs={"es/voice.json": {"a": 1}})["hash"] != base["hash"], "a pack is genome too"


def test_the_check_refuses_a_genome_without_a_generation_or_a_section():
    old = {k: v for k, v in GOOD.items() if k != "generation"} | {"version": 1}
    assert any("generation" in w for w in genome.check(old))
    assert any("`playbooks`" in w for w in genome.check({**GOOD, "playbooks": []}))
    assert any("`meeting`" in w for w in genome.check({**GOOD, "playbooks": {"meeting": "prose"}}))


def _point(monkeypatch, tmp_path, text):
    f = tmp_path / "genesis.json"
    f.write_text(text, encoding="utf-8")
    monkeypatch.setattr(genome, "GENESIS", f)
    monkeypatch.setitem(genome._cache, "data", None)
    return f


def test_a_refused_genesis_reads_as_the_last_good_generation_and_says_so(mem, tmp_path, monkeypatch):
    alerts = []
    monkeypatch.setattr(genome, "_refused", lambda why: alerts.append(why))
    f = _point(monkeypatch, tmp_path, json.dumps(GOOD))
    assert genome.boot()["generation"] == 3
    assert genome.genesis()["library"] == {"x": 1} and not genome.in_fallback()

    import os
    f.write_text('{"generation": 4, "style": {"max_sen', encoding="utf-8")   # half a file
    os.utime(f, ns=(1, 1))
    got = genome.genesis()
    assert got["generation"] == 3 and got["library"] == {"x": 1}, "the reader got the last good generation"
    assert genome.in_fallback() and alerts and "unreadable" in alerts[0]


def test_with_no_good_generation_kept_a_refused_genesis_reads_as_nothing_never_half(mem, tmp_path, monkeypatch):
    monkeypatch.setattr(genome, "_refused", lambda why: None)
    _point(monkeypatch, tmp_path, json.dumps({**GOOD, "generation": 0}))
    assert genome.genesis() == {} and genome.in_fallback()


def test_an_old_install_keeps_its_learned_routes_under_the_playbook_route_name(tmp_path, monkeypatch):
    import sqlite3

    from memory import db as memdb
    from nucleo import routes
    path = tmp_path / "old.db"
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE workflows (id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT NOT NULL, channel TEXT NOT "
              "NULL, rank INTEGER NOT NULL DEFAULT 100, status TEXT NOT NULL DEFAULT 'active', source TEXT NOT NULL "
              "DEFAULT 'seed', target TEXT, evidence TEXT, hits INTEGER NOT NULL DEFAULT 0, ttl_s INTEGER NOT NULL "
              "DEFAULT 604800, checked_at INTEGER, created_at INTEGER NOT NULL, last_hit_at INTEGER, "
              "UNIQUE(domain, channel))")
    c.execute("INSERT INTO workflows (domain, channel, status, source, created_at) VALUES "
              "('wellness','mesh','none','learned',1)")
    c.commit()
    c.close()
    monkeypatch.setenv("ZAELAR_DB", str(path))
    memdb.reset_db()
    try:
        db = memdb.get_db()
        tables = {r[0] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "playbook_routes" in tables and "workflows" not in tables
        from memory import api as memory
        assert [r["channel"] for r in memory.routes_for("wellness")] == ["mesh"]
        assert routes.plan  # the package is the route's runtime
    finally:
        memdb.reset_db()

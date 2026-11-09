"""V2-859 T566 · a new generation absorbs what it now ships, and leaves everything that is his.

On the first boot of a new generation, a learned alias the factory now ships IDENTICAL becomes the factory row. A
learned row that differs stays learned; a learned row he disabled stays his; a seed he disabled stays disabled
(also across the seed re-import); his rules and an operator-pinned route are not touched. The same generation
booted again absorbs nothing.
"""
from __future__ import annotations

import json
import time

from genome import absorb

PACK = {"limpia la pantalla": {"do": "close_all"}, "pantalla completa": {"do": "fullscreen", "widget": "agenda"}}


def _row(mem, phrase):
    return dict(mem.query_one("SELECT source, status, action FROM action_map WHERE lang='xx' AND phrase=?", (phrase,)))


def test_a_new_generation_absorbs_the_identical_and_keeps_the_personal(mem, alias_row, monkeypatch):
    from memory import api as memory
    from nucleo.actionmap import store as amap
    from rules import store as rules

    monkeypatch.setattr(amap, "factory", lambda lang: PACK if lang == "xx" else {})
    events = []
    monkeypatch.setattr(absorb, "_gene", lambda row: events.append(row["phrase"]))
    close_all = json.dumps({"do": "close_all"})
    alias_row("xx", "limpia la pantalla", close_all)                                    # identical
    alias_row("xx", "pantalla completa", json.dumps({"do": "fullscreen", "widget": "notas"}))  # differs
    alias_row("xx", "lo dicho", close_all, status="disabled")                             # his veto
    alias_row("xx", "cierra eso", close_all, source="seed", status="disabled")            # seed he disabled
    memory.route_upsert("hotel", "browser", status="active", rank=1, source="operator", target="x")
    rule = {"id": "u:test", "scope": "global", "kind": "pref", "key": "max_sentences", "value": 1,
            "source": "user", "created_at": time.time()}
    rules.put(rule)

    ident = {"generation": 2, "hash": "aaaa"}
    assert absorb.on_boot(ident) == 1 and events == ["limpia la pantalla"]
    assert _row(mem, "limpia la pantalla")["source"] == "seed"
    assert _row(mem, "pantalla completa")["source"] == "learned", "a learned row that differs stays learned"
    assert _row(mem, "lo dicho") == {"source": "learned", "status": "disabled", "action": close_all}
    assert _row(mem, "cierra eso")["status"] == "disabled"
    assert [r["source"] for r in memory.routes_for("hotel")] == ["operator"]
    assert rules.get("u:test")["value"] == 1

    memory.action_map_add("xx", "cierra eso", close_all)   # the importer runs again: OR IGNORE
    assert _row(mem, "cierra eso")["status"] == "disabled", "a seed he disabled stays disabled"

    mem.execute("UPDATE action_map SET source='learned' WHERE lang='xx' AND phrase='limpia la pantalla'")
    assert absorb.on_boot(ident) == 0, "the same generation booted again absorbs nothing"
    assert absorb.on_boot({"generation": 3, "hash": "bbbb"}) == 1, "a new generation absorbs again"

"""The genome says each change on the timeline (`gene`), so a session replay shows the DNA move where it moved.

V2-859 T567. The learned layer of the genome (playbook routes, action aliases) used to change in silence: a route the
mesh taught, a domain it found empty, a route forgotten, a new seed pack imported — none of it left an event, so the
session player could neither draw it nor show the before and after. Every write now emits ONE `gene` event with the
row as it was and as it is; a write that changed nothing is silent, a row the operator pinned is never moved (and so
never announced), and the event is stamped with the map piece that owns it.
"""
from __future__ import annotations

import pytest

from memory import api as memory
from memory import db as memdb
from nucleo import routes as wf
from nucleo.actionmap import store as amap
from observability import pieces
from voice import observer


@pytest.fixture
def genes(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    got: list = []
    real = observer.emit

    def emit(kind, label, text="", role="", extra=None, piece=None):
        if kind == "gene":
            got.append({"label": label, **(extra or {})})
        return real(kind, label, text=text, role=role, extra=extra, piece=piece)
    monkeypatch.setattr(observer, "emit", emit)
    yield got
    memdb.reset_db()


def test_a_learned_route_says_before_and_after_and_the_same_lesson_again_is_silent(genes):
    wf.learn("massage", wf.store.CH_MESH, target="agent-7", evidence="served it", rank=10)
    assert len(genes) == 1, genes
    g = genes[0]
    assert g["layer"] == "learned" and g["type"] == "route" and g["cause"] == "learned"
    assert g["key"] == "massage/mesh" and g["before"] is None
    assert g["after"] == {"status": "active", "rank": 10, "source": "learned", "target": "agent-7"}
    wf.learn("massage", wf.store.CH_MESH, target="agent-7", evidence="served it again", rank=10)
    assert len(genes) == 1, "the same route learned again changed nothing"


def test_a_domain_found_empty_turns_the_route_into_nothing_serves(genes):
    wf.learn("massage", wf.store.CH_MESH, target="agent-7", rank=10)
    wf.note_empty("massage", evidence="oracle reached, 0 agents")
    g = genes[-1]
    assert g["type"] == "nothing_serves" and g["before"]["status"] == "active" and g["after"]["status"] == "none"
    assert g["evidence"] == "oracle reached, 0 agents"


def test_forgetting_a_domain_says_one_gene_per_route_it_dropped(genes):
    wf.learn("hotel", wf.store.CH_MESH, rank=10)
    wf.learn("hotel", wf.store.CH_BROWSER, rank=20)
    del genes[:]
    wf.forget("hotel")
    assert sorted(g["key"] for g in genes) == ["hotel/browser", "hotel/mesh"], genes
    assert all(g["after"] is None and g["cause"] == "forgotten" and g["before"] for g in genes)


def test_a_route_the_operator_pinned_is_never_moved_so_nothing_is_announced(genes):
    memory.route_upsert("hotel", wf.store.CH_BROWSER, status="active", rank=1, source="operator")
    wf.learn("hotel", wf.store.CH_BROWSER, rank=50)
    wf.note_empty("hotel", wf.store.CH_BROWSER)
    assert genes == []


def test_a_new_seed_pack_is_one_factory_gene_not_one_per_phrase(genes, monkeypatch):
    monkeypatch.setattr(amap, "seed_pack", lambda lang: {"version": 2, "entries": []} if lang == "xx" else {})
    monkeypatch.setattr(amap, "_pack_entries", lambda pack: [
        {"phrase": "abre la agenda", "action": {"op": "open", "widget": "agenda"}},
        {"phrase": "cierra la agenda", "action": {"op": "close", "widget": "agenda"}}])
    from nucleo.actionmap import executor
    monkeypatch.setattr(executor, "validate", lambda action: "")
    amap.ensure_seeded("xx")
    assert len(genes) == 1, genes
    g = genes[0]
    assert g["layer"] == "factory" and g["type"] == "alias" and g["key"] == "xx/seed"
    assert g["before"] is None and g["after"]["version"] == 2 and g["after"]["entries"] == 2
    amap.ensure_seeded("xx")
    assert len(genes) == 1, "the same pack version again imports nothing"


def test_the_gene_event_is_stamped_with_the_genome_piece_that_owns_it():
    assert pieces.piece_for("nucleo/routes/store.py", "gene") == "g_route"
    assert pieces.piece_for("nucleo/actionmap/store.py", "gene") == "g_alias"
    assert pieces.piece_for("memory/routes_store.py") == "st_route"
    assert pieces.piece_for("nucleo/genesis.json") == "g_factory"

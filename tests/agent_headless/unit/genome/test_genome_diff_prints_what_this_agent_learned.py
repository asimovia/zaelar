"""V2-859 T565 · `python -m genome diff` prints the heritable learned genes that differ from this generation.

With their evidence counts, refusals and privacy drops counted by kind (never by value), sorted, offline. A learned
alias the factory already ships identical is not a difference; an operator-pinned route and his rules are personal
and never appear; a route's target never appears.
"""
from __future__ import annotations

import json

from genome import __main__ as cli
from genome import diff


def _seed(alias_row, monkeypatch):
    from memory import api as memory
    from nucleo.actionmap import store as amap
    from widgets import directory

    monkeypatch.setattr(directory, "_contacts", lambda: [])
    monkeypatch.setattr(amap, "factory", lambda lang: {"limpia la pantalla": {"do": "close_all"}})
    alias_row("es", "limpia la pantalla", json.dumps({"do": "close_all"}))               # = factory
    alias_row("es", "quita todo de en medio", json.dumps({"do": "close_all"}), hits=7)  # heritable
    alias_row("es", "ponlo grande", json.dumps({"do": "fullscreen", "widget": "agenda"}), hits=1)
    alias_row("es", "lo que dije", json.dumps({"do": "close_all"}), status="disabled")
    memory.route_upsert("restaurant", "mesh", status="active", rank=10, source="learned", target="casa-ejemplo")
    memory.route_upsert("wellness", "mesh", status="none", rank=999, source="learned")
    memory.route_upsert("hotel", "browser", status="active", rank=1, source="operator", target="his-hotel-site")


def test_the_diff_is_the_heritable_difference_with_its_evidence(mem, alias_row, monkeypatch):
    _seed(alias_row, monkeypatch)
    d = diff.diff()
    assert [(g["type"], g["key"]) for g in d["genes"]] == [
        ("alias", {"lang": "es", "phrase": "quita todo de en medio"}),
        ("nothing_serves", {"domain": "wellness", "channel": "mesh"}),
        ("route", {"domain": "restaurant"}),
    ]
    assert d["genes"][0]["evidence"] == {"hits": 7, "agree": 4, "disagree": 0}
    assert d["refused"] == {"alias: not enough evidence": 1}
    out = json.dumps(d)
    assert "casa-ejemplo" not in out and "his-hotel-site" not in out and "hotel" not in out
    assert d["identity"]["generation"] >= 1
    assert diff.diff() == d, "deterministic"


def test_the_command_prints_one_line_per_gene_and_the_counts(mem, alias_row, monkeypatch, capsys):
    _seed(alias_row, monkeypatch)
    assert cli.main(["diff"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].startswith("genome generation ") and lines[1] == "3 heritable learned gene(s)"
    assert json.loads(lines[2])["key"]["phrase"] == "quita todo de en medio"
    assert lines[-1] == "refused: alias: not enough evidence ×1"
    assert cli.main(["diff", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["genes"]) == 3

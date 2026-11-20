"""The architecture map is the code's portrait, and it may not drift (operator, 2026-11-07).

`.meshkore/docs/architecture/zaelar-architecture-map.json` is the ONE representation of the agent's pieces that the
others are aligned to (the web's Technology pages, the session player, the pieces events declare). The code is its
source; this test is what keeps it true:

  · every path a piece or an external names EXISTS;
  · every root package of the engine is drawn somewhere or listed in `not_drawn` with its reason;
  · every model id the model table (`config/models.default.json`) can call is on an external box, and every model id
    a box claims is one the table (or the Jev client) really uses;
  · ids are unique and every flow joins two pieces that are in the map.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAP = json.loads((ROOT / ".meshkore/docs/architecture/zaelar-architecture-map.json").read_text(encoding="utf-8"))
BOXES = MAP["pieces"] + MAP["external"]


def _table_models() -> set[str]:
    table = json.loads((ROOT / "config/models.default.json").read_text(encoding="utf-8"))
    out: set[str] = set()
    for svc in table["services"].values():
        for seat in ("titular", "failover"):
            s = svc.get(seat) or {}
            out |= {s[k] for k in ("model", "fast_model") if s.get(k)}
    return out


def test_every_path_in_the_map_exists():
    missing = [(b["id"], p) for b in BOXES for p in b.get("paths", []) + b.get("called_from", []) if not (ROOT / p).exists()]
    missing += [("relays", p) for p in MAP.get("relays", []) if not (ROOT / p).exists()]
    assert not missing, f"the map names code that is not there: {missing}"


def test_every_root_package_is_drawn_or_said_why_not():
    drawn = {p.split("/")[0] for b in BOXES for p in b.get("paths", []) + b.get("called_from", [])}
    packages = {d.name for d in ROOT.iterdir() if d.is_dir() and (d / "__init__.py").exists()}
    loose = packages - drawn - set(MAP["not_drawn"])
    assert not loose, f"root packages the map does not account for: {sorted(loose)}"


def test_the_models_are_the_ones_the_table_calls():
    claimed = {m for b in MAP["external"] for m in b.get("model_ids", [])}
    table = _table_models()
    assert table <= claimed, f"the model table calls ids no box shows: {sorted(table - claimed)}"
    jev = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "nucleo/jev").glob("*.py"))
    ghosts = {m for m in claimed - table if m not in jev}
    assert not ghosts, f"boxes claim ids nothing calls: {sorted(ghosts)}"


def test_ids_are_unique_and_flows_join_pieces_of_the_map():
    ids = [b["id"] for b in BOXES]
    assert len(ids) == len(set(ids)), "an id is repeated"
    zones = {z["id"] for z in MAP["zones"]}
    assert all(b["zone"] in zones for b in BOXES)
    flow_ids = [f["id"] for f in MAP["flows"]]
    assert len(flow_ids) == len(set(flow_ids))
    loose = [f["id"] for f in MAP["flows"] if f["a"] not in ids or f["b"] not in ids]
    assert not loose, f"flows to pieces the map does not have: {loose}"


STATUSES = {"retiring"}
DIRS = {"a>b", "b>a", "both"}


def test_status_and_direction_are_ones_the_schema_names():
    bad = [(x["id"], x["status"]) for x in MAP["zones"] + BOXES if "status" in x and x["status"] not in STATUSES]
    bad += [(f["id"], f["dir"]) for f in MAP["flows"] if "dir" in f and f["dir"] not in DIRS]
    assert not bad, f"a status or a direction the schema (`_schema`) does not name: {bad}"


def test_a_planned_piece_points_at_nothing_yet_and_is_never_a_flow():
    planned = MAP.get("planned", [])
    ids = {b["id"] for b in BOXES}
    zones = {z["id"] for z in MAP["zones"]}
    assert all("paths" not in p and p["zone"] in zones and p["id"] not in ids for p in planned), \
        "a planned piece has paths, an unknown zone, or the id of a built one"
    assert all(r in ids for p in planned for r in p.get("replaces", [])), "a planned piece replaces an id the map does not have"
    named = {p["id"] for p in planned}
    assert not [f["id"] for f in MAP["flows"] if f["a"] in named or f["b"] in named], "a flow joins a planned piece"


def test_every_view_draws_only_ids_the_map_has():
    known = {b["id"] for b in BOXES} | {p["id"] for p in MAP.get("planned", [])} | {z["id"] for z in MAP["zones"]}
    planned = {p["id"] for p in MAP.get("planned", [])}
    for name, view in MAP.get("views", {}).items():
        if name.startswith("_"):
            continue
        own = {b["id"] for b in view["outside"]}
        assert not own & known, f"{name}: an aggregate box reuses a map id"
        assert all(z in known for z in view["frame"]["zones"]), f"{name}: the frame names an unknown zone"
        assert all(i in known for i in view["inside"]), f"{name}: an inside id the map does not have"
        assert all(s in known for b in view["outside"] for s in b["stands_for"]), f"{name}: a box stands for nothing"
        drawn = set(view["inside"]) | own
        for e in view["edges"]:
            assert e["from"] in drawn and e["to"] in drawn, f"{name}: an edge to an id the view does not draw: {e}"
            assert e["dir"] in DIRS and e.get("status", "built") in STATUSES | {"built", "decided"}, f"{name}: {e}"
            if {e["from"], e["to"]} & planned:
                assert e.get("status") == "decided", f"{name}: an edge to a planned piece drawn as built: {e}"

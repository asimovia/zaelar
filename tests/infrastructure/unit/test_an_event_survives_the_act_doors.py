"""An event of the act doors survives their fold (V2-826 §2b, refactor2710-06).

The section folds the media, message, errand, memory and search files of `nucleo/flash` into `nucleo/acts/`. A fold
may carry an `emit(...)` to another file; it may never drop it. This freezes what the doors emit with literal
arguments. A pair added later passes; a pair retired on purpose leaves this set in the same commit, with the reason.
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

FROZEN_PAIRS = {
    # T-05 · the search door (from flash/search_routing, search_turn, listing_turn and the voice lane); the old turn's
    # web search, its shadow route and its outward-act gate went with it (INI-078 L1) — the manager's own doors emit theirs
    ("brain", "🛒 la pasada rápida acabó después del turno"), ("search", "🛒 búsqueda de anuncios"),
    ("widget", "show"),
}


def _emitted() -> set:
    pairs = set()
    for p in (ENGINE / "nucleo/acts").rglob("*.py"):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if not isinstance(n, ast.Call):
                continue
            name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
            if name == "apply" and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                pairs.add(("widget", n.args[0].value))   # through the one canvas door, which emits `widget/<op>`
                continue
            if "emit" in name and len(n.args) > 1 and all(isinstance(a, ast.Constant) for a in n.args[:2]):
                pairs.add((n.args[0].value, n.args[1].value))
    return pairs


def test_no_frozen_event_of_the_act_doors_vanishes():
    assert not sorted(FROZEN_PAIRS - _emitted()), f"an event stopped being emitted: {sorted(FROZEN_PAIRS - _emitted())}"


def test_disarm_a_dropped_event_is_named():
    pairs = _emitted()
    assert sorted(FROZEN_PAIRS - (pairs - {("search", "🛒 búsqueda de anuncios")})) == [("search", "🛒 búsqueda de anuncios")]


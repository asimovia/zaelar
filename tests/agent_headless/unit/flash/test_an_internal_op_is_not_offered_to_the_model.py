"""An op the card fires by itself is never offered to the model.

`ended`, `enrich_art`, `player_error`, `player_quality`, `player_audio` are reports a card sends about itself;
the model must never call them, and listing them in every turn's prompt was paid on every turn — the same budget
the turn-prompt ceiling guards. They are declared `"internal": true` in the card's manifest, and the catalog skips
them. Declared data, not a reading of the description.
"""
from __future__ import annotations

import json
from pathlib import Path

from widgets import brief

ROOT = Path(__file__).resolve().parents[4]


def _declared_internal() -> dict[str, list[str]]:
    out = {}
    for p in sorted((ROOT / "widgets").glob("*/manifest.json")):
        acts = json.loads(p.read_text(encoding="utf-8")).get("actions") or {}
        names = [n for n, s in acts.items() if isinstance(s, dict) and s.get("internal") is True]
        if names:
            out[p.parent.name] = names
    return out


def test_the_cards_that_report_on_themselves_declare_it():
    declared = _declared_internal()
    assert {"ended", "enrich_art"} <= set(declared.get("musica", []))
    assert {"player_error", "player_quality", "player_audio"} <= set(declared.get("youtube", []))


def test_the_catalog_never_names_an_internal_op():
    text = brief.for_prompt(open_ids=["musica", "youtube"])
    for wid, names in _declared_internal().items():
        row = next((ln for ln in text.splitlines() if ln.startswith(f"- {wid} ")), "")
        assert row, f"{wid} is missing from the catalog"
        for n in names:
            assert f"{n}," not in row and not row.rstrip().endswith(n), f"{wid}:{n} offered to the model"
    assert "add_tracks" in text and "play_playlist" in text, "ordinary ops are still offered"


def test_an_op_whose_only_object_is_a_held_row_is_named_by_that_row_not_by_the_catalog():
    """`open_draft` / `discard_draft` act only on a held draft, and a held draft reaches every turn as a pending-work
    row that names those verbs (V2-807 T-10). Naming them in the catalog too cost every turn, with or without a
    draft — part of what put the composed prompt over its ceiling. Declared data (`"row_verb": true`)."""
    acts = json.loads((ROOT / "widgets" / "mensajeria" / "manifest.json").read_text(encoding="utf-8"))["actions"]
    row_verbs = {n for n, s in acts.items() if isinstance(s, dict) and s.get("row_verb") is True}
    assert {"open_draft", "discard_draft"} <= row_verbs
    offered = brief._offered_action_names(acts)
    assert not [o for o in offered if o.split("(")[0] in row_verbs], "a row verb is offered on every turn"
    assert "send_draft(confirmar)" in offered and "draft" in offered, "the draft ops he speaks are still offered"

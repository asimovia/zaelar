"""A sure «close» verdict yields to the order INSIDE the card it would close (agenda-everyday-edits ES, 2026-10-11).

Two red steps, one class. «Vale, ya la puedes cerrar» (the dentist's detail open) read canvas=close 1.00 AND
`agenda:close_meeting` 1.00; «Y quita el piano entero, toda la serie» read canvas=close 0.91 AND
`agenda:cancel_meeting` 0.71. The model called nothing and said «Hecho.»; the canvas completion
(`direct_action.complete_canvas`, both channels) ran FIRST and closed the whole agenda — the detail stayed «open»
in the card's state and six piano lessons stayed in the calendar. `canvas_yields` (V2-781 pair 5) already said a
sure inner op wins, but only at the data completion, which the canvas completion pre-empted.

Nodes: 2.440 a sure inner op wins over the close (both channels); 2.441 an inner WRITE is never read as a close
and is left to the repair; 2.442 a named card and an unsure inner lens keep the close (R4 / M4); 2.443 the claim
backing cancels the WHOLE series he named by one word; 2.444 the rename field is named as the NEW title.
"""
from __future__ import annotations

import json
import pathlib



ENGINE = pathlib.Path(__file__).resolve().parents[4]


# ── 2.440 · a sure inner op wins over the close — in both channels ────────────────────────────────────────────

# ── 2.441 · an inner WRITE is never read as a close ───────────────────────────────────────────────────────────

# ── 2.442 · the close stands when he named a card, or the inner op is an unsure lens ──────────────────────────

# ── an ARRANGE yields to a sure action on a card too (demo sandbox 2026-10-28, S2) ────────────────────────────

# ── 2.443 · the claim backing cancels the whole series he named by one word ───────────────────────────────────

def _agenda():
    series = {"freq": "weekly", "interval": 1, "until": "2026-11-30", "days": [1]}
    return {"meetings": [{"title": "Clase de piano de Abril", "date": "2026-10-27", "startTime": "17:00",
                          "repeat": series},
                         {"title": "Clase de piano de Abril", "date": "2026-10-14", "startTime": "17:00",
                          "fromSeries": "2026-10-13"},
                         {"title": "Revisión dental con el doctor Ruiz", "date": "2026-10-15", "startTime": "11:30"}]}


# ── 2.444 · the rename field reads as the NEW title, the selector as the current one ──────────────────────────

def test_the_rename_field_is_the_new_title():
    spec = json.loads((ENGINE / "widgets/agenda/manifest.json").read_text(encoding="utf-8"))
    pay = spec["actions"]["update_meeting"]["payload"]
    assert "NUEVO" in pay["newTitle"] and "ACTUAL" in pay["title"]

"""A client STATE report is not a person doing anything.

`POST /api/ui-event` with `src="frontend"` carries what the tab itself saw happen — it went to the foreground, the
agent state moved, the mic analyzer opened. Those events counted as real activity, so a tab merely coming to the
foreground moved the activity clock: a hosted engine stayed awake, and its session read as active, with nobody there.
What the operator DOES (`src="user"`, a tap) still counts."""
from __future__ import annotations

import asyncio

from observability import identity
from server import voice_api


def _activity_after(monkeypatch, payload) -> list[bool]:
    marks: list[bool] = []
    real = identity.note_real_activity

    def _spy():
        marks.append(not identity.is_paced())
        return real()
    monkeypatch.setattr(identity, "note_real_activity", _spy)
    monkeypatch.setattr(identity, "end_session", lambda *a, **k: {})
    asyncio.run(voice_api.ui_event(payload))
    return marks


def test_the_tab_going_to_the_foreground_does_not_move_the_activity_clock(monkeypatch):
    marks = _activity_after(monkeypatch, {"kind": "ui", "action": "tab:visibility", "state": "visible", "src": "frontend"})
    assert not any(marks), "a client state transition counted as a person"


def test_a_tap_still_counts(monkeypatch):
    marks = _activity_after(monkeypatch, {"kind": "ui", "action": "orb:power", "src": "user"})
    assert marks and all(marks)

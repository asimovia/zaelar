"""A typed line that starts with `LOG:` is a note on the timeline, never a turn (INI-042 #37).

Measured: notes the operator left for support inside his session («LOG: …») were answered, routed, and one opened an
errand. At the typed door the prefix now writes one `feedback` event and the line never reaches the session.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from nucleo.input import support_note


@pytest.mark.parametrize("line, note", [("LOG: latency again on T52", "latency again on T52"),
                                        ("  log : the wall doubled", "the wall doubled"),
                                        ("LOG:::still slow", "still slow"),
                                        ("Log:", "")])
def test_the_prefix_is_recognised_in_any_case(line, note):
    assert support_note.body(line) == note


@pytest.mark.parametrize("line", ["Add a log entry: walked 5 km", "logo: change it", "the LOG: is here", ""])
def test_an_ordinary_line_is_not_a_note(line):
    assert support_note.body(line) is None


def test_the_typed_door_records_the_note_and_hands_nothing_to_the_session(monkeypatch):
    from server import screens_api
    events, delivered = [], []
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: events.append((a, k)))

    async def _deliver(text, dev):
        delivered.append(text)
        return True
    monkeypatch.setattr(screens_api.screens, "deliver_typed", _deliver)

    r = asyncio.run(screens_api.chat(text="LOG: T53 opened an errand", dev="desk:1"))
    assert json.loads(r.body) == {"ok": True, "note": True}
    assert delivered == [], "a note never becomes a turn"
    (args, kw), = events
    assert args[0] == "feedback" and kw["text"] == "T53 opened an errand" and kw["extra"]["support_note"] is True

    asyncio.run(screens_api.chat(text="Add a dentist on Friday", dev="desk:1"))
    assert delivered == ["Add a dentist on Friday"], "an ordinary line still reaches the session"

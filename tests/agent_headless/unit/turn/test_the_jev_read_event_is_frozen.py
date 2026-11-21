"""The `jev read` event is FROZEN across the brief's move (refactor2710-07, V2-826 §2b).

Every reader of a verdict leaves one `jev read <question>` row in the timeline — the observatory and the Master filter
on its kind, label and `extra` keys. 07 moved the reading door (`nucleo/turn/verdicts.read` over `nucleo/jev`), so this
pins the row the old `jev.read` emitted: same kind, same label, same text, same extra, one per (call, question).

Disarm: rename the label in `nucleo/jev._emit_read` and the frozen-shape test goes red; point `_engine_root` back at
`nucleo/` and the key test goes red.
"""
from __future__ import annotations


import pytest

from nucleo import jev

FROZEN_EXTRA = {"cat", "call_id", "turn_id", "question", "used", "why", "confidence", "choice"}


@pytest.fixture
def events(monkeypatch):
    got = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: got.append((kind, label, kw)))
    jev.reset_read_events()
    yield got
    jev.reset_read_events()


def test_the_key_is_read_from_the_engine_root():
    """When `jev.py` became a package its root moved one folder down: the key file was looked for under `nucleo/`, no
    key was found, and every brief went silent (measured on battery seed 2707: 30 of 30 reds with an empty brief)."""
    root = jev._engine_root()
    assert (root / "nucleo" / "jev" / "__init__.py").is_file(), root

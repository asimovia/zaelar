"""The embedded voice is refused: the voice always runs in its own process (INI-078 F2, after the unplug).

`ZAELAR_VOICE_EMBEDDED=1` kept the LiveKit worker inside the body, and that worker built the old turn's voice node
(`build_llm` → its `llm_node`, a kickoff greeting by `generate_reply`) with no switch and no manager's ear — the last
live entry to the old turn. Asked for it, the body says no on his screen and builds the voice process as always.
"""
from __future__ import annotations

import sys

from voice import child_process


def test_asked_to_embed_the_voice_it_says_no_and_builds_its_own_process(monkeypatch):
    from voice import observer
    alerts = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: alerts.append((kind, label)))
    monkeypatch.setenv("ZAELAR_VOICE_EMBEDDED", "1")
    monkeypatch.delitem(sys.modules, "voice.engine.pipeline.agent", raising=False)
    assert child_process.factory() is child_process.make_child
    assert not child_process.embedded() and child_process.asked_embedded()
    assert ("alert", "the embedded voice is refused: it runs in its own process") in alerts
    assert "voice.engine.pipeline.agent" not in sys.modules, "the embedded worker (the old voice node) is never built"


def test_not_asked_it_builds_its_own_process_saying_nothing(monkeypatch):
    from voice import observer
    alerts = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: alerts.append((kind, label)))
    monkeypatch.delenv("ZAELAR_VOICE_EMBEDDED", raising=False)
    assert child_process.factory() is child_process.make_child and alerts == []

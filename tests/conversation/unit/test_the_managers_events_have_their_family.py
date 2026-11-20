"""The manager's events have their family, and it counts as his activity (node 13.117, V2-941, plan v3.2 C17/C21).

Every kind the package declares (`conversation.telemetry.KINDS`) is stamped `conversation` on the bus (as the viewer
and the Master group them), the viewer lists that family, and an event of it is REAL activity for the engine's idle clock
(`observability/flows.REAL_ACTIVITY_WHERE`, which only `system` and `pulse` stay out of) — a session the manager is
talking in never looks idle.

Disarms seen red: a kind dropped from the observer's families; the family made `system`.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from conversation.telemetry import KINDS

ENGINE = Path(__file__).resolve().parents[3]


def test_every_kind_the_package_declares_is_of_the_family():
    from voice import observer
    assert {k: observer._CAT.get(k) for k in KINDS} == dict.fromkeys(KINDS, "conversation")


def test_the_bus_carries_it_stamped(monkeypatch):
    import bus
    from voice import observer
    got = []
    monkeypatch.setattr(bus, "emit_sync", lambda topic, ev, *a, **k: got.append(dict(ev)) if topic == "observer"
                        else None)
    observer.emit("conv_run", "started", extra={"refs": {"run": "run_1"}})
    assert [e.get("cat") for e in got if e.get("kind") == "conv_run"] == ["conversation"]


def test_it_is_real_activity_for_the_idle_clock():
    from observability.flows import REAL_ACTIVITY_WHERE
    from voice import observer
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE events (kind TEXT, cat TEXT, payload TEXT)")
    db.executemany("INSERT INTO events VALUES (?, ?, ?)",
                   [(k, observer._CAT[k], "{}") for k in KINDS] + [("pulse", "pulse", "{}")])
    real = {k for (k,) in db.execute(f"SELECT kind FROM events WHERE {REAL_ACTIVITY_WHERE}")}
    assert real == set(KINDS)


def test_the_viewer_lists_the_family():
    js = (ENGINE / "frontend/app/components/DebugPanel.js").read_text(encoding="utf-8")
    assert 'key: "conversation"' in js and 'conversation: "debug.cat_conversation"' in js

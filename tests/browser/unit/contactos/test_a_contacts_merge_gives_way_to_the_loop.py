"""A contacts merge in the widget thread gives the loop its turn (E0, node 3.204).

Measured 2026-11-12: `sync_contacts` ran 13.4 s in the `widget-data` thread while the host paged the body in from
swap, and the loop did not run. The merges now call `imports.give_way(i)` once per row: every `GIVE_WAY_EVERY` rows
the thread yields the interpreter, and while the body's loop is stalling (`nucleo/pulse/loop_lag`) it also waits,
so the host has room to run the loop before the next batch.

Disarm (seen red): drop the `give_way(i)` call from either merge loop → the seam is never reached.
"""
from __future__ import annotations

from collections import deque

import pytest

from nucleo.pulse import loop_lag
from widgets.contactos import gmerge, imports


@pytest.fixture
def meter(monkeypatch):
    from nucleo.workers import envelope
    monkeypatch.setattr(envelope, "policy", lambda: {**envelope._DEFAULTS, "loop_lag_s": 1.0})
    monkeypatch.setattr(loop_lag, "_state", {"loops": set(), "last": 0.0, "worst": 0.0, "n": 0, "total_s": 0.0,
                                             "stalls": deque(maxlen=64), "last_stall": None})
    monkeypatch.setattr(loop_lag, "_say", lambda s: None)
    monkeypatch.setattr(loop_lag, "_shed", lambda s: None)
    slept: list = []
    monkeypatch.setattr(loop_lag.time, "sleep", slept.append)
    return slept


def test_the_google_merge_reaches_the_seam_on_every_row(meter, monkeypatch):
    seen = []
    monkeypatch.setattr(loop_lag, "give_way", lambda i, every=50: seen.append((i, every)))
    rows = [{"name": f"Persona {i}", "googleId": f"g{i}", "email": f"p{i}@example.com"} for i in range(120)]
    out = gmerge.merge_imported({}, rows)
    assert out["added"] == 120 and seen == [(i, imports.GIVE_WAY_EVERY) for i in range(120)]


def test_the_platform_merge_reaches_the_seam_on_every_row(meter, monkeypatch):
    seen = []
    monkeypatch.setattr(loop_lag, "give_way", lambda i, every=50: seen.append((i, every)))
    rows = [{"name": f"Persona {i}", "externalIds": {"telegram": f"t{i}"}} for i in range(120)]
    out = imports.merge_contacts({}, rows, source="telegram")
    assert out["added"] == 120 and seen == [(i, imports.GIVE_WAY_EVERY) for i in range(120)]


def test_the_thread_paces_itself_while_the_body_loop_stalls(meter):
    assert imports.give_way(0) is False and meter == [0], "the interpreter is yielded, nothing more"
    loop_lag.note(2.0)                                   # the host stopped the loop a moment ago
    assert imports.give_way(50) is True and meter[-1] == 0.05
    assert imports.give_way(51) is False and len(meter) == 2

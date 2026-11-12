"""The body measures its own event loop and names the host that stopped it (E0, node 3.201).

Measured 2026-11-12 on a host out of memory: the body's loop stopped in stretches of 12–31 s and nothing in the body
read it — the lag watcher runs in the voice process since V2-891 — so the engine blamed the model, the provider and
found the body «unreachable». Now `nucleo/pulse/loop_lag` probes the server loop: a late wake over `loop_lag_s` is a
STALL — recorded with its end, one `health` event, a quiet shed through the lag reader (`BODY` source), pressure for
the shed ladder as `cause=machine`, and `GET /api/debug/loop` answers from the process.

Disarms (each seen red): `note()` never appends to `_state["stalls"]` → (a) and (c); `shed_ladder._lag` reads only
`voice_lag_s` → (c); `give_way` never sleeps while the loop stalls → (e).
"""
from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections import deque
from pathlib import Path

import pytest

from nucleo.pulse import loop_lag, shed_actuators, shed_ladder


@pytest.fixture
def world(monkeypatch):
    from nucleo.workers import envelope
    from voice import lag, observer
    seen = {"events": [], "shed": [], "unshed": []}
    monkeypatch.setattr(envelope, "policy", lambda: {**envelope._DEFAULTS, "loop_lag_s": 0.3, "voice_lag_s": 0.5})
    monkeypatch.setattr(observer, "emit", lambda kind, label, **k: seen["events"].append((kind, label, k.get("extra") or {})))
    monkeypatch.setattr(envelope, "shed", lambda s, source: seen["shed"].append(source))
    monkeypatch.setattr(envelope, "unshed", lambda source: seen["unshed"].append(source))
    monkeypatch.setattr(lag, "_state", {**lag._state, "loops": set()})
    monkeypatch.setattr(loop_lag, "_state", {"loops": set(), "last": 0.0, "worst": 0.0, "n": 0, "total_s": 0.0,
                                             "stalls": deque(maxlen=64), "last_stall": None})
    return seen


def test_a_stalled_loop_is_recorded_said_once_and_shed_quietly(world):
    """(a) the probe on the loop reads the stall, (b) one `health` event with the seconds, the shed by the BODY
    source — and no spoken line, a stopped loop is never the audio path."""
    t0 = time.monotonic()

    async def session():
        assert loop_lag.watch() is True and loop_lag.watch() is False, "idempotent per loop"
        await asyncio.sleep(0.05)
        time.sleep(1.2)                      # the loop is held — the host, in the measured case
        await asyncio.sleep(0.3)
    asyncio.run(session())
    health = [e for e in world["events"] if e[0] == "health" and e[2].get("kind_diag") == "loop_lag"]
    assert len(health) == 1 and health[0][2]["lag_s"] >= 0.6 and health[0][2]["source"] == "body_loop", world["events"]
    assert "body_loop" in world["shed"] and "voice_loop" not in world["shed"]
    assert loop_lag.stalled_since(mono=t0) >= 0.6 and loop_lag.stalled_since(mono=time.monotonic()) == 0.0
    st = loop_lag.status()
    assert st["stalls"] == 1 and st["last_stall"]["s"] >= 0.6 and st["watching"] and st["bound_s"] == 0.3


def test_a_loop_on_time_records_nothing_and_releases_the_hold(world):
    assert loop_lag.note(0.05) is False
    assert not world["events"] and not world["shed"] and world["unshed"] == ["body_loop"]
    assert loop_lag.stalled_recently(60.0) == 0.0 and loop_lag.status()["stalls"] == 0


def test_the_ladder_reads_the_body_loops_stalls_as_the_machines_pressure(world, monkeypatch):
    """(c) within our budgets, a stalled body loop descends the ladder with `cause=machine`; a beat without a stall
    lets it recover."""
    from nucleo.workers import envelope
    gb = 2 ** 30
    monkeypatch.setattr(envelope, "measured", lambda: (16 * gb, 12 * gb))     # plenty of memory: only the lag acts
    monkeypatch.setattr(shed_actuators, "_rss_mb", lambda pid=None: 200.0)
    monkeypatch.setattr(shed_actuators, "_workers", lambda: [])
    quiet = shed_actuators.reading()
    assert quiet["loop_lag_s"] == 0.0 and not shed_ladder.pressure(quiet)
    loop_lag.note(2.5)
    r = shed_actuators.reading()
    assert r["loop_lag_s"] == 2.5 and r["lag_bound_s"] == 0.3 and r["cause"] == "machine"
    assert shed_ladder.pressure(r) and not shed_ladder.recovered(r)
    assert shed_ladder.Ladder(rungs=("a",)).step(r) == {"engage": "a", "cause": "machine", "depth": 1}
    later = {**r, "loop_lag_s": 0.0}
    assert shed_ladder.recovered(later), "a beat without a stall, over the floor with margin: the ladder climbs back"


def test_the_bound_is_declared_beside_the_envelope():
    d = json.loads((Path(loop_lag.__file__).resolve().parents[2] / "config" / "resources.default.json").read_text())
    assert d["loop_lag_s"] == 1.0


def test_the_boot_starts_the_probe_and_the_debug_route_answers_from_the_process(world):
    from server import voice_api
    from server.boot import surfaces
    assert "loop_lag.watch()" in inspect.getsource(surfaces)
    assert '"/api/debug/loop"' in inspect.getsource(voice_api)
    loop_lag.note(1.2)
    assert asyncio.run(voice_api.debug_loop()).body and loop_lag.status()["stalled_total_s"] == 1.2


def test_heavy_work_gives_way_every_n_rows_and_paces_only_while_the_loop_stalls(world, monkeypatch):
    """(e) a merge in the widget thread yields the interpreter every N rows; with a stall in the window it also waits,
    so the host has room to run the loop."""
    slept = []
    monkeypatch.setattr(loop_lag.time, "sleep", slept.append)
    assert loop_lag.give_way(0) is False and loop_lag.give_way(1) is False and loop_lag.give_way(50) is False
    assert slept == [0, 0], "every N rows the interpreter is yielded, nothing more while the loop is fine"
    loop_lag.note(1.5)
    assert loop_lag.give_way(100) is True and slept[-1] == 0.05
    assert loop_lag.give_way(101) is False and len(slept) == 3

"""The body measures its own event loop and names the host that stopped it (E0, node 3.201).

Measured 2026-11-12 on a host out of memory: the body's loop stopped in stretches of 12–31 s and nothing in the body
read it — the lag watcher runs in the voice process since V2-891 — so the engine blamed the model, the provider and
found the body «unreachable». Now `nucleo/pulse/loop_lag` probes the server loop: a late wake over `loop_lag_s` is a
STALL — recorded with its end, one `health` event, a quiet shed through the lag reader (`BODY` source), pressure for
the shed ladder as `cause=machine`, and `GET /api/debug/loop` answers from the process.

Disarms (each seen red): `note()` never appends to `_state["stalls"]` → (a) and (c); `shed_ladder._lag` drops
`loop_lag_s` → (c); `give_way` never sleeps while the loop stalls → (e); the ladder reading the last 60 s instead of
the persisting beat → (f); `whose` always `host` → (g) and (h); recovery reading the persisting `min` → (i).
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
    health = [e for e in world["events"] if e[0] == "homeostasis" and e[2].get("kind_diag") == "loop_lag"]
    assert len(health) == 1 and health[0][2]["lag_s"] >= 0.6 and health[0][2]["source"] == "body_loop", world["events"]
    assert "body_loop" in world["shed"] and "voice_loop" not in world["shed"]
    assert loop_lag.stalled_since(mono=t0) >= 0.6 and loop_lag.stalled_since(mono=time.monotonic()) == 0.0
    st = loop_lag.status()
    assert st["stalls"] == 1 and st["last_stall"]["s"] >= 0.6 and st["watching"] and st["bound_s"] == 0.3


def test_a_loop_on_time_records_nothing_and_releases_the_hold(world):
    assert loop_lag.note(0.05) is False
    assert not world["events"] and not world["shed"] and world["unshed"] == ["body_loop"]
    assert loop_lag.stalled_since() == 0.0 and loop_lag.status()["stalls"] == 0


_CLOCK = {"t": 1000.0}    # the beats' monotonic clock: 30 s between a beat and a stall, a stall and the next beat


def _beat():
    _CLOCK["t"] += 30.0
    return shed_actuators.reading()


def _stall(lag: float, **kw):
    """A stall that ran entirely between the last beat and the next one (counted by its overlap with the beat)."""
    _CLOCK["t"] += 30.0
    loop_lag.note(lag, mono=_CLOCK["t"], **kw)


@pytest.fixture
def host_with_memory(world, monkeypatch):
    from nucleo.workers import envelope
    gb = 2 ** 30
    monkeypatch.setattr(envelope, "measured", lambda: (16 * gb, 12 * gb))     # plenty of memory: only the lag acts
    monkeypatch.setattr(shed_actuators, "_rss_mb", lambda pid=None: 200.0)
    monkeypatch.setattr(shed_actuators, "_workers", lambda: [])
    monkeypatch.setattr(shed_actuators, "_L", {"ladder": None, "beat_at": None, "beat_lag": None})
    import types
    monkeypatch.setattr(shed_actuators, "time", types.SimpleNamespace(monotonic=lambda: _CLOCK["t"]))
    return world


def test_the_ladder_reads_a_loop_the_host_keeps_stopping_as_the_machines_pressure(host_with_memory):
    """(c) within our budgets, a body loop stalled beat after beat descends the ladder with `cause=machine`; a beat
    without a stall lets it recover."""
    quiet = _beat()
    assert quiet["loop_lag_s"] == 0.0 and not shed_ladder.pressure(quiet)
    _stall(2.5, faults=3)                     # the process paged while its loop thread did not run
    _beat()
    _stall(1.5, faults=1)
    r = _beat()
    assert r["loop_lag_s"] == 1.5 and r["lag_bound_s"] == 0.3 and r["cause"] == "machine"
    assert shed_ladder.pressure(r) and not shed_ladder.recovered(r)
    assert shed_ladder.Ladder(rungs=("a",)).step(r) == {"engage": "a", "cause": "machine", "depth": 1}
    later = _beat()
    assert later["loop_lag_s"] == 0.0 and shed_ladder.recovered(later), \
        "a beat without a stall, over the floor with margin: the ladder climbs back"


def test_a_lone_hiccup_is_never_the_ladders_pressure(host_with_memory):
    """(f) E3: one 1 s stall used to count as pressure for the whole next minute — the ladder went down rung by rung
    with memory to spare. A stall is counted in ONE beat, and only a stall in two beats running is pressure."""
    _beat()
    _stall(1.0)
    r = _beat()
    assert r["loop_lag_s"] == 0.0 and not shed_ladder.pressure(r), "one hiccup descended the ladder"
    again = _beat()
    assert again["loop_lag_s"] == 0.0, "a stall was counted again in the next beat"


def test_whose_stall_it_was_is_measured_never_assumed(host_with_memory):
    """(g) E3: a stall while the process ran on the CPU is the engine's own work holding its loop — said so, and
    named `cause=engine` by the ladder, never «host stalled»."""
    for cpu, faults, who in ((1.1, 0, "engine"), (0.05, 2, "host"), (0.05, 0, "unknown"), (None, 0, "unknown")):
        loop_lag.note(1.2, cpu_s=cpu, faults=faults)
        assert loop_lag.status()["last_stall"]["whose"] == who, (cpu, faults)
    loop_lag._state["stalls"].clear()
    host_with_memory["events"].clear()
    _beat()
    _stall(1.2, cpu_s=1.2)
    _beat()
    _stall(1.4, cpu_s=1.3)
    r = _beat()
    assert shed_ladder.pressure(r) and r["cause"] == "engine"
    said = [e for e in host_with_memory["events"] if e[2].get("kind_diag") == "loop_lag"]
    assert said and all(e[2]["whose"] == "engine" and e[2]["cause"] == "engine" for e in said)
    assert not any("host stalled" in e[1] for e in said), said
    assert loop_lag.stalled_since(who="engine") == 2.6 and loop_lag.stalled_since(who="host") == 0.0


def test_the_probe_reads_the_loop_threads_cpu_and_the_page_faults(world, monkeypatch):
    """(h) the probe hands `note` the LOOP THREAD's CPU and the major faults over the wake (E3 audit: the process's CPU
    summed every thread). Deterministic: the clocks are counters, the hold only has to pass the 0.3 s bound."""
    feed = {"cpu": 0.0, "step": 0.0, "faults": 0, "fstep": 0}

    def thread_time():
        feed["cpu"] += feed["step"]
        return feed["cpu"]

    def faults():
        feed["faults"] += feed["fstep"]
        return feed["faults"]
    monkeypatch.setattr(loop_lag.time, "thread_time", thread_time)
    monkeypatch.setattr(loop_lag, "_major_faults", faults)

    async def session():
        loop_lag.watch()
        await asyncio.sleep(0.05)
        time.sleep(1.0)                      # the probe wakes ~0.55 s late: over the 0.3 s bound
        await asyncio.sleep(0.3)
    for step, fstep in ((1.0, 0), (0.0, 1), (0.0, 0)):
        feed.update(step=step, fstep=fstep)
        asyncio.run(session())
    said = [e[2]["whose"] for e in world["events"] if e[2].get("kind_diag") == "loop_lag"]
    assert said == ["engine", "host", "unknown"], said
    assert not any("host stalled" in e[1] for e in world["events"] if e[2].get("whose") != "host")


def test_a_rung_is_released_only_by_a_beat_without_a_stall(host_with_memory):
    """(i) E3 audit: recovery read the same persisting `min` as pressure, so with a stall every other beat the ladder
    released a rung on a beat that had one. Pressure is what persists; recovery is what THIS beat shows."""
    lad = shed_ladder.Ladder(rungs=("a", "b"), engaged=["a", "b"])
    _beat()
    released = []
    for stall in (True, False, True, False):
        if stall:
            _stall(1.5, faults=1)
        act = lad.step(_beat())
        released.append(bool(act and "release" in act))
    assert released == [False, True, False, True], released


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


"""A held worker says its TRUE reason and is admitted by measured room, one at a time (V2-867 F0+F1).

Measured 2026-11-09: a job said «waiting for free memory» for 60 s and then «little free memory — starting anyway» on
a host with 70 % of its memory free. The hold was the voice's loop-lag shed — a fixed one-minute clock — and the
only words the wait had were the memory ones. The class, as mechanism:
  · the wait names its reason: `waiting_room` only while `admits()` is false, `waiting_voice` for a shed (T590);
  · a shed names its source and ends when THAT source recovers; another source's hold stands (T591);
  · there is no deadline start, and the next worker is measured only once the previous one RUNS (T592/T593);
  · the floor is the larger of the ratio and the voice's absolute reserve (T593).

Disarms (each seen red): the reason fixed to `waiting_room`; `unshed` clearing every source; the admitted worker not
registered (no settle gate); the floor reduced to the ratio alone.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.workers import envelope

GB = 1024 ** 3
MB = 2 ** 20
POL = {"worker_nice": 10, "admit_free_ratio": 0.2, "pause_free_ratio": 0.1, "voice_reserve_mb": 0, "voice_lag_s": 0.5}


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(envelope, "_sheds", {})
    monkeypatch.setattr(envelope, "_admitted", {})
    monkeypatch.setattr(envelope, "policy", lambda: dict(POL))


def test_a_voice_shed_on_a_roomy_host_is_said_as_the_voice_never_as_memory(monkeypatch):
    monkeypatch.setattr(envelope, "measured", lambda: (4 * GB, int(0.7 * 4 * GB)))   # 70 % free: memory is fine
    envelope.shed(60, "voice_loop")
    said = []

    async def run():
        t = asyncio.ensure_future(envelope.wait_for_room(said.append, poll_s=0.01))
        await asyncio.sleep(0.05)
        assert not t.done(), "a shed did not hold the worker"
        envelope.unshed("voice_loop")
        return await asyncio.wait_for(t, 1.0)
    assert asyncio.run(run()) is True
    assert said == ["waiting_voice"], said
    assert "waiting_room" not in said, "the record named memory while admits() was true"


def test_the_voice_recovering_never_releases_the_watchdogs_hold(monkeypatch):
    monkeypatch.setattr(envelope, "measured", lambda: (4 * GB, int(0.7 * 4 * GB)))
    envelope.shed(60, "voice_loop")
    envelope.shed(60, "watchdog")
    envelope.unshed("voice_loop")
    assert envelope.shedding() and envelope.reason() == "waiting_voice", "the watchdog's hold went with the voice's"
    envelope.unshed("watchdog")
    assert not envelope.shedding() and envelope.reason() == ""


def test_the_loop_reading_back_under_the_bound_releases_only_the_loops_shed(monkeypatch):
    from voice import lag
    envelope.shed(60, "voice_audio")
    lag.note(1.0, lag.LOOP)
    assert set(envelope._sheds) == {"voice_audio", "voice_loop"}
    lag.note(0.0, lag.LOOP)
    assert set(envelope._sheds) == {"voice_audio"}, "the loop's recovery released another source"


def _host(state, roomy: bool):
    """Measured memory: room for exactly one worker on a tight host (under the floor once one runs)."""
    def measured():
        if roomy:
            return 4 * GB, int(0.9 * 4 * GB)
        return (4 * GB, int(0.5 * 4 * GB)) if state["running"] == 0 else (4 * GB, int(0.05 * 4 * GB))
    return measured


async def _three(state, said):
    async def job(i):
        rec = {"runs": False}
        await envelope.wait_for_room(lambda why: said.append((i, why)), key=str(i), runs=lambda: rec["runs"],
                                     poll_s=0.01)
        state["starts"].append(i)
        await asyncio.sleep(0.03)                 # the process takes a moment to come up: memory not yet measured
        state["running"] += 1
        rec["runs"] = True
        state["peak"] = max(state["peak"], state["running"])
        await asyncio.sleep(0.08)
        state["running"] -= 1
        envelope.released(str(i))
    await asyncio.wait_for(asyncio.gather(*(job(i) for i in range(3))), 5.0)


def test_three_jobs_on_a_tight_host_run_one_then_one_then_one(monkeypatch):
    state = {"running": 0, "peak": 0, "starts": []}
    monkeypatch.setattr(envelope, "measured", _host(state, roomy=False))
    said = []
    asyncio.run(_three(state, said))
    assert state["peak"] == 1, f"{state['peak']} workers ran at once on a host with room for one"
    assert sorted(state["starts"]) == [0, 1, 2], "a job never started (or started twice)"
    reasons = {why for _, why in said}
    assert reasons <= {"queued_behind", "waiting_room"}, reasons


def test_three_jobs_on_a_roomy_host_overlap(monkeypatch):
    state = {"running": 0, "peak": 0, "starts": []}
    monkeypatch.setattr(envelope, "measured", _host(state, roomy=True))
    said = []
    asyncio.run(_three(state, said))
    assert state["peak"] >= 2, "a roomy host serialised the work"
    assert all(why == "queued_behind" for _, why in said), said   # only the settle gate, never memory or voice


def test_the_floor_is_the_larger_of_the_ratio_and_the_voice_reserve():
    pol = {**POL, "voice_reserve_mb": 768}
    assert envelope.floor(2 * GB, pol) == 768 * MB                   # a small host: the reserve governs
    assert envelope.floor(16 * GB, pol) == 0.2 * 16 * GB              # a large one: the ratio governs
    assert not envelope.admits(2 * GB, 700 * MB, pol), "the ratio alone admitted under the voice's reserve"
    assert envelope.admits(2 * GB, 800 * MB, pol)


def test_the_reserve_is_declared_data():
    import json
    import os
    path = os.path.join(os.path.dirname(envelope._HERE), "config", "resources.default.json")
    declared = json.load(open(path, encoding="utf-8"))
    assert declared["voice_reserve_mb"] > 0 and "admit_wait_s" not in declared
    assert any("voice_reserve_mb" in line for line in declared["_doc"])


def test_the_waiting_row_says_the_reason_it_was_given(monkeypatch):
    """The row's words follow the envelope's reason: the voice as the voice even with work running, memory only for
    the floor, and the running work it queues behind when another worker holds the room."""
    from types import SimpleNamespace
    from nucleo.dispatch import session as ds
    from nucleo.workers import progress, reports
    phases = []
    monkeypatch.setattr(reports, "session_phase", lambda key, p: phases.append(p))
    monkeypatch.setattr(progress, "say", lambda key, default, **kw: key)
    for running in ([], [{"id": "9", "status": "running", "title": "the trip plan"}]):
        d = SimpleNamespace(active_sessions=lambda r=running: r, logger=SimpleNamespace(debug=print))
        for why in ("waiting_voice", "waiting_room", "queued_behind"):
            ds._say_held(d, "1", why)
    assert phases == ["waiting_voice", "waiting_room", "queued",
                      "waiting_voice", "queued_behind", "queued_behind"], phases

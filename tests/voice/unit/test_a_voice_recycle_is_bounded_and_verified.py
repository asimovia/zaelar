"""A LiveKit recycle is bounded and verified, and a dead voice never stays dead quietly (V2-871).

Measured on a hosted Machine: the heartbeat read the embedded worker as degraded and recycled it cold. The recycle
awaited the old server's `aclose()` with no bound; that close cancels the worker's LiveKit connection first and then
waits for the stuck job executor, so it never returned — no new server, the heartbeat parked in the await, and the
voice dead for the rest of the process while HTTP and the text path stayed green. Nothing retried or said so. The
degraded marks themselves fell inside the first session's warm-up, 2.5 min after boot.

Disarms (each seen red): await `old.aclose()` unbounded in `_close_bounded` → (a) hangs past its bound; drop the
`_verify` call (a recycle is «ok» once scheduled) → (b) never gives up; drop `since=` in `_tick` → (c) recycles from
the warm-up; drop `_in_boot_grace()` in `lag.note` → (d) sheds and speaks during the cold start.
"""
from __future__ import annotations

import asyncio
import time
import types

import pytest

from nucleo.pulse import homeostasis as H
from nucleo.pulse import self_watchdog, voice_recycle as VR

POL = {"recycle_close_s": 0.2, "recycle_verify_s": 0.3, "recycle_attempts": 3, "recycle_backoff_s": 0.01,
       "recycle_retry_s": 60.0, "voice_dead_s": 1.0, "boot_grace_s": 0.0}


class _Server:
    """The shape of `AgentServer` the recycle reads: `run`, `aclose`, `id`, `_closed`, `_connecting`."""

    def __init__(self, *, registers: bool = True, close_hangs: bool = False):
        self.id, self._closed, self._connecting = "unregistered", True, False
        self.registers, self.close_hangs, self.ran = registers, close_hangs, False

    async def run(self, devmode: bool = False) -> None:
        self.ran, self._closed = True, False
        if self.registers:
            await asyncio.sleep(0.01)
            self.id = "worker-1"
        await asyncio.Event().wait()

    async def aclose(self) -> None:
        if self.close_hangs:
            await asyncio.Event().wait()          # the job executor never lets go
        self._closed = True


def _app(server=None, task=None):
    return types.SimpleNamespace(state=types.SimpleNamespace(lk_server=server, lk_task=task))


@pytest.fixture
def seen(monkeypatch):
    from nucleo.pulse import notices
    from voice import observer
    got = {"events": [], "alerts": [], "notices": [], "exits": []}

    def emit(kind, label, text="", role="", extra=None, **_k):
        (got["alerts"] if kind == "alert" else got["events"]).append((extra or {}).get("kind_diag") or label)
    monkeypatch.setattr(observer, "emit", emit)

    async def notify(title, text, **k):
        got["notices"].append(text)
    monkeypatch.setattr(notices, "notify", notify)
    monkeypatch.setattr(VR, "policy", lambda: dict(POL))
    monkeypatch.setattr(VR, "grace_end", lambda: 0.0)            # past the cold start
    monkeypatch.setattr(VR, "_state", {"requested": 0.0, "gave_up": False, "told": False, "retry_at": 0.0})
    monkeypatch.setattr(self_watchdog, "_exit", lambda pol: got["exits"].append(pol))
    monkeypatch.setitem(self_watchdog._state, "exiting", False)
    return got


def test_a_close_that_never_returns_is_abandoned_and_the_new_server_runs(seen):
    async def go():
        old = _Server(close_hangs=True)
        old_task = asyncio.create_task(old.run())
        await asyncio.sleep(0.05)
        app = _app(old, old_task)
        t0 = time.monotonic()
        ok = await asyncio.wait_for(VR.recycle(app, _Server, devmode=True), timeout=3)
        took = time.monotonic() - t0
        await asyncio.sleep(0)
        return ok, took, app, old_task, old, VR.worker_alive(app.state.lk_server, app.state.lk_task)
    ok, took, app, old_task, old, alive = asyncio.run(go())
    assert ok and took < POL["recycle_close_s"] + POL["recycle_verify_s"] + 0.5, took
    assert app.state.lk_server is not old and app.state.lk_server.ran and alive, "the new server runs, registered"
    assert old_task.cancelled(), "the abandoned server's run task is cancelled, never left holding the worker"
    assert seen["events"][:2] == ["recycle_start", "recycle_ok"], seen["events"]


def test_a_recycle_that_never_registers_gives_up_says_so_and_restarts_under_a_supervisor(seen, monkeypatch):
    monkeypatch.setenv("ZAELAR_SUPERVISED", "1")

    async def go():
        app = _app()
        ok = await VR.recycle(app, lambda: _Server(registers=False), devmode=True)
        what = await VR.check_dead(app, lambda a: None)
        return ok, what
    ok, what = asyncio.run(go())
    assert ok is False
    assert seen["events"].count("recycle_failed") == POL["recycle_attempts"] and seen["events"][-1] == "recycle_gave_up"
    assert what == "exit" and len(seen["exits"]) == 1 and seen["alerts"] == ["voice_dead_exit", "self_watchdog"]


def test_unsupervised_a_dead_voice_is_said_once_and_retried_on_its_clock(seen, monkeypatch):
    monkeypatch.delenv("ZAELAR_SUPERVISED", raising=False)
    tries = []

    async def again(app):
        tries.append(1)

    async def go():
        app = _app()
        VR.note_session_requested(now=1000.0)
        out = [await VR.check_dead(app, again, now=1000.5)]          # asked for, not yet `voice_dead_s`
        out.append(await VR.check_dead(app, again, now=1002.0))
        out.append(await VR.check_dead(app, again, now=1003.0))      # within `recycle_retry_s`
        out.append(await VR.check_dead(app, again, now=1063.0))
        await asyncio.sleep(0)
        return out
    out = asyncio.run(go())
    assert out == ["ok", "retry", "wait", "retry"] and len(tries) == 2 and not seen["exits"]
    assert seen["alerts"] == ["voice_dead"] and len(seen["notices"]) == 1, (seen["alerts"], seen["notices"])


@pytest.mark.parametrize("after_grace,recycles", [(False, 0), (True, 1)])
def test_degraded_marks_inside_the_cold_start_are_the_warm_up(monkeypatch, after_grace, recycles):
    now = time.time()
    grace_end = now - 100 if after_grace else now + 100
    ran = []

    async def recycle(app):
        ran.append(1)
        return True

    async def no_dead(app, fn, now):
        return "ok"
    monkeypatch.setattr(VR, "grace_end", lambda: grace_end)
    monkeypatch.setattr(VR, "check_dead", no_dead)
    monkeypatch.setattr(H, "_recycle_livekit", recycle)
    monkeypatch.setattr(H, "_marks", [now - 30, now - 20, now - 10])
    monkeypatch.setattr(H, "_last_recycle", 0.0)
    monkeypatch.setattr(H, "_recycle_requested", "")
    monkeypatch.setattr(H, "_voice_on", lambda: False)
    monkeypatch.setattr(H, "_recent_activity_ts", lambda: 0.0)
    from memory import api as memory
    monkeypatch.setattr(memory, "kv_keys", lambda prefix: [])
    monkeypatch.setattr(H, "_emit", lambda *a, **k: None)
    asyncio.run(H._tick(_app(object())))
    assert len(ran) == recycles


@pytest.mark.parametrize("after_grace", [False, True])
def test_the_audio_lag_inside_the_cold_start_neither_sheds_nor_speaks(monkeypatch, after_grace):
    from nucleo.workers import envelope
    from voice import lag, observer, proactive
    got = {"shed": [], "events": []}
    monkeypatch.setattr(envelope, "policy", lambda: {**envelope._DEFAULTS, "voice_lag_s": 0.2})
    monkeypatch.setattr(envelope, "shed", lambda s, source: got["shed"].append(source))
    monkeypatch.setattr(envelope, "unshed", lambda source: None)
    monkeypatch.setattr(observer, "emit", lambda kind, label, **k: got["events"].append(label))
    monkeypatch.setattr(lag, "_audio_flows", lambda: True)
    monkeypatch.setattr(proactive, "user_speaking", lambda: False)
    monkeypatch.setitem(lag._state, "last_act", -1e9)
    monkeypatch.setitem(lag._state, "episode", False)
    monkeypatch.setattr(VR, "grace_end", lambda: time.time() + (-100 if after_grace else 100))
    acted = lag.note(1.2, "vad.py")
    assert acted is after_grace and bool(got["shed"]) is after_grace and bool(got["events"]) is after_grace

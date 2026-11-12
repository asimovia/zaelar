"""A dead voice is recycled `voice_dead_s` after the FIRST ask it left unanswered, however often it is asked (node 3.198).

Measured on a local engine: the LiveKit worker lost its server, gave up after 16 reconnects, and stayed dead for
3 h 40 min. A desktop page asked for a room every ~150 ms; the token door answered 503 `voice_starting` each time and
each answer re-stamped `note_session_requested` — so `check_dead` always read an ask a fraction of a second old and
never reached `voice_dead_s`: the guard that exists to recycle that worker was held off by the very person trying to
talk to it. Now the clock starts at the first ask the worker has not been seen alive since, and an ask made while
the worker is alive does not arm it.
"""
from __future__ import annotations

import asyncio
import types

import pytest

from nucleo.pulse import self_watchdog, voice_recycle as VR

POL = {"recycle_close_s": 0.2, "recycle_verify_s": 0.3, "recycle_attempts": 3, "recycle_backoff_s": 0.01,
       "recycle_retry_s": 60.0, "voice_dead_s": 120.0, "boot_grace_s": 0.0}


class _Registered:
    id, _closed, _connecting = "worker-1", False, False


class _Running:
    def done(self):
        return False


def _app(alive: bool):
    st = types.SimpleNamespace(lk_server=_Registered() if alive else None, lk_task=_Running() if alive else None)
    return types.SimpleNamespace(state=st)


@pytest.fixture
def recycles(monkeypatch):
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: None)
    monkeypatch.setattr(VR, "_tell", lambda supervised: None)
    monkeypatch.setattr(VR, "policy", lambda: dict(POL))
    monkeypatch.setattr(VR, "grace_end", lambda: 0.0)
    monkeypatch.setattr(VR, "_state", {"requested": 0.0, "alive_at": 0.0, "gave_up": False, "told": False,
                                       "retry_at": 0.0})
    monkeypatch.delenv("ZAELAR_SUPERVISED", raising=False)
    monkeypatch.setitem(self_watchdog._state, "exiting", False)
    done = []

    async def again(app):
        done.append(app)
    return done, again


def test_a_page_that_keeps_asking_does_not_hold_the_recycle_off(recycles):
    done, again = recycles
    dead = _app(False)

    async def go():
        t, out = 1000.0, []
        while t < 1000.0 + POL["voice_dead_s"] + 30:     # an ask every 150 ms, a heartbeat every 10 s
            VR.note_session_requested(now=t)
            if int(t * 100) % 1000 == 0:
                out.append(await VR.check_dead(dead, again, now=t))
            t = round(t + 0.15, 2)
        return out
    out = asyncio.run(go())
    assert "retry" in out and done, f"a voice asked for every 150 ms for {POL['voice_dead_s'] + 30:g}s was never recycled"
    assert out[0] == "ok", "the first heartbeat after the first ask is not yet a dead voice"


def test_the_clock_starts_again_after_the_worker_was_seen_alive(recycles):
    done, again = recycles

    async def go():
        VR.note_session_requested(now=1000.0)
        assert await VR.check_dead(_app(True), again, now=1001.0) == "ok"      # served: the ask is answered
        VR.note_session_requested(now=5000.0)                                   # the worker dies later; a new ask
        early = await VR.check_dead(_app(False), again, now=5010.0)
        late = await VR.check_dead(_app(False), again, now=5000.0 + POL["voice_dead_s"])
        return early, late
    early, late = asyncio.run(go())
    assert early == "ok", "a fresh ask after a live reading is the start of the clock, not an old debt"
    assert late == "retry" and len(done) == 1

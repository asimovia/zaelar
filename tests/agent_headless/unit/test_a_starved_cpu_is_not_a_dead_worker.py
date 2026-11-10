"""A starved CPU is not a dead worker, and no recycle cuts a live or fresh session (V2-872 W2).

Measured on a small shared-CPU host: the boot burned the CPU quota and the host was throttled (`/proc/stat` after 17 min:
user+sys 152 s, steal 654 s); the voice stack's own marks («job executor is unresponsive» ×8) read as a degraded
engine, and the heartbeat recycled the LiveKit worker 11 s after a session started — the greeting never sounded.
Its two guards read wrong: `_voice_on()` read `STATE["voice"]`, the INDEX of the chosen voice (0 → «off»), and the
idle window read only the timeline's mtime.

Disarms (each seen red, restored in a `finally`): `_voice_on` back to `STATE["voice"]` → (a); drop the
`session_grace_s` check in `safe_to_recycle` → (b); `starved()` blind to the steal share → (c); drop the episode's
`open` check in `starvation.report` → (d); never take the starved branch in `_tick` → (e).
"""
from __future__ import annotations

import asyncio
import time
import types

import pytest

from nucleo.pulse import homeostasis as H
from nucleo.pulse import starvation as S
from nucleo.pulse import voice_recycle as VR

UNKNOWN = {"steal_pct": None, "throttled_ms": None, "nr_throttled": None}


def _app():
    return types.SimpleNamespace(state=types.SimpleNamespace(lk_server=object(), lk_task=None))


@pytest.fixture
def beat(monkeypatch):
    """A heartbeat past the cold start, with degraded marks, a recorder for recycles, events and notices."""
    from memory import api as memory
    from nucleo.pulse import notices
    from nucleo.workers import envelope
    from server import active
    got = {"recycles": 0, "events": [], "notices": [], "win": dict(UNKNOWN)}

    async def recycle(app):
        got["recycles"] += 1
        return True

    async def no_dead(app, fn, now):
        return "ok"

    async def notify(title, text, **k):
        got["notices"].append(text)

    now = time.time()
    monkeypatch.setattr(VR, "grace_end", lambda: now - 1000)
    monkeypatch.setattr(VR, "check_dead", no_dead)
    monkeypatch.setattr(H, "_recycle_livekit", recycle)
    monkeypatch.setattr(H, "_marks", [now - 30, now - 20, now - 10])
    monkeypatch.setattr(H, "_last_recycle", 0.0)
    monkeypatch.setattr(H, "_recycle_requested", "")
    monkeypatch.setattr(H, "_recent_activity_ts", lambda: 0.0)
    monkeypatch.setattr(H, "_emit", lambda label, text="", extra=None: got["events"].append((label, extra or {})))
    monkeypatch.setattr(H, "_alert", lambda *a, **k: asyncio.sleep(0))
    monkeypatch.setitem(S._state, "open", False)
    monkeypatch.setattr(S, "tick", lambda read=None: dict(got["win"]))
    monkeypatch.setattr(envelope, "policy", lambda: {**envelope._DEFAULTS, "steal_pct_starved": 20,
                                                     "session_grace_s": 180})
    monkeypatch.setattr(notices, "notify", notify)
    monkeypatch.setattr(memory, "kv_keys", lambda prefix: [])
    monkeypatch.setattr(active, "_shutdowns", [])
    monkeypatch.setattr(active, "_last_registered_at", 0.0)
    return got


# ── (a) liveness, not a voice index ─────────────────────────────────────────────────────────────────────────────
def test_a_live_session_with_voice_index_zero_is_not_recycled(beat, monkeypatch):
    from server import active
    from server import state as St
    monkeypatch.setitem(St.STATE, "voice", 0)              # the first voice of the list: index 0
    asyncio.run(H._tick(_app()))
    assert beat["recycles"] == 1                           # control: no session, idle, degraded → recycled
    monkeypatch.setattr(H, "_marks", [time.time() - 5] * 3)
    monkeypatch.setattr(H, "_last_recycle", 0.0)
    monkeypatch.setattr(active, "_last_registered_at", time.time() - 3600)   # an old session, past the grace
    active._shutdowns.append(lambda reason="": asyncio.sleep(0))
    assert H._voice_on() is True
    asyncio.run(H._tick(_app()))
    assert beat["recycles"] == 1, "a live run_bot session was recycled because the voice INDEX was 0"


# ── (b) never over a fresh session ──────────────────────────────────────────────────────────────────────────────
def test_a_session_started_inside_the_grace_is_never_recycled():
    now = 10_000.0
    assert not H.safe_to_recycle(False, now - 999, now, session_started=now - 11, session_grace_s=180)
    assert H.safe_to_recycle(False, now - 999, now, session_started=now - 181, session_grace_s=180)
    assert H.safe_to_recycle(False, now - 999, now)        # no session ever: the idle window alone decides


def test_register_stamps_the_session_start(monkeypatch):
    from server import active
    monkeypatch.setattr(active, "_shutdowns", [])
    monkeypatch.setattr(active, "_last_registered_at", 0.0)
    t0 = time.time()
    active.register(lambda reason="": asyncio.sleep(0))
    assert active.last_registered_at() >= t0 and active.count() == 1


# ── (c) the classification from sampled numbers (pure) ──────────────────────────────────────────────────────────
def test_the_starvation_classification_reads_steal_and_throttling():
    # the measured host: 152 s busy, 654 s steal, a little idle (ticks at 100 Hz)
    prev = {"cpu": {"busy": 0, "idle": 0, "steal": 0}, "cg": None}
    host = {"cpu": {"busy": 15200, "idle": 2000, "steal": 65400}, "cg": None}
    win = S.window(prev, host)
    assert win["steal_pct"] > 70 and S.starved(win, 20) is True
    laptop = {"cpu": {"busy": 5000, "idle": 95000, "steal": 0}, "cg": None}
    assert S.starved(S.window(prev, laptop), 20) is False
    throttled = S.window({"cpu": None, "cg": {"nr_throttled": 4, "throttled_usec": 1_000}},
                         {"cpu": None, "cg": {"nr_throttled": 9, "throttled_usec": 801_000}})
    assert throttled["throttled_ms"] == 800 and S.starved(throttled, 20) is True
    assert S.starved(S.window(None, host), 20) is None     # one sample is no window
    assert S.starved(UNKNOWN, 20) is None                  # macOS: the host says nothing


def test_the_proc_and_cgroup_files_are_read(tmp_path):
    stat = tmp_path / "stat"
    stat.write_text("cpu  100 5 50 1000 20 3 2 400 0 0\ncpu0 1 2 3 4 5 6 7 8 0 0\n")
    assert S.read_proc_stat(str(stat)) == {"busy": 160, "idle": 1020, "steal": 400}
    cg = tmp_path / "cpu.stat"
    cg.write_text("usage_usec 9\nnr_periods 3\nnr_throttled 2\nthrottled_usec 1500\n")
    assert S.read_cgroup(str(cg)) == {"nr_throttled": 2, "throttled_usec": 1500}
    assert S.read_proc_stat(str(tmp_path / "absent")) is None and S.read_cgroup(str(tmp_path / "absent")) is None


# ── (d) one notice per episode · (e) no recycle while starved ───────────────────────────────────────────────────
def test_a_starved_window_never_recycles_and_says_so(beat):
    beat["win"] = {"steal_pct": 81.0, "throttled_ms": None, "nr_throttled": None}
    asyncio.run(H._tick(_app()))
    assert beat["recycles"] == 0, "the heartbeat recycled the worker over a starved CPU"
    assert H._marks == []                                  # the window's marks were the host's
    starved = [x for label, x in beat["events"] if label == "starved"]
    assert starved and starved[0]["steal_pct"] == 81.0 and starved[0]["marks"] == 3


def test_the_notice_is_given_once_per_episode(beat, monkeypatch):
    from i18n import langs
    starved = {"steal_pct": 64.0, "throttled_ms": 0, "nr_throttled": 0}
    for _ in range(3):
        beat["win"] = dict(starved)
        monkeypatch.setattr(H, "_marks", [time.time() - 5] * 3)
        asyncio.run(H._tick(_app()))
    assert len(beat["notices"]) == 1, beat["notices"]
    assert beat["notices"][0] == langs.words("alerts.cpu_starved")
    beat["win"] = {"steal_pct": 2.0, "throttled_ms": 0, "nr_throttled": 0}      # a window under: the episode closes
    monkeypatch.setattr(H, "_marks", [])
    asyncio.run(H._tick(_app()))
    beat["win"] = dict(starved)
    monkeypatch.setattr(H, "_marks", [time.time() - 5] * 3)
    asyncio.run(H._tick(_app()))
    assert len(beat["notices"]) == 2 and beat["recycles"] == 0


def test_an_unknown_host_changes_nothing(beat):
    asyncio.run(H._tick(_app()))                           # macOS: no steal, no cgroup → the V2-871 path as before
    assert beat["recycles"] == 1 and not [1 for label, _ in beat["events"] if label == "starved"]

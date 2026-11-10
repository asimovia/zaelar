"""An engine nobody is using ends its own process, and every stop ends within a bounded time.

Two mechanisms, one promise — the process exits on its own, with status 0, instead of being killed:
  * `nucleo/idle_stop.py`: with `ZAELAR_IDLE_STOP_MIN` set, no real activity, no worker and no notice due soon
    → the server is asked to shut down gracefully (never a signal to itself);
  * `server/lifespan.py`: each shutdown step has a timeout and the whole shutdown a hard deadline.
"""
from __future__ import annotations

import asyncio
import importlib
import time

import pytest

from nucleo import idle_stop, suspend

MIN = 60_000
NOW = 1_800_000_000_000


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    suspend._reset_for_tests()
    monkeypatch.delenv("ZAELAR_IDLE_STOP_MIN", raising=False)
    yield
    suspend._reset_for_tests()


def test_quiet_for_the_whole_window_with_nothing_pending_is_a_stop():
    why = idle_stop.decide(NOW, NOW - 16 * MIN, NOW - 60 * MIN, False, None, 15 * MIN)
    assert why and "16 min" in why


@pytest.mark.parametrize("last, started, workers, next_due, window", [
    (NOW - 14 * MIN, NOW - 60 * MIN, False, None, 15 * MIN),      # real activity inside the window
    (None, NOW - 3 * MIN, False, None, 15 * MIN),                 # the process itself is younger than the window
    (NOW - 60 * MIN, NOW - 90 * MIN, True, None, 15 * MIN),       # a Brain Worker is running
    (NOW - 60 * MIN, NOW - 90 * MIN, False, (NOW + 10 * MIN) / 1000, 15 * MIN),   # a notice is due soon
    (NOW - 60 * MIN, NOW - 90 * MIN, False, None, 0),             # off (self-host default)
])
def test_anything_still_owed_keeps_the_engine_up(last, started, workers, next_due, window):
    assert idle_stop.decide(NOW, last, started, workers, next_due, window) is None


def test_a_notice_far_away_does_not_hold_the_engine():
    assert idle_stop.decide(NOW, None, NOW - 60 * MIN, False, (NOW + 3 * 60 * MIN) / 1000, 15 * MIN)


def test_an_unreadable_worker_registry_counts_as_busy(monkeypatch):
    import sys
    import types
    broken = types.ModuleType("nucleo.dispatch.registry")

    def _boom():
        raise RuntimeError("unreadable")
    broken.has_active = _boom
    monkeypatch.setitem(sys.modules, "nucleo.dispatch.registry", broken)
    import nucleo.dispatch as dispatch_pkg
    monkeypatch.setattr(dispatch_pkg, "registry", broken, raising=False)
    _last, workers, _next = idle_stop._readings(time.time())
    assert workers is True


def test_a_shutdown_step_that_hangs_is_cut_and_the_next_one_still_runs(monkeypatch):
    lifespan = importlib.import_module("server.lifespan")
    monkeypatch.setattr(lifespan, "STEP_TIMEOUT_S", 0.2)
    ran = []

    async def _hangs():
        await asyncio.sleep(30)

    async def _main():
        t0 = time.monotonic()
        await lifespan._stop("hangs", lambda: _hangs())
        await lifespan._stop("next", lambda: ran.append("next"))
        return time.monotonic() - t0
    assert asyncio.run(_main()) < 2
    assert ran == ["next"]


def test_the_shutdown_deadline_exits_the_process_with_status_zero(monkeypatch):
    lifespan = importlib.import_module("server.lifespan")
    codes = []
    monkeypatch.setattr(lifespan.os, "_exit", lambda code: codes.append(code))
    t = lifespan._arm_deadline(0.1)
    t.join(2)
    assert codes == [0]
    assert lifespan._arm_deadline(0) is None


# ── V2-872 · presence is the person, never the tab ─────────────────────────────────────────────────────────────
# The loop this closes: an open tab's stream reconnects after every stop, that request starts the engine again,
# and the engine waits the full window again with nobody there.

GRACE = 3 * MIN


def test_woken_with_nobody_present_it_stops_after_the_short_grace():
    why = idle_stop.decide(NOW, None, NOW - 4 * MIN, False, None, 15 * MIN, last_presence_ms=None, grace_ms=GRACE)
    assert why and "nobody present" in why


def test_the_grace_is_counted_from_the_boot_and_not_before_it_ends():
    assert idle_stop.decide(NOW, None, NOW - 2 * MIN, False, None, 15 * MIN, grace_ms=GRACE) is None


def test_activity_that_is_not_a_person_does_not_stretch_the_grace():
    """A boot's own events and a reconnecting tab move the activity clock with nobody there; the grace ignores it."""
    why = idle_stop.decide(NOW, NOW - 10_000, NOW - 4 * MIN, False, None, 15 * MIN, last_presence_ms=None, grace_ms=GRACE)
    assert why and "nobody present" in why


def test_after_his_first_input_the_full_window_applies():
    started = NOW - 30 * MIN
    assert idle_stop.decide(NOW, None, started, False, None, 15 * MIN,
                            last_presence_ms=NOW - 4 * MIN, grace_ms=GRACE) is None
    why = idle_stop.decide(NOW, None, started, False, None, 15 * MIN, last_presence_ms=NOW - 16 * MIN, grace_ms=GRACE)
    assert why and "nobody present for 16 min" in why


@pytest.mark.parametrize("workers, next_due", [
    (True, None),                                  # a worker (email triage, messaging) keeps its veto in the grace
    (False, (NOW + 10 * MIN) / 1000),              # …and so does a notice due within the full window
])
def test_workers_and_due_notices_keep_their_veto_inside_the_grace(workers, next_due):
    assert idle_stop.decide(NOW, None, NOW - 10 * MIN, workers, next_due, 15 * MIN, grace_ms=GRACE) is None


def test_the_two_windows_are_declared_in_the_resources_policy(monkeypatch):
    from nucleo.workers import envelope
    pol = envelope.policy()
    assert pol["wake_grace_min"] == 1 and pol["tab_sleep_min"] == 10
    monkeypatch.setenv("ZAELAR_IDLE_STOP_MIN", "15")
    assert idle_stop.wake_grace_min() == 1 and idle_stop.tab_sleep_min() == 10
    monkeypatch.setenv("ZAELAR_WAKE_GRACE_MIN", "2.5")
    assert idle_stop.wake_grace_min() == 2.5, "one deployment may set its own grace"
    monkeypatch.setenv("ZAELAR_WAKE_GRACE_MIN", "soon")
    assert idle_stop.wake_grace_min() == 1, "a value that is not a number keeps the policy's"


def test_an_engine_that_never_stops_never_puts_a_tab_to_sleep(monkeypatch):
    """Self-host (no idle stop): the hello says 0 — an open stream costs nothing there and a wall display is read
    without being touched. The policy's 10 is for a host that stops when idle."""
    monkeypatch.delenv("ZAELAR_IDLE_STOP_MIN", raising=False)
    assert idle_stop.tab_sleep_min() == 0.0
    monkeypatch.setenv("ZAELAR_IDLE_STOP_MIN", "15")
    assert idle_stop.tab_sleep_min() == 10


def test_a_stream_a_beat_or_visibility_is_not_presence_and_his_input_is():
    from voice import screens
    screens._reset_for_tests()
    try:
        screens.attach("desktop:abc")
        screens.beat("desktop:abc", visible=True)
        screens.beat("desktop:abc", visible=False)
        screens.detach("desktop:abc")
        assert screens.last_input_ms() is None, "a stream open, a beat or a visibility change counted as a person"
        screens.touched("desktop:abc")
        assert screens.last_input_ms() is not None, "a touch on a screen is his input"
        screens._reset_for_tests()
        screens.stamp({"kind": "transcript", "role": "user", "text": "hola", "dev": ""})
        assert screens.last_input_ms() is not None, "his spoken turn is his input, with or without a screen named"
    finally:
        screens._reset_for_tests()


def test_maybe_stop_reads_screen_input_as_presence(monkeypatch):
    from voice import screens
    screens._reset_for_tests()
    monkeypatch.setenv("ZAELAR_IDLE_STOP_MIN", "15")
    monkeypatch.setattr(idle_stop, "_readings", lambda now: (None, False, None))
    exits = []
    suspend.request_exit(lambda: exits.append(1))
    now = time.time()
    monkeypatch.setattr(idle_stop, "_STARTED_MS", round((now - 5 * 60) * 1000))
    try:
        screens.attach("mobile:x1")                          # a tab reconnected: not a person
        assert idle_stop.maybe_stop(now) is True and exits == [1]
        suspend._reset_for_tests()
        suspend.request_exit(lambda: exits.append(2))
        screens.touched("mobile:x1")                         # he touched it: the full window holds
        assert idle_stop.maybe_stop(time.time()) is False and exits == [1]
    finally:
        screens._reset_for_tests()


def _armed(monkeypatch, record):
    monkeypatch.setenv("ZAELAR_IDLE_STOP_MIN", "1")
    monkeypatch.setattr(idle_stop, "_readings", lambda now: (None, False, None))
    monkeypatch.setattr(idle_stop, "_last_presence", lambda: None)
    monkeypatch.setattr(idle_stop, "_STARTED_MS", round((time.time() - 3600) * 1000))
    import voice.observer as observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: record.append(f"{kind}:{label}"))
    suspend.request_exit(lambda: record.append("exit"))


def test_the_engine_says_goodnight_before_it_exits(monkeypatch):
    record = []
    _armed(monkeypatch, record)
    assert idle_stop.maybe_stop() is True
    assert record == ["session:engine.sleep", "exit"], record


def test_on_the_server_loop_the_exit_waits_one_beat_for_the_goodnight(monkeypatch):
    record = []
    _armed(monkeypatch, record)
    monkeypatch.setattr(suspend, "SLEEP_FLUSH_S", 0.2)

    async def _main():
        assert idle_stop.maybe_stop() is True
        await asyncio.sleep(0.05)                     # the stop runs as a task: the report first, then the goodnight
        before = list(record)
        await asyncio.sleep(0.5)
        return before
    before = asyncio.run(_main())
    assert before == ["session:engine.sleep"], "the exit did not wait for the goodnight to be flushed"
    assert record == ["session:engine.sleep", "exit"]

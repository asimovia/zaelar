"""An idle engine asks its host to SUSPEND it, falls back to the clean exit when it cannot, and knows it has resumed.

The stop decided by `nucleo/idle_stop.py` (node 2.830) used to end the process; a deployment that can suspend its
host resumes it in well under a second instead of a cold boot. These tests hold the mechanism around that:
  * the wake report goes out BEFORE the goodnight, and a failed report keeps the engine up;
  * the sleep endpoint's answers: 202 waits to be suspended (and exits if nothing happens), 200 is already a resume,
    anything else or no answer is the clean exit — and a suspend followed by a resume is never read as a failure;
  * the pulse finds a resume from the clocks and starts the idle state over;
  * presence is a connected, visible screen — not only input;
  * a widget's background tick is not activity, and a job the engine could not fire does not hold it up.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from nucleo import idle_stop

MIN = 60_000


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    idle_stop._reset_for_tests()
    for k in ("ZAELAR_IDLE_STOP_MIN", "ZAELAR_SLEEP_URL", "ZAELAR_WAKE_URL", "CONTROL_PLANE_URL",
              "CONTROL_PLANE_SERVICE_TOKEN", "ZAELAR_WAKE_GRACE_MIN"):
        monkeypatch.delenv(k, raising=False)
    yield
    idle_stop._reset_for_tests()


def _arm(monkeypatch, record, *, status=202, flushed=True, post=None):
    """An engine due to stop now, with a sleep endpoint whose answer is `status` (or what `post` does)."""
    monkeypatch.setenv("ZAELAR_IDLE_STOP_MIN", "1")
    monkeypatch.setenv("ZAELAR_SLEEP_URL", "http://deployment.invalid/sleep")
    monkeypatch.setattr(idle_stop, "_readings", lambda now: (None, False, None))
    monkeypatch.setattr(idle_stop, "_last_presence", lambda: None)
    monkeypatch.setattr(idle_stop, "_STARTED_MS", round((time.time() - 3600) * 1000))
    monkeypatch.setattr(idle_stop, "SLEEP_FLUSH_S", 0.01)
    import voice.observer as observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: record.append(f"{kind}:{label}"))

    async def _flush():
        record.append("report")
        return flushed

    async def _post(endpoint, token):
        record.append("sleep")
        return await post() if post else status
    monkeypatch.setattr(idle_stop, "_flush_wake", _flush)
    monkeypatch.setattr(idle_stop, "_post_sleep", _post)
    idle_stop.request_exit(lambda: record.append("exit"))


async def _stop_now():
    assert idle_stop.maybe_stop() is True
    await asyncio.sleep(0.1)


# ── the sleep sequence ─────────────────────────────────────────────────────────────────────────────────────────

def test_the_report_goes_out_before_the_goodnight_and_the_sleep_request(monkeypatch):
    record = []
    _arm(monkeypatch, record)
    asyncio.run(_stop_now())
    assert record == ["report", "session:engine.sleep", "sleep"], record


def test_a_failed_wake_report_keeps_the_engine_up_and_tries_later(monkeypatch):
    """A stop with a stale report sleeps through the next notice: no goodnight, no sleep, no exit."""
    record = []
    _arm(monkeypatch, record, flushed=False)
    asyncio.run(_stop_now())
    assert record == ["report"], record
    assert idle_stop._state["requested"] is False
    assert idle_stop.maybe_stop() is False, "the stop is retried after WAKE_RETRY_S, not on the next beat"


def test_a_refused_sleep_is_the_clean_exit_on_the_next_beat(monkeypatch):
    record = []
    _arm(monkeypatch, record, status=409)
    asyncio.run(_stop_now())
    assert "exit" not in record, "the exit is decided on the pulse, after it looked for a resume"
    idle_stop.note_tick(time.time(), time.monotonic(), 1.0)
    assert idle_stop.maybe_stop() is True and record[-1] == "exit"


def test_no_sleep_endpoint_is_the_clean_exit(monkeypatch):
    record = []
    _arm(monkeypatch, record)
    monkeypatch.delenv("ZAELAR_SLEEP_URL")
    asyncio.run(_stop_now())
    assert record == ["report", "session:engine.sleep", "exit"], record


def test_an_accepted_sleep_that_never_comes_falls_back_to_the_exit(monkeypatch):
    record = []
    _arm(monkeypatch, record, status=202)
    asyncio.run(_stop_now())
    assert idle_stop._state["sleep"] is not None
    assert idle_stop.maybe_stop() is False and "exit" not in record, "inside SLEEP_CONFIRM_S it waits"
    idle_stop._state["sleep"]["deadline"] = time.monotonic() - 1      # SLEEP_CONFIRM_S went by, still running
    idle_stop.note_tick(time.time(), time.monotonic(), 1.0)
    idle_stop.note_tick(time.time() + 1, time.monotonic() + 1, 1.0)
    assert idle_stop.maybe_stop() is True and record[-1] == "exit"


@pytest.mark.parametrize("wall_gap, mono_gap", [
    (600.0, 1.0),       # the guest's monotonic clock stood still while the host was frozen
    (600.0, 600.0),     # …or the host counted the frozen time on both clocks
])
def test_an_accepted_sleep_followed_by_a_resume_never_exits(monkeypatch, wall_gap, mono_gap):
    record = []
    _arm(monkeypatch, record, status=202)
    asyncio.run(_stop_now())
    w, m = time.time(), time.monotonic()
    idle_stop.note_tick(w, m, 1.0)
    idle_stop._state["sleep"]["deadline"] = m - 1                    # the deadline is gone on the monotonic clock too
    assert idle_stop.note_tick(w + wall_gap, m + mono_gap, 1.0) is True, "the resume was not seen"
    assert idle_stop.maybe_stop() is False and "exit" not in record, "a resumed engine exited"
    assert "session:engine.resumed" in record
    assert idle_stop._state["requested"] is False and idle_stop._state["sleep"] is None


def test_an_unanswered_sleep_across_a_resume_is_not_a_refusal(monkeypatch):
    """The host froze mid-request: the answer is lost (None). The pulse saw the resume meanwhile, so nothing exits."""
    record = []

    async def _frozen_then_lost():
        w, m = time.time(), time.monotonic()
        idle_stop.note_tick(w, m, 1.0)
        idle_stop.note_tick(w + 900, m + 0.5, 1.0)                  # the beat after the resume
        return None
    _arm(monkeypatch, record, post=_frozen_then_lost)
    asyncio.run(_stop_now())
    assert idle_stop._state["exit_pending"] is False
    assert idle_stop.maybe_stop() is False and "exit" not in record


def test_a_200_is_a_sleep_that_already_happened(monkeypatch):
    record = []
    _arm(monkeypatch, record, status=200)
    asyncio.run(_stop_now())
    assert "exit" not in record and "session:engine.resumed" in record
    assert idle_stop._state["requested"] is False


def test_the_sleep_endpoint_mirrors_the_wake_one(monkeypatch):
    assert idle_stop.sleep_url() == ("", "")
    monkeypatch.setenv("CONTROL_PLANE_URL", "https://cp.invalid/")
    assert idle_stop.sleep_url() == ("", ""), "no token: nowhere to ask"
    monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", "t0k")
    assert idle_stop.sleep_url() == ("https://cp.invalid/sleep", "t0k")
    monkeypatch.setenv("ZAELAR_SLEEP_URL", "http://elsewhere.invalid/s")
    assert idle_stop.sleep_url() == ("http://elsewhere.invalid/s", "t0k")


def test_the_report_before_a_stop_skips_the_debounce(monkeypatch):
    from nucleo.pulse import scheduler, wake
    wake._reset_for_tests()
    monkeypatch.setenv("ZAELAR_WAKE_URL", "http://deployment.invalid/wake")
    monkeypatch.setattr(scheduler, "next_due", lambda: 1_900_000_000.0)
    sent = []

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            sent.append(json)
            return type("R", (), {"status_code": 204})()
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    try:
        now = time.time()
        wake._state["last"] = now                                    # a report went out a moment ago
        assert asyncio.run(wake.flush(now)) is False and wake.pending(), "the debounce holds an ordinary flush"
        assert asyncio.run(wake.flush(now, force=True)) is True and not wake.pending()
        assert sent == [{"next_due": 1_900_000_000}]
    finally:
        wake._reset_for_tests()


# ── resume ─────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("wall, mono, sleeping, resumed", [
    (1.0, 1.0, False, False),
    (40.0, 40.0, False, False),       # a slow beat (a consolidation) is not a resume
    (40.0, 40.0, True, True),         # …after a sleep was asked for, it is
    (300.0, 1.0, False, True),        # the wall clock jumped, the monotonic one did not: a frozen guest
    (1.0, 300.0, False, True),        # the monotonic clock ran, the wall clock not corrected yet
    (8.0, 1.0, False, False),         # under the skew
])
def test_a_resume_is_read_from_the_clocks(wall, mono, sleeping, resumed):
    assert idle_stop.resumed_between(wall, mono, 1.0, sleeping=sleeping) is resumed


def test_a_resume_starts_the_idle_state_over(monkeypatch):
    monkeypatch.setenv("ZAELAR_IDLE_STOP_MIN", "15")
    from nucleo.pulse import wake
    wake._reset_for_tests()
    wake._state["dirty"] = False
    record = []
    import voice.observer as observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: record.append(f"{kind}:{label}"))
    w, m = time.time(), time.monotonic()
    idle_stop._state["requested"] = True
    assert idle_stop.note_tick(w, m, 1.0) is False, "the first beat has nothing to compare with"
    assert idle_stop.note_tick(w + 3600, m + 1, 1.0) is True
    assert idle_stop._state["requested"] is False
    assert idle_stop._since_ms() == round((w + 3600) * 1000), "the grace counts from the resume, not the boot"
    assert wake.pending(), "the next due instant is reported again after a resume"
    assert record == ["session:engine.resumed"]
    from voice.observer import _CAT
    assert _CAT["session"] == "system", "engine.resumed must not count as real activity"
    wake._reset_for_tests()


def test_nobody_after_a_resume_is_the_short_grace_again():
    now = 1_800_000_000_000
    resumed = now - 2 * MIN
    why = idle_stop.decide(now, now - 1000, resumed, False, None, 15 * MIN, last_presence_ms=None, grace_ms=MIN)
    assert why and "since boot or resume" in why


def test_the_pulse_looks_for_a_resume_before_anything_else():
    import inspect
    from nucleo.pulse import loop
    src = inspect.getsource(loop.OrchestratorLoop.tick)
    assert src.index("self._note_resume(") < src.index("self._supervise_workers(") < src.index("self._maybe_idle_stop(")


# ── presence is a connected person ─────────────────────────────────────────────────────────────────────────────

def test_a_visible_connected_screen_is_presence_and_a_stream_alone_is_not():
    from voice import screens
    screens._reset_for_tests()
    try:
        screens.attach("desktop:abc")
        screens.beat("desktop:abc", visible=True)
        assert screens.last_presence_ms() is None, "a stream open or a visibility beat counted as a person"
        screens.present("desktop:abc")
        assert screens.last_presence_ms() is not None
        assert screens.last_input_ms() is None, "presence is not input: the grace of an unattended wake reads both"
    finally:
        screens._reset_for_tests()


def test_the_beat_marks_presence_only_for_a_visible_screen():
    from server import screens_api
    from voice import screens
    screens._reset_for_tests()
    try:
        screens_api.beat({"dev": "mobile:x1", "visible": False, "present": True})
        assert screens.last_presence_ms() is None, "a hidden tab is nobody"
        screens_api.beat({"dev": "mobile:x1", "visible": True, "present": True})
        assert screens.last_presence_ms() is not None
    finally:
        screens._reset_for_tests()


def test_a_page_opened_keeps_the_engine_up_for_the_full_window():
    now = 1_800_000_000_000
    boot = now - 10 * MIN
    assert idle_stop.decide(now, None, boot, False, None, 15 * MIN, last_presence_ms=boot + 5_000, grace_ms=MIN) is None
    assert idle_stop.decide(now + 6 * MIN, None, boot, False, None, 15 * MIN,
                            last_presence_ms=boot + 5_000, grace_ms=MIN), "15 min after the last beat it stops"


# ── hole 1: a widget's background tick is not activity ─────────────────────────────────────────────────────────

def test_a_background_tick_never_moves_the_activity_clock(monkeypatch):
    from observability import identity
    from widgets import background as bg
    from nucleo import runstate
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    identity._last_real_activity_ms["v"] = None

    def _tick(wid):                                   # what a tick does: saves, writes memory, emits (in a thread)
        from voice.observer import stamp_identity
        stamp_identity({"kind": "widget", "label": "data", "text": wid})
        stamp_identity({"kind": "memory", "label": "write", "text": wid})
    monkeypatch.setattr(bg, "_call_tick", _tick)
    asyncio.run(bg._tick_once("agenda", "passive"))
    assert identity.last_real_activity_ms() is None, "a widget's own cycle counted as somebody using the engine"
    identity.note_real_activity()
    assert identity.last_real_activity_ms() is not None, "outside a tick, activity still counts"
    identity._last_real_activity_ms["v"] = None


# ── hole 3: a job the engine could not fire holds nothing ──────────────────────────────────────────────────────

def test_a_past_due_job_does_not_hold_the_engine_up(monkeypatch):
    from nucleo.pulse import due, scheduler
    now = 1_800_000_000.0
    jobs = [{"id": 1, "next_run": now - 600}, {"id": 2, "next_run": now + 7200}, {"id": 3, "next_run": None}]
    monkeypatch.setattr(scheduler, "list_jobs", lambda active_only=True: jobs)
    assert due.next_owed(now) == now + 7200, "a job ⏻ held past its instant pinned the engine awake"
    jobs.pop(1)
    assert due.next_owed(now) is None
    why = idle_stop.decide(round(now * 1000), None, round(now * 1000) - 60 * MIN, False, due.next_owed(now),
                           15 * MIN, last_presence_ms=round(now * 1000) - 30 * MIN, grace_ms=MIN)
    assert why, "an overdue job the engine could not fire kept it from stopping"


def test_the_idle_stop_reads_the_owed_instant_not_the_raw_schedule(monkeypatch):
    from nucleo.pulse import due
    seen = []
    monkeypatch.setattr(due, "next_owed", lambda now: seen.append(now) or 123.0)
    assert idle_stop._readings(1000.0)[2] == 123.0 and seen == [1000.0]

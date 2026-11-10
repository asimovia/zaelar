"""V2-872 W3 — a cheap boot: a host that stops when idle does not warm the search Chromium, nothing loads YouTube
as a side effect of a boot, and a passive widget's tick follows presence.

Measured on one hosted engine (2 shared vCPU), every boot: the Chromium warm-up 53-96 s, a YouTube results page
through that Chromium ~50 s in (the search status probe, 18 s, «unreachable»), and the agenda's tick every 10 s
with five calendar calls with nobody on screen — the CPU quota spent and the voice throttled behind it.

Each guard was seen RED with its mechanism disarmed (see the PR).
"""
from __future__ import annotations

import asyncio
import json
import shutil

import pytest

from nucleo.llm import prewarm
from widgets import background as bg

_REAL_SLEEP = asyncio.sleep


# ── 1 · the search Chromium is warmed only where the host does not sleep ─────────────────────────────────────

@pytest.mark.parametrize("declared, idle_min, want", [
    (None, 15, False),     # a host that stops when idle, nothing declared → no warm-up
    (None, 0, True),       # a laptop that stays up → the repo default
    (True, 15, True),      # the deployment's own file always wins
    (False, 0, False),
])
def test_the_browser_prewarm_decision(declared, idle_min, want):
    assert prewarm.browser_prewarm_wanted(declared, idle_min) is want


def _config_dir(tmp_path, deployment: dict | None):
    from nucleo.workers import envelope
    shutil.copy(f"{envelope._HERE}/resources.default.json", tmp_path / "resources.default.json")
    if deployment is not None:
        (tmp_path / "resources.json").write_text(json.dumps(deployment), encoding="utf-8")
    return str(tmp_path)


def _warm(monkeypatch) -> list:
    from search import browser
    started: list = []

    async def _fake_start():
        started.append(1)
        return True
    monkeypatch.setattr(browser, "ensure_started", _fake_start)
    asyncio.run(prewarm._warm_browser())
    return started


def test_a_host_that_stops_when_idle_does_not_start_the_chromium_at_boot(monkeypatch, tmp_path):
    from nucleo.workers import envelope
    monkeypatch.setattr(envelope, "_HERE", _config_dir(tmp_path, None))
    monkeypatch.setenv("ZAELAR_IDLE_STOP_MIN", "15")
    assert _warm(monkeypatch) == []


def test_a_deployment_that_declares_false_does_not_start_it_either(monkeypatch, tmp_path):
    from nucleo.workers import envelope
    monkeypatch.setattr(envelope, "_HERE", _config_dir(tmp_path, {"prewarm_browser": False}))
    monkeypatch.delenv("ZAELAR_IDLE_STOP_MIN", raising=False)
    assert _warm(monkeypatch) == []


def test_a_laptop_that_stays_up_still_warms_it(monkeypatch, tmp_path):
    from nucleo.workers import envelope
    monkeypatch.setattr(envelope, "_HERE", _config_dir(tmp_path, None))
    monkeypatch.delenv("ZAELAR_IDLE_STOP_MIN", raising=False)
    assert _warm(monkeypatch) == [1]


def test_the_first_search_starts_the_browser_itself(monkeypatch):
    """Not warming it costs nothing but the first search's start: every door asks `ensure_started` first."""
    from search import browser
    asked: list = []

    async def _fake_start():
        asked.append(1)
        return False
    monkeypatch.setattr(browser, "ensure_started", _fake_start)
    for door in (browser.search_google("x"), browser.page_html("https://example.com/")):
        with pytest.raises(RuntimeError):
            asyncio.run(door)
    assert asked == [1, 1]


# ── 2 · nothing touches YouTube as a side effect of a boot ───────────────────────────────────────────────────

def test_the_boot_probe_does_not_start_the_browser_nor_load_youtube_through_it(monkeypatch):
    """The ~50 s-after-boot «youtube_browser» call of every boot was the status probe (`search.api.prime_cache`)."""
    from search import api, browser, health
    from search.providers import PROVIDERS, keys
    in_chromium = {n for n, p in PROVIDERS.items() if p.env_switch[0] == "BROWSER_SEARCH"}
    assert "youtube_browser" in in_chromium and "google" in in_chromium
    monkeypatch.setattr(keys, "leased", lambda: False)
    monkeypatch.setattr(api, "_health_cache", {"at": 0.0, "rows": []})
    asked: list = []
    monkeypatch.setattr(health, "probe_all", lambda names=None, parallel=True: asked.extend(names or []) or [])
    monkeypatch.setattr(browser, "_ctx", None)
    api.prime_cache()
    assert asked and not in_chromium & set(asked)
    assert {r["provider"] for r in api.cached_rows() if r["state"] == "unprobed"} == in_chromium
    # …and a browser someone already started is probed as before.
    asked.clear()
    monkeypatch.setattr(browser, "_ctx", object())
    api.prime_cache()
    assert in_chromium <= set(asked)


def test_the_video_card_loads_without_a_search(monkeypatch):
    """The card's load path (`_load`, `view_data`, the prompt digest) reads its store and nothing else."""
    from search import browser, video
    calls: list = []
    monkeypatch.setattr(video, "find_videos", lambda *a, **k: calls.append(("find", a)) or [])
    monkeypatch.setattr(browser, "page_html_sync", lambda *a, **k: calls.append(("page", a)) or "")
    from widgets.youtube import data
    monkeypatch.setattr(data, "_search_many", lambda *a, **k: calls.append(("many", a)) or [])
    data._load()
    data.view_data()
    data.prompt_digest()
    assert calls == []


# ── 3 · a passive tick follows presence ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("declared, screens, always, want", [
    (10, True, False, 10),       # a person looking: the declared cadence
    (10, False, False, 300),     # nobody looking: the idle ceiling
    (10, False, True, 10),       # `always`: kept off-screen
    (600, False, False, 600),    # a declared cadence slower than the ceiling is never sped up
])
def test_the_effective_period(declared, screens, always, want):
    assert bg.effective_period(declared, screens, always, 300) == want


def test_a_first_tick_waits_without_a_screen_and_runs_at_once_with_one():
    assert bg.due(2.0, None, 0.0, 10, True, False, 300)
    assert not bg.due(2.0, None, 0.0, 10, False, False, 300)
    assert bg.due(300.0, None, 0.0, 10, False, False, 300)
    assert bg.due(2.0, None, 0.0, 10, False, True, 300)
    # a screen that opens after an idle tick brings the declared cadence back on the next wake
    assert not bg.due(110.0, 100.0, 0.0, 10, False, False, 300)
    assert bg.due(110.0, 100.0, 0.0, 10, True, False, 300)


def test_always_is_read_from_the_manifest_and_validated():
    from widgets import validator_actions as va
    assert bg.background_always({"background": {"every": "10s", "always": True}})
    assert not bg.background_always({"background": {"every": "10s"}})
    assert not bg.background_always({"background": "10s"})
    src = "def tick(ctx):\n    pass\n"
    assert va._validate_background({"background": {"every": "10s", "always": True}}, src) is None
    assert va._validate_background({"background": {"every": "10s", "always": "yes"}}, src)


def _run_loop(monkeypatch, *, screens: bool, always: bool = False, wakes: int = 40) -> list[float]:
    """Drive `_run_widget` (declared 10 s) on a fake clock for `wakes` wakes; return the instants it ticked."""
    clock = {"t": 0.0}
    ticks: list[float] = []
    monkeypatch.setattr(bg.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(bg, "_screens_open", lambda: screens)
    monkeypatch.setattr(bg, "_idle_every_s", lambda: 300)

    async def _tick(wid, kind):
        ticks.append(clock["t"])
    monkeypatch.setattr(bg, "_tick_once", _tick)
    n = {"wakes": 0}

    async def _sleep(s):
        n["wakes"] += 1
        if n["wakes"] > wakes:
            raise asyncio.CancelledError
        clock["t"] += s
        await _REAL_SLEEP(0)
    monkeypatch.setattr(bg.asyncio, "sleep", _sleep)
    try:
        asyncio.run(bg._run_widget("w", 10, "passive", always))
    except asyncio.CancelledError:      # the fake clock's end, raised from the loop's sleep
        pass
    return ticks


def test_the_scheduler_ticks_at_the_idle_ceiling_with_nobody_looking(monkeypatch):
    ticks = _run_loop(monkeypatch, screens=False)      # ~400 s of loop
    assert len(ticks) == 1, ticks                       # one tick at 300 s after start, not forty


def test_the_scheduler_keeps_the_declared_cadence_with_a_screen_or_always(monkeypatch):
    assert len(_run_loop(monkeypatch, screens=True)) >= 35
    assert len(_run_loop(monkeypatch, screens=False, always=True)) >= 35

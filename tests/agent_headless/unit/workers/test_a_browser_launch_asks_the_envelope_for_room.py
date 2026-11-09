"""A browser launch asks the worker envelope for room first (V2-867 F2).

On a small host three Chromium processes and one worker left 45 MB free and the voice broke: the browsers launched
outside the envelope. Now both launch sites go through `nucleo.workers.room.room_for`:
  · without room the NEWEST running worker is paused before the launch, and resumed after it once room returns;
  · with room nothing is paused;
  · `room` resumes only what IT paused — never a pause of the operator's ⏻ or of the envelope's;
  · the operator's own window is never refused (one poll, then it opens); the search browser waits like a worker;
  · the search module launches ONE persistent context even under concurrent callers.

Disarms (each seen red, 2026-11-09): `_pause_newest` pauses nothing → the pause-first and his-window tests red; the
resume after the launch not scheduled → the pause-first test reds; `resume_ours` taking every paused record instead
of its own mark → the not-its-own test reds; the start lock's re-check dropped in `search.browser.ensure_started` →
the concurrent-start test reds; either launch site taken out of its `room_for` → its wiring test reds.
"""
from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace

import pytest

from nucleo import dispatch
from nucleo.workers import envelope, room

GB = 1024 ** 3
LOW = (4 * GB, int(0.05 * 4 * GB))
HIGH = (4 * GB, int(0.6 * 4 * GB))


class _Sess:
    def __init__(self, rec, log):
        self.rec, self.log = rec, log

    def pause(self):
        self.rec.paused = True
        self.log.append(("pause", self.rec.task_id))
        return True

    def resume(self):
        self.rec.paused = False
        self.log.append(("resume", self.rec.task_id))
        return True


def _rec(tid, started, log, paused=False, paused_by=""):
    r = SimpleNamespace(task_id=tid, status="running", started=started, paused=paused, paused_by=paused_by)
    r.session = _Sess(r, log)
    return r


@pytest.fixture
def host(monkeypatch):
    """A host whose free memory the test sets; the dispatch registry replaced by the test's own records."""
    state = {"mem": HIGH}
    monkeypatch.setattr(envelope, "measured", lambda: state["mem"])
    monkeypatch.setattr(envelope, "policy", lambda: {"admit_free_ratio": 0.2, "pause_free_ratio": 0.1})
    monkeypatch.setattr(envelope, "_sheds", {})
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    monkeypatch.setattr(room, "_stopped", lambda: False)
    monkeypatch.setattr(room, "_say", lambda *a, **k: None)
    monkeypatch.setattr(room, "_resumer", None)
    return state


def test_without_room_the_newest_worker_is_paused_before_the_launch_and_resumed_after(host):
    log: list = []
    old, new = _rec("old", 1.0, log), _rec("new", 2.0, log)
    dispatch._SESSIONS.update({"old": old, "new": new})
    host["mem"] = LOW

    async def run():
        async def free_after_pause():                     # the pause takes effect: the host has room again
            while not new.paused:
                await asyncio.sleep(0.001)
            host["mem"] = HIGH
        asyncio.get_running_loop().create_task(free_after_pause())
        async with room.room_for("browser", poll_s=0.01):
            log.append(("launch", ""))
            host["mem"] = LOW                             # the browser takes the room; the worker stays paused
        assert new.paused and new.paused_by == room.MARK, "the worker was resumed while there was no room"
        host["mem"] = HIGH                                # room returns after the launch
        await asyncio.wait_for(room._resumer, 2)

    asyncio.run(asyncio.wait_for(run(), 3))      # a missing pause would wait for room forever
    assert log == [("pause", "new"), ("launch", ""), ("resume", "new")], log
    assert not old.paused, "the oldest worker was paused too"
    assert new.paused_by == ""


def test_with_room_nothing_is_paused(host):
    log: list = []
    dispatch._SESSIONS.update({"a": _rec("a", 1.0, log)})

    async def run():
        async with room.room_for("browser", poll_s=0.01):
            log.append(("launch", ""))
    asyncio.run(asyncio.wait_for(run(), 2))
    assert log == [("launch", "")]


@pytest.mark.parametrize("who", ["operator", "envelope", ""])
def test_room_never_resumes_a_pause_that_is_not_its_own(host, who):
    log: list = []
    theirs = _rec("theirs", 1.0, log, paused=True, paused_by=who)
    dispatch._SESSIONS.update({"theirs": theirs})
    host["mem"] = HIGH
    assert room.resume_ours() == []
    assert theirs.paused and theirs.paused_by == who and log == []


def test_his_window_opens_after_one_poll_even_without_room(host):
    log: list = []
    w = _rec("w", 1.0, log)
    dispatch._SESSIONS.update({"w": w})
    host["mem"] = LOW

    async def run():
        async with room.room_for("browser", patient=False, poll_s=0.01):
            log.append(("launch", ""))
    asyncio.run(asyncio.wait_for(run(), 2))
    assert log == [("pause", "w"), ("launch", "")]


def test_room_leaves_its_pauses_to_the_stop_switch(host, monkeypatch):
    log: list = []
    w = _rec("w", 1.0, log, paused=True, paused_by=room.MARK)
    dispatch._SESSIONS.update({"w": w})
    monkeypatch.setattr(room, "_stopped", lambda: True)
    assert room.resume_ours() == []
    assert w.paused and w.paused_by == "" and log == []


def test_two_concurrent_search_starts_launch_one_context(monkeypatch, host):
    from search import browser
    launched: list = []

    class _Ctx:
        def set_default_timeout(self, _ms):
            pass

        async def new_page(self):
            raise RuntimeError("no network in a unit test")

    class _Chromium:
        async def launch_persistent_context(self, *_a, **_k):
            await asyncio.sleep(0.02)                    # a launch takes time: a second caller arrives meanwhile
            launched.append(1)
            return _Ctx()

    class _Starter:
        async def start(self):
            return SimpleNamespace(chromium=_Chromium())

    mod = types.ModuleType("playwright.async_api")
    mod.async_playwright = lambda: _Starter()
    monkeypatch.setitem(sys.modules, "playwright.async_api", mod)
    monkeypatch.setenv("BROWSER_SEARCH", "1")
    for name in ("_pw", "_ctx", "_start_lock", "_owner"):
        monkeypatch.setattr(browser, name, None)
    from search import hooks
    monkeypatch.setattr(hooks, "room", None)

    async def run():
        return await asyncio.gather(browser.ensure_started(), browser.ensure_started())
    assert asyncio.run(run()) == [True, True]
    assert len(launched) == 1, "two concurrent callers launched two Chromium contexts"


def _recording_room(log):
    import contextlib

    @contextlib.asynccontextmanager
    async def fake(what, **kw):
        log.append(("room", what, kw.get("patient")))
        yield
        log.append(("room_exit", what))
    return fake


def test_the_search_browser_launches_inside_the_hosts_room(monkeypatch):
    from search import browser, hooks
    log: list = []

    class _Ctx:
        def set_default_timeout(self, _ms):
            pass

        async def new_page(self):
            raise RuntimeError("no network in a unit test")

    class _Chromium:
        async def launch_persistent_context(self, *_a, **_k):
            log.append(("launch",))
            return _Ctx()

    class _Starter:
        async def start(self):
            return SimpleNamespace(chromium=_Chromium())

    mod = types.ModuleType("playwright.async_api")
    mod.async_playwright = lambda: _Starter()
    monkeypatch.setitem(sys.modules, "playwright.async_api", mod)
    monkeypatch.setenv("BROWSER_SEARCH", "1")
    for name in ("_pw", "_ctx", "_start_lock", "_owner"):
        monkeypatch.setattr(browser, name, None)
    monkeypatch.setattr(hooks, "room", _recording_room(log))
    assert asyncio.run(browser.ensure_started()) is True
    assert log == [("room", "browser", None), ("launch",), ("room_exit", "browser")], log


def test_his_window_launches_inside_room_and_is_never_held(monkeypatch):
    from widgets.navegador import owner as o, owner_page
    log: list = []

    class _Ctx:
        pages: list = []

        async def add_init_script(self, _js):
            pass

        async def add_cookies(self, _c):
            pass

        def on(self, *_a):
            pass

        def set_default_navigation_timeout(self, _ms):
            pass

        def set_default_timeout(self, _ms):
            pass

        async def new_page(self):
            return SimpleNamespace(is_closed=lambda: False)

    class _Chromium:
        async def launch_persistent_context(self, *_a, **_k):
            log.append(("launch",))
            return _Ctx()

    monkeypatch.setattr(o, "_page", None)
    monkeypatch.setattr(o, "_context", None)
    monkeypatch.setattr(o, "_pw", SimpleNamespace(chromium=_Chromium()))
    monkeypatch.setattr(o, "_headless", lambda: True)
    monkeypatch.setattr(o, "_remote_port", lambda: None)
    monkeypatch.setattr(o, "_profile_dir", lambda: "/nonexistent-profile")
    monkeypatch.setattr(o, "_browser_locale", lambda: ("en-US", "UTC"))
    monkeypatch.setattr(o, "_emit", lambda *a, **k: None)
    monkeypatch.setattr(room, "room_for", _recording_room(log))
    asyncio.run(owner_page._ensure_page())
    assert log == [("room", "browser", False), ("launch",), ("room_exit", "browser")], log

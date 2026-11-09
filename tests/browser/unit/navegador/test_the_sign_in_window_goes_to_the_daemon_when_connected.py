"""The sign-in window goes to the local daemon only when one is connected and it is where the window goes (V2-575 P2).

`owner._browser_backend()` is the switch: `daemon` when a loopback daemon declared `browser.auth` and this engine has
no window of its own, `inproc` otherwise. With no daemon nothing changes — the reach is exactly what it was (decision
5). An engine WITH a screen keeps its own window even with a daemon connected: the task's browser runs here, and a
session made in another profile is one the task cannot read. When the window goes to the daemon, it opens on THIS
engine's profile (same computer), and the engine watches it until two reads in a row show he signed in.

The daemon is faked at the link's one HTTP seam (`daemon_link._call`).
Disarms: `browser_backend` answering `daemon` whenever a link exists (ignoring the reach) → red; `sync` not
registering the daemon → red.
"""
import asyncio

import pytest

from nucleo import browser_window
from widgets.navegador import owner, tasks
from widgets.navegador.owner_login import daemon_link


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    owner._auth_resume.clear()
    browser_window.daemon_gone()
    daemon_link._state["registered"] = False
    monkeypatch.setattr(owner, "_daemon_told", False)
    monkeypatch.setattr(owner, "_LOGIN_POLL", 0.0)
    monkeypatch.setattr(owner, "_visible_override", None)
    monkeypatch.setattr(owner, "_auth_active", "")

    async def _notify(title, text, **kw):
        return True
    from voice import proactive
    monkeypatch.setattr(proactive, "notify", _notify)

    async def _no_session(site):
        return False
    monkeypatch.setattr(owner, "_already_authenticated", _no_session)

    async def _stop():
        return None
    monkeypatch.setattr(owner, "stop", _stop)
    yield
    for t in list(owner._login_timeouts.values()):
        t.cancel()
    owner._login_timeouts.clear()
    owner._auth_resume.clear()
    browser_window.daemon_gone()
    daemon_link._state["registered"] = False


def _daemon(monkeypatch, caps, states=None):
    """A daemon on loopback declaring `caps`; `/browser/state` answers the given sequence."""
    calls: list = []
    seq = list(states or [])

    async def _call(path, payload=None, *, timeout=2.0):
        calls.append((path, payload))
        if path == "/health":
            return {"ok": True, "capabilities": list(caps)} if caps is not None else {}
        if path == "/browser/open":
            return {"ok": True, "open": True}
        if path == "/browser/state":
            return seq.pop(0) if seq else {"ok": True, "open": True, "url": "https://shop.example/login",
                                           "new_cookies": 0}
        return {"ok": True}
    monkeypatch.setattr(daemon_link, "_call", _call)
    return calls


def _screen(monkeypatch, has: bool):
    monkeypatch.setattr(browser_window, "_has_display", lambda: has)


@pytest.mark.parametrize("display", [True, False])
def test_no_daemon_changes_nothing(monkeypatch, display):
    _screen(monkeypatch, display)
    _daemon(monkeypatch, None)
    before = browser_window.reach()
    assert asyncio.run(daemon_link.sync()) is False
    assert owner._browser_backend() == "inproc" and browser_window.reach() == before


def test_a_connected_daemon_is_the_backend_where_the_engine_has_no_window(monkeypatch):
    _screen(monkeypatch, False)
    _daemon(monkeypatch, ["files.list", "browser.auth"])
    assert asyncio.run(daemon_link.sync()) is True
    assert owner._browser_backend() == "daemon"


def test_an_engine_with_its_own_screen_keeps_its_own_window(monkeypatch):
    _screen(monkeypatch, True)
    _daemon(monkeypatch, ["files.list", "browser.auth"])
    asyncio.run(daemon_link.sync())
    assert owner._browser_backend() == "inproc", "the session must land in the profile the task's browser reads"


def test_a_daemon_without_the_window_capability_is_not_registered(monkeypatch):
    _screen(monkeypatch, False)
    _daemon(monkeypatch, ["files.list", "files.read"])
    assert asyncio.run(daemon_link.sync()) is False
    assert owner._browser_backend() == "inproc" and browser_window.reach() == ""


def test_sync_never_clears_a_link_another_transport_registered(monkeypatch):
    _screen(monkeypatch, False)
    browser_window.daemon_connected([browser_window.BROWSER_CAPABILITY], opener=lambda u, t: True)
    _daemon(monkeypatch, None)
    asyncio.run(daemon_link.sync())
    assert browser_window.reach() == browser_window.DAEMON


def test_the_handover_opens_on_the_daemon_with_this_engines_profile_and_watches_it(monkeypatch):
    _screen(monkeypatch, False)
    states = [{"ok": True, "open": True, "url": "https://shop.example/login", "new_cookies": 0},
              {"ok": True, "open": True, "url": "https://shop.example/account", "new_cookies": 2},
              {"ok": True, "open": True, "url": "https://shop.example/account", "new_cookies": 2}]
    calls = _daemon(monkeypatch, ["browser.auth"], states)
    done: list = []

    async def _auth_done(tid):
        done.append(tid)
    monkeypatch.setattr(owner, "_auth_done", _auth_done)
    tid = tasks.create("comprar en la tienda", title="Tienda")

    async def run():
        await owner._authenticate(tid, "https://shop.example/login", site="shop.example", goal="comprar")
        assert tasks.get(tid)["awaiting_login"] and not tasks.get(tid).get("blocked")
        await asyncio.wait_for(owner._login_timeouts[tid], timeout=5)
    asyncio.run(run())
    opens = [p for path, p in calls if path == "/browser/open"]
    assert opens == [{"task": tid, "url": "https://shop.example/login", "profile": owner._profile_dir()}], opens
    assert done == [tid], "two signed-in reads in a row end the wait through the same _auth_done"
    assert ("/browser/close", {"task": tid}) in calls, "the window closes so the profile is free for the engine"


def test_a_window_he_closed_gives_the_tasks_back(monkeypatch):
    _screen(monkeypatch, False)
    _daemon(monkeypatch, ["browser.auth"], [{"ok": True, "open": False, "closed_by_user": True}])
    abandoned: list = []

    async def _abandon(tid):
        abandoned.append(tid)
    monkeypatch.setattr(owner, "_abandon_login", _abandon)
    tid = tasks.create("comprar en la tienda", title="Tienda")

    async def run():
        await owner._authenticate(tid, "https://shop.example/login", site="shop.example", goal="comprar")
        await asyncio.wait_for(owner._login_timeouts[tid], timeout=5)
    asyncio.run(run())
    assert abandoned == [tid]


def test_the_engines_window_is_untouched_when_it_has_a_screen(monkeypatch):
    """With a display the handover is today's: no request reaches the daemon's browser at all."""
    _screen(monkeypatch, True)
    calls = _daemon(monkeypatch, ["browser.auth"])
    opened: list = []

    class _TB:
        def __init__(self, tid):
            self.page = None

        async def open_target(self, url):
            opened.append(url)
    monkeypatch.setattr(owner, "TaskBrowser", _TB)
    monkeypatch.setattr(owner, "_headed", True)
    monkeypatch.setattr(owner, "_arm_login_watch", lambda tid, site: None)

    async def _fp(tb):
        return set()
    monkeypatch.setattr(owner, "_cookie_fingerprint", _fp)
    tid = tasks.create("comprar en la tienda", title="Tienda")
    asyncio.run(owner._authenticate(tid, "https://shop.example/login", site="shop.example", goal="comprar"))
    assert opened == ["https://shop.example/login"], "the engine's own window opened"
    assert not [c for c in calls if c[0].startswith("/browser/")], calls


def test_the_link_keeps_the_daemons_port():
    import daemon
    assert daemon_link._DEFAULT_PORT == daemon.PORT

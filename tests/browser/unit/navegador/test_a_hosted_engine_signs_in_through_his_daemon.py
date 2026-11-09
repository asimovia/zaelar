"""A hosted engine opens the sign-in window on his computer through the relay and brings that ONE site's session back
(V2-575 P3).

An engine away from him cannot reach his loopback. With a relay to ask (`CONTROL_PLANE_URL`), presence decides whether
his daemon is registered as the window's backend (`browser_window.daemon_connected` / `daemon_gone`); the sign-in then
runs open → state (two signed-in reads) → `browser.export_session` → import into this engine's browser → close →
`_auth_done`. The import takes only the cookies and storage of the domain the session came for. From his PHONE no
window opens anywhere. With no relay configured nothing changes.

End to end: this engine's one HTTP seam (`relay_link._http`) is bridged to an in-process relay that holds the REAL
daemon's outbound link (`daemon/relay/client.py`); the daemon's Chromium is a fake injected at its launcher seam, and
this engine's browser context is a fake that records what it was given.
Disarms: `sync` registering a daemon presence says is gone → red; the import keeping another domain's cookie → red;
`reach` ignoring `phone` → red.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from nucleo import browser_window
from tests.infrastructure.unit.daemon.fake_relay import FakeRelay
from widgets.navegador import owner, owner_page, tasks
from widgets.navegador.owner_login import authenticate, daemon_link, relay_link


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    owner._auth_resume.clear()
    owner_page._imported_sessions.clear()
    browser_window.daemon_gone()
    relay_link._state.update(registered=False, presence={})
    daemon_link._state["registered"] = False
    monkeypatch.setattr(owner, "_daemon_told", False)
    monkeypatch.setattr(owner, "_LOGIN_POLL", 0.02)
    monkeypatch.setattr(owner, "_visible_override", None)
    monkeypatch.setattr(owner, "_auth_active", "")
    monkeypatch.setattr(browser_window, "_has_display", lambda: False)

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

    async def _no_loopback(path, payload=None, *, timeout=2.0):
        return {}
    monkeypatch.setattr(daemon_link, "_call", _no_loopback)
    yield
    for t in list(owner._login_timeouts.values()):
        t.cancel()
    owner._login_timeouts.clear()
    owner._auth_resume.clear()
    owner_page._imported_sessions.clear()
    browser_window.daemon_gone()
    relay_link._state.update(registered=False, presence={})


def _hosted(monkeypatch, on=True):
    monkeypatch.setattr(relay_link, "_is_cloud", lambda: on)
    if on:
        monkeypatch.setenv("CONTROL_PLANE_URL", "https://service.test")
        monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", "svc-token")
    else:
        monkeypatch.delenv("CONTROL_PLANE_URL", raising=False)


class _EngineCtx:
    """This engine's browser context: records what the import gives it."""

    def __init__(self):
        self.cookies, self.scripts = [], []

    async def add_cookies(self, cookies):
        self.cookies.extend(cookies)

    async def add_init_script(self, script):
        self.scripts.append(script)


# ── presence drives the link ────────────────────────────────────────────────────────────────────────────────

def test_with_no_relay_nothing_changes(monkeypatch):
    _hosted(monkeypatch, False)

    async def boom(*a, **k):
        raise AssertionError("a self-hosted engine asked a relay")
    monkeypatch.setattr(relay_link, "_http", boom)
    assert relay_link.hosted() is False
    assert asyncio.run(relay_link.sync()) is False and browser_window.reach() == ""


def test_presence_registers_and_withdraws_the_daemon(monkeypatch):
    _hosted(monkeypatch)
    presence = {"connected": True, "caps": ["files.list", "browser.auth"], "version": "0.3.0", "platform": "macos",
                "since": "2026-11-09T10:00:00Z"}
    seen: list = []

    async def _http(method, path, body=None, *, timeout=0):
        seen.append((method, path))
        return 200, dict(presence)
    monkeypatch.setattr(relay_link, "_http", _http)
    assert asyncio.run(relay_link.sync()) is True and browser_window.reach() == browser_window.DAEMON
    presence["connected"] = False
    assert asyncio.run(relay_link.sync()) is False and browser_window.reach() == ""
    presence.update(connected=True, caps=["files.list"])
    assert asyncio.run(relay_link.sync()) is False, "a daemon that cannot open a window is not the window's backend"
    assert seen[0] == ("GET", "/daemon/presence")


def test_the_relay_never_clears_the_loopback_link(monkeypatch):
    _hosted(monkeypatch)

    async def _http(method, path, body=None, *, timeout=0):
        return 200, {"connected": False}
    monkeypatch.setattr(relay_link, "_http", _http)
    browser_window.daemon_connected([browser_window.BROWSER_CAPABILITY], opener=lambda u, t: True)
    asyncio.run(relay_link.sync())
    assert browser_window.reach() == browser_window.DAEMON


# ── the phone ───────────────────────────────────────────────────────────────────────────────────────────────

def test_a_phone_never_gets_a_window(monkeypatch):
    browser_window.daemon_connected([browser_window.BROWSER_CAPABILITY], opener=lambda u, t: True)
    monkeypatch.setattr(browser_window, "_has_display", lambda: True)
    assert browser_window.reach("phone") == ""
    assert browser_window.reach("computer") == browser_window.HERE


def test_a_sign_in_asked_from_the_phone_blocks_as_phone(monkeypatch):
    _hosted(monkeypatch, False)
    browser_window.daemon_connected([browser_window.BROWSER_CAPABILITY], opener=lambda u, t: True)
    monkeypatch.setattr(authenticate, "_surface_of", lambda tid: "phone")
    opened: list = []
    monkeypatch.setattr(browser_window, "open_on_daemon", lambda *a: opened.append(a))
    tid = tasks.create("comprar en la tienda", title="Tienda")
    asyncio.run(owner._authenticate(tid, "https://shop.example.com/login", site="shop.example.com", goal="x"))
    assert tasks.get(tid).get("blocked") == "phone" and not opened


# ── the import ──────────────────────────────────────────────────────────────────────────────────────────────

def test_the_import_takes_only_the_domain_it_came_for(monkeypatch):
    ctx = _EngineCtx()
    monkeypatch.setattr(owner, "_context", ctx)
    state = {"cookies": [{"name": "sid", "value": "S1", "domain": ".shop.example.com", "path": "/", "sameSite": "Lax"},
                         {"name": "sid", "value": "OTHER", "domain": ".other.example.net", "path": "/"}],
             "origins": [{"origin": "https://shop.example.com", "localStorage": [{"name": "k", "value": "LS"}]},
                         {"origin": "https://other.example.net", "localStorage": [{"name": "k", "value": "NO"}]}]}
    out = asyncio.run(owner._import_session("example.com", state))
    assert out == {"ok": True, "cookies": 1, "origins": 1}, out
    assert [c["value"] for c in ctx.cookies] == ["S1"]
    assert len(ctx.scripts) == 1 and "LS" in ctx.scripts[0] and "NO" not in ctx.scripts[0]
    assert "S1" not in json.dumps(out), "the import answers counts"


def test_an_imported_session_survives_a_relaunch(monkeypatch):
    monkeypatch.setattr(owner, "_context", None)
    asyncio.run(owner._import_session("example.com", {"cookies": [
        {"name": "sid", "value": "S1", "domain": "example.com", "path": "/"}], "origins": []}))
    fresh = _EngineCtx()
    asyncio.run(owner_page._apply_imported_sessions(fresh))
    assert [c["value"] for c in fresh.cookies] == ["S1"]


# ── end to end: engine → relay → the real daemon link ──────────────────────────────────────────────────────

class _Page:
    def __init__(self):
        self.url = "about:blank"

    async def goto(self, url, timeout=0):
        self.url = url

    async def bring_to_front(self):
        return None


class _DaemonCtx:
    def __init__(self):
        self._cookies = [{"name": "consent", "value": "old", "domain": ".shop.example.com", "path": "/"}]
        self.pages: list = []
        self.closed = False

    async def new_page(self):
        p = _Page()
        self.pages.append(p)
        return p

    async def cookies(self):
        return [dict(c) for c in self._cookies]

    async def storage_state(self):
        return {"cookies": [dict(c) for c in self._cookies] +
                [{"name": "sid", "value": "BANK", "domain": ".bank.example.org", "path": "/"}],
                "origins": [{"origin": "https://shop.example.com", "localStorage": [{"name": "t", "value": "LS"}]}]}


@pytest.fixture
def daemon_over_relay(tmp_path, monkeypatch):
    """The real daemon, paired to an in-process relay, with a fake Chromium; this engine's HTTP seam bridged to it."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import browser
    from daemon import config as dcfg
    from daemon.browser import window
    from daemon.relay import client, config
    dcfg.reset_cache()
    launched: list = []

    async def launcher(profile):
        ctx = _DaemonCtx()
        launched.append((str(profile), ctx))

        async def stop():
            ctx.closed = True
        return ctx, stop
    monkeypatch.setattr(browser, "WINDOWS", window.Windows(launcher=launcher))
    monkeypatch.setattr(browser, "available", lambda: True)
    relay = FakeRelay()
    config.store_pairing("d" * 40, relay_url=relay.url)
    link = client.RelayClient()
    link.start()
    assert relay.connected.wait(10)
    commands: list = []

    async def _http(method, path, body=None, *, timeout=0):
        conn = relay.conns[-1]
        if path == "/daemon/presence":
            return 200, {"connected": link.connected(), "caps": conn.hello.get("caps"),
                         "version": conn.hello.get("version"), "platform": conn.hello.get("platform"),
                         "since": "2026-11-09T10:00:00Z"}
        if path == "/daemon/command":
            commands.append(body)
            res = await asyncio.to_thread(conn.command, body["op"], body.get("args"),
                                          deadline_ms=body.get("deadline_ms") or 30_000)
            return 200, ({"ok": True, "data": res["data"]} if res.get("ok") else {"ok": False, "error": res["error"]})
        return 404, {}
    _hosted(monkeypatch)
    monkeypatch.setattr(relay_link, "_http", _http)
    yield launched, commands, relay
    link.stop()
    link.join(5)
    browser.WINDOWS.close()
    relay.close()
    dcfg.reset_cache()


def test_open_state_export_import_through_the_relay(daemon_over_relay, monkeypatch):
    launched, commands, relay = daemon_over_relay
    engine_ctx = _EngineCtx()
    monkeypatch.setattr(owner, "_context", engine_ctx)
    done: list = []

    async def _auth_done(tid):
        done.append(tid)
    monkeypatch.setattr(owner, "_auth_done", _auth_done)
    tid = tasks.create("comprar en la tienda", title="Tienda")

    async def run():
        await owner._authenticate(tid, "https://shop.example.com/login", site="shop.example.com", goal="comprar")
        assert relay_link.owns_link() and tasks.get(tid)["awaiting_login"], "the window opened on his computer"
        from tests.waiting import until                       # he signs in on the daemon's window
        await until(lambda: launched and launched[0][1].pages, "the daemon's window to open a page", timeout_s=4)
        ctx = launched[0][1]
        await asyncio.sleep(0.1)
        ctx._cookies.append({"name": "sid", "value": "SECRET", "domain": ".shop.example.com", "path": "/"})
        ctx.pages[0].url = "https://shop.example.com/account"
        await asyncio.wait_for(owner._login_timeouts[tid], timeout=15)
    asyncio.run(run())

    ops = [c["op"] for c in commands]
    assert ops[0] == "browser.open" and "profile" not in commands[0]["args"], commands[0]
    assert launched[0][0].endswith("config/daemon/browser/profile"), "the window is on the daemon's own profile"
    assert "browser.state" in ops
    assert ops.index("browser.export_session") < ops.index("browser.close"), "exported while the window still held it"
    assert done == [tid], "the same _auth_done a local window ends with"
    values = sorted(c["value"] for c in engine_ctx.cookies)
    assert values == ["SECRET", "old"], f"only shop.example.com's cookies were imported: {values}"
    assert any("LS" in s for s in engine_ctx.scripts)
    assert launched[0][1].closed, "the window on his computer closed"
    events = [e for e in relay.conns[-1].events if e.get("name") == "browser.state"]
    assert events and events[0]["data"]["open"] is True, "the daemon tells the relay his window changed"
    assert "SECRET" not in json.dumps(events), "an event carries no cookie"

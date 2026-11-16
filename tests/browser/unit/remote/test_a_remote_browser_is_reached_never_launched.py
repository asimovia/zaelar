"""A remote browser is REACHED over CDP, never launched (V2-918).

`nucleo/remote_browser.py` is the one seam every browser consumer asks first. With nothing configured it says
`local` and both consumers launch their own Chromium as before. With a fixed CDP endpoint or a leased one:
  · the navegador widget and the search browser connect over CDP and open a fresh context — no launch at all;
  · a browser that cannot be reached is the seam's NAMED error (`RemoteBrowserUnavailable`) and STILL no launch:
    the navegador raises it, the search returns False so its chain falls to the next index;
  · the boot prewarm does not take a browser (it would lease one per boot);
  · the lease is asked from the control plane with this host's credential, reused while live, renewed only when it
    was USED since its last renewal, and a refusal is named.

Disarms (seen red 2026-11-16): `mode()` always 'local' → every remote test reds; the navegador's remote branch
dropped → the launch-forbidden fake is called; the renewal ignoring `used_at` → the idle-lease test reds.
"""
from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace

import pytest

from nucleo import remote_browser as rb


class _Ctx:
    def __init__(self):
        self.pages: list = []
        self.cookies: list = []

    async def add_init_script(self, _js):
        pass

    async def add_cookies(self, c):
        self.cookies += c

    def on(self, *_a):
        pass

    def set_default_navigation_timeout(self, _ms):
        pass

    def set_default_timeout(self, _ms):
        pass

    async def new_page(self):
        return SimpleNamespace(is_closed=lambda: False)

    async def close(self):
        pass


class _Browser:
    def __init__(self, log):
        self.log, self.connected = log, True

    def is_connected(self):
        return self.connected

    async def new_context(self, **kw):
        self.log.append(("new_context", kw.get("locale")))
        return _Ctx()

    async def close(self):
        self.connected = False


class _Chromium:
    def __init__(self, log, fail_connect=False):
        self.log, self.fail_connect = log, fail_connect

    async def launch_persistent_context(self, *_a, **_k):
        self.log.append(("LAUNCH",))
        raise AssertionError("remote mode must never launch a local Chromium")

    async def connect_over_cdp(self, url, **_k):
        self.log.append(("connect", url))
        if self.fail_connect:
            raise ConnectionRefusedError("nobody there")
        return _Browser(self.log)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("ZAELAR_BROWSER_CDP_URL", "ZAELAR_BROWSER_LEASE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(rb, "_lease", {})
    yield


def test_nothing_configured_is_local_mode():
    assert rb.mode() == "local"
    with pytest.raises(rb.RemoteBrowserUnavailable):
        asyncio.run(rb.endpoint())


def _navegador(monkeypatch, chromium):
    from widgets.navegador import owner as o, owner_page
    for name in ("_page", "_context", "_browser"):
        monkeypatch.setattr(o, name, None)
    monkeypatch.setattr(o, "_pw", SimpleNamespace(chromium=chromium))
    monkeypatch.setattr(o, "_browser_locale", lambda: ("es-ES", "Europe/Madrid"))
    monkeypatch.setattr(o, "_emit", lambda *a, **k: None)
    monkeypatch.setattr(owner_page, "_apply_imported_sessions", lambda _c: asyncio.sleep(0))
    return o, owner_page


def test_the_navegador_connects_to_the_remote_browser_and_launches_nothing(monkeypatch):
    monkeypatch.setenv("ZAELAR_BROWSER_CDP_URL", "http://[fdaa::1]:9223/s3cr3t")
    log: list = []
    o, owner_page = _navegador(monkeypatch, _Chromium(log))
    page = asyncio.run(owner_page._ensure_page())
    assert page is not None
    assert ("LAUNCH",) not in log
    assert log[:2] == [("connect", "http://[fdaa::1]:9223/s3cr3t"), ("new_context", "es-ES")], log
    assert o._browser is not None and o._context is not None


def test_an_unreachable_remote_browser_is_named_and_still_launches_nothing(monkeypatch):
    monkeypatch.setenv("ZAELAR_BROWSER_CDP_URL", "http://[fdaa::1]:9223/s3cr3t")
    log: list = []
    _o, owner_page = _navegador(monkeypatch, _Chromium(log, fail_connect=True))
    with pytest.raises(rb.RemoteBrowserUnavailable, match="CDP connect failed"):
        asyncio.run(owner_page._ensure_page())
    assert ("LAUNCH",) not in log


def test_a_remote_browser_that_ended_is_reconnected_not_reused(monkeypatch):
    monkeypatch.setenv("ZAELAR_BROWSER_CDP_URL", "http://[fdaa::1]:9223/s3cr3t")
    log: list = []
    o, owner_page = _navegador(monkeypatch, _Chromium(log))
    asyncio.run(owner_page._ensure_page())
    o._browser.connected = False                      # the lease ended on the other side
    o._page = SimpleNamespace(is_closed=lambda: False)  # a stale page handle must not be handed out
    asyncio.run(owner_page._ensure_page())
    assert [e for e in log if e[0] == "connect"].__len__() == 2


def _search(monkeypatch, chromium):
    from search import browser
    mod = types.ModuleType("playwright.async_api")

    class _Starter:
        async def start(self):
            return SimpleNamespace(chromium=chromium)

    mod.async_playwright = lambda: _Starter()
    monkeypatch.setitem(sys.modules, "playwright.async_api", mod)
    monkeypatch.setenv("BROWSER_SEARCH", "1")
    for name in ("_pw", "_ctx", "_start_lock", "_owner", "_remote_browser"):
        monkeypatch.setattr(browser, name, None)
    return browser


def test_the_search_browser_connects_remotely_and_falls_to_its_chain_when_it_cannot(monkeypatch):
    monkeypatch.setenv("ZAELAR_BROWSER_CDP_URL", "ws://[fdaa::1]:9223/s3cr3t/devtools/browser/x")
    log: list = []
    browser = _search(monkeypatch, _Chromium(log))
    assert asyncio.run(browser.ensure_started()) is True
    assert ("LAUNCH",) not in log and log[0][0] == "connect"
    log2: list = []
    browser = _search(monkeypatch, _Chromium(log2, fail_connect=True))
    assert asyncio.run(browser.ensure_started()) is False
    assert ("LAUNCH",) not in log2


def test_the_boot_prewarm_takes_no_remote_browser(monkeypatch):
    monkeypatch.setenv("ZAELAR_BROWSER_LEASE", "1")
    from nucleo.llm import prewarm
    called = []
    fake = types.ModuleType("search.browser")

    async def _ensure():
        called.append(1)
        return True

    fake.ensure_started = _ensure
    monkeypatch.setitem(sys.modules, "search.browser", fake)
    monkeypatch.setattr(prewarm, "_emit_prewarm", lambda *a, **k: None)
    asyncio.run(prewarm._warm_browser())
    assert called == []


def test_the_lease_is_reused_renewed_only_when_used_and_a_refusal_is_named(monkeypatch):
    monkeypatch.setenv("ZAELAR_BROWSER_LEASE", "1")
    calls: list = []
    now = [1000.0]
    monkeypatch.setattr(rb.time, "time", lambda: now[0])

    async def post(path, body, timeout):
        calls.append(path)
        if path == rb.LEASE_PATH:
            return 200, {"ok": True, "machine_id": "m1", "cdp_url": "http://[fdaa::2]:9223/abc",
                         "expires_at": now[0] + rb.LEASE_TTL_S}
        if path == rb.RENEW_PATH:
            return 200, {"ok": True, "expires_at": now[0] + rb.LEASE_TTL_S}
        return 200, {"ok": True}

    monkeypatch.setattr(rb, "_post", post)
    assert asyncio.run(rb.endpoint()) == "http://[fdaa::2]:9223/abc"
    assert asyncio.run(rb.endpoint()) == "http://[fdaa::2]:9223/abc"
    assert calls == [rb.LEASE_PATH], "a live lease is reused"
    now[0] += rb.LEASE_TTL_S * 0.6                      # past half, but NOT used since: no renewal
    asyncio.run(rb.endpoint())
    assert calls == [rb.LEASE_PATH]
    rb.touch()
    asyncio.run(rb.endpoint())
    assert calls == [rb.LEASE_PATH, rb.RENEW_PATH], "used and past half: renewed"

    async def refuse(path, body, timeout):
        return 503, {"ok": False, "error": "no_browser"}

    monkeypatch.setattr(rb, "_lease", {})
    monkeypatch.setattr(rb, "_post", refuse)
    with pytest.raises(rb.RemoteBrowserUnavailable, match="no_browser"):
        asyncio.run(rb.endpoint())

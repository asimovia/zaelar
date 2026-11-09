"""The engine's own Chromium — the navigator's (`owner_page._ensure_page`) and the search one (`search/browser.py`) —
launches with `--proxy-server=<the local forwarder>` ONLY while his tunnel is up (V2-836); with no tunnel the launch
arguments are exactly the ones it always had, and the direct fetch carries no proxy.

The launch is driven for real up to Playwright, which is a recording fake: the test reads the args each launch was
given. Both launches still pass through the worker envelope (`room_for`).
Disarm (seen red 2026-11-09): `link.launch_args()` returning the proxy whether or not a tunnel is up → the «no tunnel»
cases red.
"""
from __future__ import annotations

import asyncio

import pytest


class _Ctx:
    def __init__(self, args):
        self.args = args
        self.pages: list = []

    async def add_init_script(self, *_a, **_k):
        return None

    async def add_cookies(self, *_a, **_k):
        return None

    def set_default_navigation_timeout(self, *_a):
        return None

    def set_default_timeout(self, *_a):
        return None

    def on(self, *_a, **_k):
        return None

    async def new_page(self):
        class P:
            async def goto(self, *a, **k):
                return None

            async def close(self):
                return None

            def is_closed(self):
                return False

            def on(self, *a, **k):
                return None
        return P()

    async def close(self):
        return None


class _PW:
    def __init__(self):
        self.launched: list = []

        class Chromium:
            async def launch_persistent_context(_s, _profile, **kw):
                ctx = _Ctx(list(kw.get("args") or []))
                self.launched.append(ctx.args)
                return ctx
        self.chromium = Chromium()

    async def stop(self):
        return None


@pytest.fixture
def tunnel(monkeypatch):
    from nucleo.daemon_egress import link
    link.reset_for_tests()
    state = {"url": None}
    monkeypatch.setattr(link, "proxy_url", lambda: state["url"])
    from search import hooks
    monkeypatch.setattr(hooks, "proxy", lambda: state["url"])   # the seam the engine wires at boot
    yield state
    link.reset_for_tests()


def test_link_launch_args_follow_the_tunnel(tunnel):
    from nucleo.daemon_egress import link
    assert link.launch_args() == []
    tunnel["url"] = "http://127.0.0.1:40123"
    assert link.launch_args() == ["--proxy-server=http://127.0.0.1:40123"]


@pytest.mark.parametrize("up", [False, True])
def test_the_navigator_launch_carries_the_proxy_only_when_up(tunnel, monkeypatch, up):
    from widgets.navegador import owner as _o, owner_page
    if up:
        tunnel["url"] = "http://127.0.0.1:40123"
    pw = _PW()
    monkeypatch.setattr(_o, "_pw", pw)
    monkeypatch.setattr(_o, "_context", None)
    monkeypatch.setattr(_o, "_page", None)
    monkeypatch.setattr(_o, "_headless", lambda: True)
    monkeypatch.setattr(_o, "_remote_port", lambda: 0)
    monkeypatch.setattr(owner_page, "_apply_imported_sessions", lambda ctx: asyncio.sleep(0))
    from widgets.navegador import page_outcome
    monkeypatch.setattr(page_outcome, "attach", lambda ctx: None)
    asyncio.run(owner_page._ensure_page())
    args = pw.launched[0]
    proxies = [a for a in args if a.startswith("--proxy-server")]
    assert proxies == (["--proxy-server=http://127.0.0.1:40123"] if up else [])
    assert [a for a in args if not a.startswith("--proxy-server")] == list(_o._LAUNCH_ARGS), "nothing else changed"


@pytest.mark.parametrize("up", [False, True])
def test_the_search_launch_carries_the_proxy_only_when_up(tunnel, monkeypatch, tmp_path, up):
    import playwright.async_api as pa

    from search import browser as sb
    if up:
        tunnel["url"] = "http://127.0.0.1:40123"
    pw = _PW()

    class _Starter:
        async def start(self):
            return pw
    monkeypatch.setattr(pa, "async_playwright", lambda: _Starter())
    monkeypatch.setattr(sb, "_PROFILE", str(tmp_path / "profile"))
    monkeypatch.setattr(sb, "_ctx", None)
    monkeypatch.setattr(sb, "_pw", None)
    monkeypatch.setattr(sb, "_owner", None)
    monkeypatch.setattr(sb, "_launched_proxy", [None])
    monkeypatch.setattr(sb, "_start_lock", sb._start_lock)
    monkeypatch.setattr(sb, "_dismiss_consent", lambda page: asyncio.sleep(0))
    monkeypatch.setattr(sb, "enabled", lambda: True)
    assert asyncio.run(sb.ensure_started())
    proxies = [a for a in pw.launched[0] if a.startswith("--proxy-server")]
    assert proxies == (["--proxy-server=http://127.0.0.1:40123"] if up else [])
    assert pw.launched[0][:3] == ["--no-sandbox", "--disable-blink-features=AutomationControlled",
                                  "--disable-dev-shm-usage"]

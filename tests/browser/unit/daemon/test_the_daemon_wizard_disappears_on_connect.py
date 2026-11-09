"""The daemon's setup screen renders both states and disappears on connect (V2-575 P1), RENDERED.

Opened while the computer is not connected, the full-screen wizard shows the «connect» screen; the moment the daemon
answers WITH a folder already granted it closes by itself. If it connects with no folder granted yet, it stays — on the
permission step, which is the one thing left to do — and says whether a sign-in window can open on this computer (P2's
measured `browser.auth` capability).

Rendered in Chromium against the real DaemonSetup, store, stylesheets and Spanish bundle, with `/api/daemon/status`
answered by the test. Disarm: the close-on-connect effect removed → the first test turns red.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
_ES = json.loads((ENGINE / "i18n/genesis/es/ui.json").read_text(encoding="utf-8"))

pytest.importorskip("playwright.sync_api")

_ABSENT = {"ok": True, "local": True, "installed": False, "reachable": False, "running": False, "state": "off",
           "capabilities": [], "roots": [], "candidates": [], "platform": "macos", "downloads": {"platforms": {}}}
_WITH_FOLDER = {**_ABSENT, "installed": True, "reachable": True, "running": True, "state": "ok",
                "capabilities": ["files.list", "files.read", "files.search"], "roots": ["/Users/x/Documents"]}
_NO_FOLDER = {**_WITH_FOLDER, "state": "warn", "roots": [],
              "capabilities": ["files.list", "files.read", "files.search", "browser.auth"]}

_CSS = """for (const h of ['/frontend/app/core/palette.css', '/frontend/app/core/shared-surfaces.css',
                       '/frontend/app/core/components.css', '/frontend/app/styles.css']) {
            const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
          const i18n = await import('/frontend/app/core/i18n.js?v=1');
          await i18n.loadBundle('es'); if (i18n.applyLang) await i18n.applyLang('es');"""

_MOUNT = "async () => {" + _CSS + """
    const store = await import('/frontend/app/core/store.js?v=2');
    const m = await import('/frontend/app/components/DaemonSetup.js?v=1');
    document.body.append(m.DaemonSetup());
    store.setDaemonSetupOpen(true);
    const d = await import('/frontend/app/services/daemon.js?v=3'); await d.check(); }"""

_READ = """() => { const o = document.querySelector('.dsx-ovl');
    return {open: o.classList.contains('on'), lead: (o.querySelector('.dsx-lead') || {}).innerText || '',
            cap: (o.querySelector('.dsx-cap') || {}).innerText || '',
            folders: !!o.querySelector('.dsx-folders'),
            visible: getComputedStyle(o).display !== 'none' && getComputedStyle(o).visibility !== 'hidden'}; }"""


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def server():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    yield port
    srv.terminate(); srv.wait(timeout=10)


def _page(pw, port, status: dict):
    pg = pw.chromium.launch().new_page(viewport={"width": 1280, "height": 800})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/daemon/status", lambda r: r.fulfill(status=200, content_type="application/json",
                                                         body=json.dumps(status["now"])))
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                         body=json.dumps({"strings": _ES})))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg._errors = errors
    return pg


def _recheck(pg):
    pg.evaluate("async () => { const d = await import('/frontend/app/services/daemon.js?v=3'); await d.check(); }")


def test_the_wizard_shows_connect_then_closes_itself_when_the_daemon_answers(server):
    from playwright.sync_api import sync_playwright
    status = {"now": _ABSENT}
    with sync_playwright() as pw:
        pg = _page(pw, server, status)
        pg.evaluate(_MOUNT)
        pg.wait_for_selector(".dsx-ovl.on .dsx-lead", timeout=5000)
        r = pg.evaluate(_READ)
        assert r["open"] and r["lead"] == _ES["daemon.local.lead"], f"not connected → the connect screen: {r}"
        status["now"] = _WITH_FOLDER
        _recheck(pg)
        until_sync(lambda: not pg.evaluate(_READ)["open"], "the wizard to close on connect", timeout_s=5)
        assert not pg._errors, pg._errors


def test_connected_with_no_folder_it_stays_on_the_permission_step(server):
    from playwright.sync_api import sync_playwright
    status = {"now": _ABSENT}
    with sync_playwright() as pw:
        pg = _page(pw, server, status)
        pg.evaluate(_MOUNT)
        pg.wait_for_selector(".dsx-ovl.on .dsx-lead", timeout=5000)
        status["now"] = _NO_FOLDER
        _recheck(pg)
        pg.wait_for_selector(".dsx-ovl.on .dsx-folders", timeout=5000)
        r = pg.evaluate(_READ)
        assert r["open"] and r["folders"] and r["lead"] == _ES["daemon.ok.lead"], f"stays on the folder step: {r}"
        assert r["cap"] == _ES["daemon.cap.browser_on"], f"the measured sign-in capability is said: {r['cap']!r}"
        assert not pg._errors, pg._errors


def test_reopened_while_connected_it_stays_open(server):
    """Closing on connect is a TRANSITION, not a state: opened to change folders, it must not vanish."""
    from playwright.sync_api import sync_playwright
    status = {"now": {**_WITH_FOLDER, "capabilities": ["files.list"]}}
    with sync_playwright() as pw:
        pg = _page(pw, server, status)
        pg.evaluate(_MOUNT)
        pg.wait_for_selector(".dsx-ovl.on .dsx-folders", timeout=5000)
        _recheck(pg)
        r = pg.evaluate(_READ)
        assert r["open"] and r["cap"] == _ES["daemon.cap.browser_off"], r
        assert not pg._errors, pg._errors

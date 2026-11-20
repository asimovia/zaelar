"""The chat wall tells the observability timeline whether it is open and on which tab. Rendered.

A session replay draws the operator's screen at every step from the timeline alone. The left column was missing
from it: `orb:chat` covered only the orb's own button, so a column opened from the bar, a tab switched by a click or
by the engine's push, or the column restored on load left no trace. Now every CHANGE of (open, tab) is one
`wall:state` ui-event: the first (the mount restoring it) as a client state transition (`src=frontend`), the later
ones as what moved it. Rendered against the real ChatWall and store in Chromium, reading the requests it sends.

Disarm: drop the report effect → no `wall:state` request → red.
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
_EN = json.loads((ENGINE / "i18n/genesis/en/ui.json").read_text(encoding="utf-8"))

pytest.importorskip("playwright.sync_api")


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def browser_and_port():
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            yield b, port
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _pump(pg, cond, what: str, timeout_ms: int = 5000):
    """Wait while the page runs: the sync API hands the routed requests over only while it is pumped."""
    for _ in range(timeout_ms // 100):
        if cond():
            return
        pg.wait_for_timeout(100)
    raise AssertionError(f"waited {timeout_ms} ms for {what} and it never happened")


def _wall_reports(sent: list) -> list:
    return [(b.get("state"), b.get("detail"), b.get("src", "user")) for b in sent if b.get("action") == "wall:state"]


def test_every_change_of_the_column_is_one_report(browser_and_port):
    b, port = browser_and_port
    pg = b.new_page(viewport={"width": 1280, "height": 800})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    sent: list = []

    def _api(route):
        if route.request.url.endswith("/api/ui-event"):
            sent.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json", body="{}")
    pg.route("**/api/**", _api)
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"strings": _EN})))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async () => {
        localStorage.clear();
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle('en'); if (i18n.applyLang) await i18n.applyLang('en');
        const store = await import('/frontend/app/core/store.js?v=2');
        const wall = await import('/frontend/app/components/ChatWall.js?v=6');
        document.body.append(wall.ChatWall());
        window.__store = store;
    }""")
    pg.wait_for_selector("#chatwall", state="attached", timeout=5000)
    _pump(pg, lambda: _wall_reports(sent), "the mount's report")
    assert _wall_reports(sent) == [("closed", "chat", "frontend")], "the mount reports the restored state, once"

    pg.evaluate("() => window.__store.setChatOpen(true)")
    pg.evaluate("() => window.__store.setChatTab('procesos')")
    pg.evaluate("() => window.__store.setChatTab('procesos')")          # the same tab again is no change
    pg.evaluate("() => window.__store.setChatOpen(false)")
    _pump(pg, lambda: len(_wall_reports(sent)) >= 4, "the three changes")
    assert _wall_reports(sent) == [("closed", "chat", "frontend"), ("open", "chat", "user"),
                                   ("open", "procesos", "user"), ("closed", "procesos", "user")]
    assert not errors, errors
    pg.close()

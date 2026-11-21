"""Opening the chat wall lands on the LATEST message, not on the top of the history. Rendered.

A line appended to the wall follows the end when the list is at the bottom — but a list written while the wall is
closed has no height, so the follow did nothing and the wall opened scrolled to the top of a long history. The pin
also runs when the list becomes visible: on open, and on coming back to the Chat tab. The lines are written through
the engine's `wall` events, as the stream brings them (INI-042 #49).
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


def _page(browser, port):
    pg = browser.new_page(viewport={"width": 1280, "height": 800})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"strings": _EN})))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async () => {
        localStorage.clear();
        for (const h of ['/frontend/app/core/palette.css', '/frontend/app/styles.css']) {
          const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle('en'); if (i18n.applyLang) await i18n.applyLang('en');
        const store = await import('/frontend/app/core/store.js?v=2');
        const wall = await import('/frontend/app/components/ChatWall.js?v=5');
        const { routeWall } = await import('/frontend/app/services/wall-bridge.js?v=1');
        let n = 0;   // the engine's lines, as its `wall` events bring them: his by the keyboard, ours by the mouth
        window.__line = (role, text) => routeWall({ kind: 'wall', writer: role === 'you' ? 'keyboard:t' : 'mouth',
                                                    op: { op: 'append', id: 'l' + (++n), role, state: 'final', text } });
        window.__route = routeWall;
        document.body.append(wall.ChatWall());
        window.__store = store;
    }""")
    pg.wait_for_selector("#chatwall", state="attached", timeout=5000)
    pg._errors = errors
    return pg


def _at_bottom(pg) -> bool:
    return pg.evaluate("""() => { const l = document.querySelector('#chatwall .cw-list');
        return l.scrollHeight > l.clientHeight && l.scrollHeight - l.clientHeight - l.scrollTop < 4; }""")


def test_a_history_written_while_closed_opens_on_its_last_line(browser_and_port):
    b, port = browser_and_port
    pg = _page(b, port)
    # The history arrives while the wall is CLOSED — what a reload or a restored session does.
    pg.evaluate("""() => { for (let i = 0; i < 60; i++) { const text = 'line ' + i + ' ' + 'word '.repeat(12);
        window.__line(i % 2 ? 'agent' : 'you', text); } }""")
    pg.evaluate("() => window.__store.openChatFrom('orb')")
    pg.wait_for_selector("#chatwall.open", timeout=5000)
    until_sync(lambda: _at_bottom(pg), "the open wall to show its latest message", timeout_s=5)
    assert not pg._errors, pg._errors
    pg.close()


def test_coming_back_to_the_chat_tab_lands_on_the_last_line(browser_and_port):
    b, port = browser_and_port
    pg = _page(b, port)
    pg.evaluate("() => { window.__store.openChatFrom('orb'); window.__store.setChatTab('processes'); }")
    pg.evaluate("""() => { for (let i = 0; i < 60; i++)
        window.__line('agent', 'line ' + i + ' ' + 'word '.repeat(12)); }""")
    pg.evaluate("() => window.__store.setChatTab('chat')")
    until_sync(lambda: _at_bottom(pg), "the Chat tab to show its latest message", timeout_s=5)
    pg.close()

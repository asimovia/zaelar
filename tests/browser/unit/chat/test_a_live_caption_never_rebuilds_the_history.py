"""A live caption never rebuilds the history: his partials and the agent's crawl only write their own text. Rendered.

Measured 2026-11-18: every interim re-rendered up to 100 rows of markdown and forced a layout (p50 6.6 ms, p90 13,
worst 84-173 ms on a loaded host), so the caption stuttered exactly when the machine was busy. Now the history rows
are the SAME nodes while he speaks and while the agent's line crawls; only a committed row rebuilds the list.

Disarm (seen red): `store.liveChat()` read again inside the history effect → the rows are rebuilt per partial.
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
        document.body.append(wall.ChatWall());
        window.__store = store;
    }""")
    pg.wait_for_selector("#chatwall", state="attached", timeout=5000)
    pg._errors = errors
    return pg


def _at_bottom(pg) -> bool:
    return pg.evaluate("""() => { const l = document.querySelector('#chatwall .cw-list');
        return l.scrollHeight > l.clientHeight && l.scrollHeight - l.clientHeight - l.scrollTop < 4; }""")


_ROWS = """() => window.__store.setChatMsgs(Array.from({length: 100}, (_, i) =>
    ({role: i % 2 ? 'agent' : 'you', text: 'line **' + i + '** ' + 'word '.repeat(12), at: Date.now() - (100 - i) * 1000})))"""

_FRAME = "() => new Promise(r => requestAnimationFrame(() => setTimeout(r, 0)))"


def test_his_partials_and_the_agents_crawl_leave_the_history_nodes_alone(browser_and_port):
    b, port = browser_and_port
    pg = _page(b, port)
    pg.evaluate(_ROWS)
    pg.evaluate("() => window.__store.openChatFrom('orb')")
    pg.wait_for_selector("#chatwall.open", timeout=5000)
    pg.evaluate("() => { window.__first = document.querySelector('#chatwall .cw-list .cw-msg'); }")
    for words in ("quiero", "quiero que me", "quiero que me recuerdes la cita"):
        pg.evaluate("(t) => window.__store.setLiveChat(t)", words)
        pg.evaluate(_FRAME)
        got = pg.evaluate("""() => ({
            same: document.querySelector('#chatwall .cw-list .cw-msg') === window.__first,
            live: [...document.querySelectorAll('#chatwall .cw-list .cw-live')].map(e => e.textContent),
            last: document.querySelector('#chatwall .cw-list').lastElementChild.classList.contains('cw-live') })""")
        assert got["same"], "a partial rebuilt the history"
        assert got["live"] == [words] and got["last"], got
    pg.evaluate("() => window.__store.clearLiveChat()")
    pg.evaluate(_FRAME)
    assert pg.evaluate("() => document.querySelectorAll('#chatwall .cw-live').length") == 0, "the caption outlived him"

    reply = "Te he apuntado la cita del dentista para el martes."
    pg.evaluate("""(r) => { const s = window.__store; s.pushAgentChat(r, {voiced: true, trace: 'TW'});
                           s.noteVoiceStarted('TW'); s.pushCaptionSeg('w1', 'Te he', false); }""", reply)
    pg.evaluate(_FRAME)
    pg.evaluate("() => { window.__first = document.querySelector('#chatwall .cw-list .cw-msg'); }")
    for said in ("Te he apuntado", "Te he apuntado la cita del dentista"):
        pg.evaluate("(t) => window.__store.pushCaptionSeg('w1', t, false)", said)
        pg.evaluate(_FRAME)
        got = pg.evaluate("""() => ({
            same: document.querySelector('#chatwall .cw-list .cw-msg') === window.__first,
            said: [...document.querySelectorAll('#chatwall .cw-speaking .cw-msg-body')].map(e => e.textContent) })""")
        assert got["same"], "a caption segment rebuilt the history"
        assert got["said"] == [said], got
    assert not pg._errors, pg._errors
    pg.close()

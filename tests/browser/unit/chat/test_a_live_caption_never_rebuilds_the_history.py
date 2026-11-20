"""A live caption never rebuilds the history: his partials and the agent's crawl only write their own line. Rendered.

Measured 2026-11-18: every interim re-rendered up to 100 rows of markdown and forced a layout (p50 6.6 ms, p90 13,
worst 84-173 ms on a loaded host), so the caption stuttered exactly when the machine was busy. The wall is now a
component with ONE node per line id, never rebuilt (INI-042 #49): a partial updates ONE node's text — his line in
course, the same node from his first partial on — and no other node of the wall is replaced; the agent's crawl the
same with its own line. Driven through the page's one old-path writer (`wall-legacy.js?v=1`), as `sse.js` and
`session-lk.js` drive it.

Disarm (seen red): `legacy.setLiveChat` appends a new line per partial instead of updating its own → a second node.
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
        window.__legacy = (await import('/frontend/app/services/wall-legacy.js?v=1')).legacy;
        document.body.append(wall.ChatWall());
        window.__store = store;
    }""")
    pg.wait_for_selector("#chatwall", state="attached", timeout=5000)
    pg._errors = errors
    return pg


def _at_bottom(pg) -> bool:
    return pg.evaluate("""() => { const l = document.querySelector('#chatwall .cw-list');
        return l.scrollHeight > l.clientHeight && l.scrollHeight - l.clientHeight - l.scrollTop < 4; }""")


# 90 final lines with markdown, his and ours: under the wall's cap (100), so a new line trims nothing and every node
# that leaves the DOM below left because something rebuilt it.
_ROWS = """() => { for (let i = 0; i < 90; i++) {
    const text = 'line **' + i + '** ' + 'word '.repeat(12);
    if (i % 2) window.__legacy.pushAgentChat(text); else window.__legacy.pushChat({role: 'you', text}); } }"""

_FRAME = "() => new Promise(r => requestAnimationFrame(() => setTimeout(r, 0)))"

_KEEP = "() => { window.__nodes = [...document.querySelectorAll('#chatwall .cw-list > [data-id]')]; }"

# Every node kept before is still in the list, and it is still the node for its id; the rest are new.
_SAME = """() => { const now = [...document.querySelectorAll('#chatwall .cw-list > [data-id]')];
    return { kept: window.__nodes.every(e => e.isConnected && now.includes(e)), fresh: now.filter(e => !window.__nodes.includes(e)).length,
             live: [...document.querySelectorAll('#chatwall .cw-list .cw-live')].map(e => e.textContent),
             lastLive: document.querySelector('#chatwall .cw-list').lastElementChild.classList.contains('cw-live') }; }"""


def test_his_partials_and_the_agents_crawl_leave_the_history_nodes_alone(browser_and_port):
    b, port = browser_and_port
    pg = _page(b, port)
    pg.evaluate(_ROWS)
    pg.evaluate("() => window.__store.openChatFrom('orb')")
    pg.wait_for_selector("#chatwall.open", timeout=5000)
    until_sync(lambda: pg.evaluate("() => document.querySelectorAll('#chatwall .cw-list .cw-msg').length") == 90,
               "the history on the wall")
    pg.evaluate(_KEEP)
    caption = None
    for words in ("quiero", "quiero que me", "quiero que me recuerdes la cita"):
        pg.evaluate("(t) => window.__legacy.setLiveChat(t)", words)
        pg.evaluate(_FRAME)
        got = pg.evaluate(_SAME)
        assert got["kept"], "a partial replaced a node of the history"
        assert got["fresh"] == 1, f"his line in course is ONE node, from his first partial on: {got}"
        assert got["live"] == [words] and got["lastLive"], got
        node = pg.evaluate_handle("() => document.querySelector('#chatwall .cw-list .cw-live')")
        if caption is None:
            caption = node
        else:
            assert pg.evaluate("([a, b]) => a === b", [caption, node]), "a partial replaced his line's own node"
    pg.evaluate("() => window.__legacy.clearLiveChat()")
    pg.evaluate(_FRAME)
    assert pg.evaluate("() => document.querySelectorAll('#chatwall .cw-live').length") == 0, "the caption outlived him"
    assert pg.evaluate(_SAME)["kept"], "clearing his caption touched the history"

    reply = "Te he apuntado la cita del dentista para el martes."
    pg.evaluate("""(r) => { const l = window.__legacy; l.pushAgentChat(r, {voiced: true, trace: 'TW'});
                           l.noteVoiceStarted('TW'); l.noteSpokenAloud('Te he', false); }""", reply)
    pg.evaluate(_FRAME)
    pg.evaluate(_KEEP)
    speaking = pg.evaluate_handle("() => document.querySelector('#chatwall .cw-list .cw-speaking')")
    for said in ("Te he apuntado", "Te he apuntado la cita del dentista"):
        pg.evaluate("(t) => window.__legacy.noteSpokenAloud(t, false)", said)
        pg.evaluate(_FRAME)
        got = pg.evaluate("""(sp) => ({
            kept: window.__nodes.every(e => e.isConnected),
            count: document.querySelectorAll('#chatwall .cw-list > [data-id]').length === window.__nodes.length,
            same: document.querySelector('#chatwall .cw-list .cw-speaking') === sp,
            said: [...document.querySelectorAll('#chatwall .cw-speaking .cw-msg-body')].map(e => e.textContent) })""",
            speaking)
        assert got["kept"] and got["count"], "a caption segment replaced a node of the wall"
        assert got["same"], "the crawl replaced its own line's node"
        assert got["said"] == [said], got
    assert not pg._errors, pg._errors
    pg.close()

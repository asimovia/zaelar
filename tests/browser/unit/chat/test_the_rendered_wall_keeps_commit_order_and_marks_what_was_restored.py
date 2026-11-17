"""The chat wall, RENDERED, in the order things were committed — and the «earlier» divider after the restored rows.

Operator's rule (2026-11-17): every bubble is stamped at the moment it is committed (his words when final, the
agent's line when the voice starts it) and the wall shows them in that order. That day his bubble landed BELOW the
agent's reply to it: the gate's directed verdict arrived 24–90 ms BEFORE his final transcript, and the client
dropped a verdict that found nothing held. This replays that exact event order through the production router
(`sse.routeEvent`) into the real store and the real ChatWall in Chromium, and reads the DOM.

The same day's screenshot showed the «earlier, N min ago» divider at the very END of a live conversation: with a
restored history at the 100-row cap, the wall counted restored rows and could not see the cap trim them, so the
divider stuck to the end for good. The store now flags each restored row and the divider follows the last one.
The .mjs twin (`test_the_wall_is_in_the_order_things_were_committed.mjs`) covers the hold and the insert door.
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

READ = """() => [...document.querySelectorAll('#chatwall .cw-list > *')].map(e =>
    e.classList.contains('cw-earlier') ? '--' : (e.classList.contains('agent') ? 'Z: ' : 'H: ')
      + (e.textContent || '').trim())"""


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


def _page(browser, port, seed=None):
    """The wall mounted with the real store and router. `seed` is a stored history, written BEFORE the store loads —
    which is what a reload is."""
    pg = browser.new_page(viewport={"width": 1280, "height": 800})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"strings": _EN})))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async (seed) => {
        localStorage.clear();
        if (seed) localStorage.setItem('hb_chat_log', JSON.stringify(seed));
        for (const h of ['/frontend/app/core/palette.css', '/frontend/app/styles.css']) {
          const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle('en'); if (i18n.applyLang) await i18n.applyLang('en');
        const store = await import('/frontend/app/core/store.js?v=2');
        const wall = await import('/frontend/app/components/ChatWall.js?v=5');
        window.__sse = await import('/frontend/app/services/sse.js?v=2');
        document.body.append(wall.ChatWall());
        window.__store = store;
        store.setAttentionMode('smart');            // there IS a gate: every spoken turn waits for its verdict
        store.openChatFrom('orb'); store.setChatTab('chat');
    }""", seed)
    pg.wait_for_selector("#chatwall.open", timeout=5000)
    pg._errors = errors
    return pg


def _route(pg, *events):
    pg.evaluate("(evs) => evs.forEach(d => window.__sse.routeEvent(null, d))", list(events))


@pytest.mark.parametrize("lang,a,r1,b,r2", [
    ("en", "Show me tomorrow's agenda", "Here it is.", "And when is the first one?", "At nine."),
    ("es", "Ponme la agenda de mañana", "Ahí la tienes.", "¿Y a qué hora es la primera?", "A las nueve."),
])
def test_a_verdict_that_arrives_before_his_words_still_paints_them_first(browser_and_port, lang, a, r1, b, r2):
    br, port = browser_and_port
    pg = _page(br, port)
    t0 = pg.evaluate("() => Date.now()")
    verdict = {"kind": "ambient", "label": "👂 dirigido a zaelar", "directed": True, "reason": "active_window",
               "window_s": 12}
    # the measured order: the verdict 50 ms BEFORE the final transcript
    _route(pg, {**verdict, "t_ms": t0}, {"kind": "transcript", "label": "transcript", "role": "user", "text": a,
                                         "t_ms": t0 + 50})
    until_sync(lambda: pg.evaluate(READ) == ["H: " + a], f"[{lang}] his line painted as soon as it is final")
    _route(pg, {"kind": "brain", "label": "🧠 reply", "role": "assistant", "text": r1, "trace": "T1", "t_ms": t0 + 1500},
           {"kind": "bot_speech", "label": "speaking", "speaking": True, "trace": "T1", "t_ms": t0 + 2000},
           {"kind": "bot_speech", "label": "idle", "speaking": False, "t_ms": t0 + 4000},
           # the next turn, in the usual order this time
           {"kind": "transcript", "label": "transcript", "role": "user", "text": b, "t_ms": t0 + 9000},
           {**verdict, "t_ms": t0 + 9070},
           {"kind": "brain", "label": "🧠 reply", "role": "assistant", "text": r2, "trace": "T2", "t_ms": t0 + 10500},
           {"kind": "bot_speech", "label": "speaking", "speaking": True, "trace": "T2", "t_ms": t0 + 11000},
           {"kind": "bot_speech", "label": "idle", "speaking": False, "t_ms": t0 + 12000})
    until_sync(lambda: pg.evaluate(READ) == ["H: " + a, "Z: " + r1, "H: " + b, "Z: " + r2],
               f"[{lang}] the wall in commit order: {pg.evaluate(READ)}")
    # the stamp is kept where the history is kept
    until_sync(lambda: [m.get("at") for m in json.loads(pg.evaluate(
        "() => localStorage.getItem('hb_chat_log') || '{\"msgs\":[]}'"))["msgs"]]
        == [t0 + 50, t0 + 2000, t0 + 9000, t0 + 11000], "the persisted rows carry their commit stamps")
    assert not pg._errors, pg._errors
    pg.close()


def test_the_divider_follows_the_restored_rows_at_the_cap(browser_and_port):
    br, port = browser_and_port
    old = [{"role": "you" if i % 2 else "agent", "text": f"old {i}", "at": 1_700_000_000_000 + i} for i in range(100)]
    pg = _page(br, port, seed={"v": 1, "at": 1_700_000_100_000, "msgs": old})
    until_sync(lambda: len(pg.evaluate(READ)) == 101, "the restored wall")
    assert pg.evaluate(READ)[-1] == "--", "a wall that is ALL restored closes with the divider"
    pg.evaluate("() => window.__store.pushChat({ role: 'you', text: 'new 1' })")
    until_sync(lambda: pg.evaluate(READ)[-1] == "H: new 1", "the new line")
    rows = pg.evaluate(READ)
    assert rows.index("--") == 99 and rows[98] == "H: old 99", rows[95:]
    assert rows[100:] == ["H: new 1"], "at the cap, the divider sits after the restored rows, not at the end"
    pg.evaluate("() => window.__store.pushChat({ role: 'agent', text: 'new 2' })")
    until_sync(lambda: pg.evaluate(READ)[-1] == "Z: new 2", "the second new line")
    rows = pg.evaluate(READ)
    assert rows.index("--") == 98 and rows[99:] == ["H: new 1", "Z: new 2"], rows[95:]
    assert not pg._errors, pg._errors
    pg.close()

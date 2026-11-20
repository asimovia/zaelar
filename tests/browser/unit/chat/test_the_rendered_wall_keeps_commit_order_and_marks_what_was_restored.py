"""The chat wall, RENDERED, in order — and ONE «earlier» divider after the restored lines.

Operator's complaint (2026-11-17): his bubble landed BELOW the agent's reply to it: the gate's directed verdict arrived
24–90 ms BEFORE his final transcript, and the client dropped a verdict that found nothing held. This replays that exact
event order through the production router (`sse.routeEvent`) into the real old-path writer (`wall-legacy.js`), the real
chat wall component and the real ChatWall in Chromium, and reads the DOM. The order rule is the wall plan's §5.1 (a
line's place is where it STARTS: his at his first words, ours at its voice's start; nothing is inserted by time) — what
stays pinned is the complaint: his line above the reply it caused.

The same day's screenshot showed the «earlier, N min ago» divider at the very END of a live conversation. The wall now
restores the final lines kept in `wall-storage.js` (`hb_wall_lines`; the old `hb_chat_log` is migrated ONCE), marks
each restored line (`cw-restored`) and puts ONE divider after them, where it stays while the cap trims the oldest.
The .mjs twin (`test_the_wall_is_in_the_order_things_were_committed.mjs`) covers the hold and the old path's writer.
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
    """The wall mounted with the real store, router and old-path writer. `seed` ({key, body}) is a stored history,
    written BEFORE the wall mounts — which is what a reload is."""
    pg = browser.new_page(viewport={"width": 1280, "height": 800})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"strings": _EN})))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async (seed) => {
        localStorage.clear();
        if (seed) localStorage.setItem(seed.key, JSON.stringify(seed.body));
        for (const h of ['/frontend/app/core/palette.css', '/frontend/app/styles.css']) {
          const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle('en'); if (i18n.applyLang) await i18n.applyLang('en');
        const store = await import('/frontend/app/core/store.js?v=2');
        const wall = await import('/frontend/app/components/ChatWall.js?v=5');
        window.__sse = await import('/frontend/app/services/sse.js?v=2');
        // the page's ONE old-path writer: the same URL every importer names (a different ?v= is a second instance)
        window.__legacy = (await import('/frontend/app/services/wall-legacy.js?v=1')).legacy;
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
    # the stamp is kept where the history is kept (`wall-storage.js`: final lines only)
    until_sync(lambda: [m.get("at") for m in json.loads(pg.evaluate(
        "() => localStorage.getItem('hb_wall_lines') || '{\"lines\":[]}'"))["lines"]]
        == [t0 + 50, t0 + 2000, t0 + 9000, t0 + 11000], "the persisted lines carry their commit stamps")
    # our replies name the line of his they answer, which stands above them
    ids = pg.evaluate("() => [...document.querySelectorAll('#chatwall .cw-list > [data-id]')].map(e => e.dataset.id)")
    kept = json.loads(pg.evaluate("() => localStorage.getItem('hb_wall_lines')"))["lines"]
    assert [k["id"] for k in kept] == ids, (kept, ids)
    assert kept[1]["re"] == [ids[0]] and kept[3]["re"] == [ids[2]], kept
    assert not pg._errors, pg._errors
    pg.close()


RESTORED = """() => [...document.querySelectorAll('#chatwall .cw-list > [data-id]')]
    .filter(e => e.classList.contains('cw-restored')).length"""


def test_the_divider_follows_the_restored_rows_at_the_cap(browser_and_port):
    br, port = browser_and_port
    old = [{"role": "you" if i % 2 else "agent", "text": f"old {i}", "at": 1_700_000_000_000 + i} for i in range(100)]
    # the old wall's key: migrated ONCE into the component's own store, every row a final line in its place
    pg = _page(br, port, seed={"key": "hb_chat_log", "body": {"v": 1, "at": 1_700_000_100_000, "msgs": old}})
    until_sync(lambda: len(pg.evaluate(READ)) == 101, "the restored wall")
    rows = pg.evaluate(READ)
    assert rows[-1] == "--" and rows.count("--") == 1, "a wall that is ALL restored closes with ONE divider"
    assert rows[:2] == ["Z: old 0", "H: old 1"] and rows[99] == "H: old 99", "restored in their order"
    assert pg.evaluate(RESTORED) == 100, "every restored line is marked as restored"
    assert pg.evaluate("() => localStorage.getItem('hb_chat_log')") is None, "the old key is migrated once and removed"
    kept = json.loads(pg.evaluate("() => localStorage.getItem('hb_wall_lines')"))["lines"]
    assert len(kept) == 100 and all(k["state"] == "final" for k in kept), "migrated as final lines"
    pg.evaluate("() => window.__legacy.pushChat({ role: 'you', text: 'new 1' })")
    until_sync(lambda: pg.evaluate(READ)[-1] == "H: new 1", "the new line")
    rows = pg.evaluate(READ)
    assert rows.index("--") == 99 and rows[98] == "H: old 99", rows[95:]
    assert rows[100:] == ["H: new 1"], "at the cap, the divider sits after the restored rows, not at the end"
    pg.evaluate("() => window.__legacy.pushChat({ role: 'agent', text: 'new 2' })")
    until_sync(lambda: pg.evaluate(READ)[-1] == "Z: new 2", "the second new line")
    rows = pg.evaluate(READ)
    assert rows.index("--") == 98 and rows[99:] == ["H: new 1", "Z: new 2"], rows[95:]
    assert rows.count("--") == 1, "still ONE divider"
    assert pg.evaluate(RESTORED) == 98, "the new lines are not marked restored; the cap trimmed two restored ones"
    assert not pg._errors, pg._errors
    pg.close()


def test_a_reload_restores_the_final_lines_once_with_one_divider(browser_and_port):
    """The component's own key: what was final comes back, in order, once; nothing live does."""
    br, port = browser_and_port
    lines = [{"id": f"l{i}", "owner": "legacy:you" if i % 2 else "legacy:agent", "role": "you" if i % 2 else "agent",
              "state": "final", "text": f"kept {i}", "at": 1_700_000_000_000 + i} for i in range(4)]
    lines.append({"id": "l_live", "owner": "legacy:you", "role": "you", "state": "live", "text": "half said"})
    pg = _page(br, port, seed={"key": "hb_wall_lines", "body": {"v": 2, "at": 1_700_000_100_000, "lines": lines}})
    until_sync(lambda: len(pg.evaluate(READ)) == 5, "the restored wall")
    assert pg.evaluate(READ) == ["Z: kept 0", "H: kept 1", "Z: kept 2", "H: kept 3", "--"], pg.evaluate(READ)
    assert pg.evaluate(RESTORED) == 4
    assert not pg._errors, pg._errors
    pg.close()

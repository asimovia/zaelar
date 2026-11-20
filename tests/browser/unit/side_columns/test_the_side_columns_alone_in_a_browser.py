"""The Connectors and Network columns work ALONE, in a real browser (INI-042 #49).

A blank page that loads only `frontend/side/<column>/` — no app, no store, no engine — mounts each column through
`mount(host, bridge)` with a bridge fed real-shaped data (the registry's descriptors with Google grouped as one row,
the catalog's wishlist, one `GET /api/a2a/network` answer) and the real English words, and reads what is PAINTED:

  · Connectors: families in his order, Google's count of services, «Connect» hands the id to the credential surface,
    the wishlist folded below, «I want it» sent ONCE, a not-possible entry with no button and its reason; an empty
    read is retried while shown and never once hidden;
  · Network: nothing while A2A is off, the four blocks once on, a card's Yes is one answer and the card says so, ✕
    stops sharing that item, and off again empties the body; `show()` re-reads.

Disarms: «I want it» not guarded → sent twice (red); `hide()` not cancelling the retry → a read while hidden (red);
the Network column drawing while off → a body with A2A off (red)."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
EN = json.loads((ENGINE / "i18n/genesis/en/ui.json").read_text(encoding="utf-8"))

pytest.importorskip("playwright.sync_api")

LIVE = [{"id": "google", "label": "Google", "family": "google", "connected": True,
         "services": [{"id": "gmail", "connected": True}, {"id": "gcal", "connected": False}, {"id": "gdrive", "connected": True}]},
        {"id": "zfam", "label": "Odd one", "family": "zeta", "connected": False},
        {"id": "telegram", "label": "Telegram", "family": "mensajeria", "connected": False},
        {"id": "spotify", "label": "Spotify", "family": "musica", "connected": True}]
WISH = [{"id": "slack", "label": "Slack", "family": "mensajeria", "state": "planned"},
        {"id": "icloud_drive", "label": "iCloud Drive", "family": "archivos", "state": "not-possible",
         "why-not": "CloudKit only gives the app's own container"}]
NET = {"relationships": [{"rel": "r1", "cid": "marta", "name": "Marta", "status": "accepted", "peer": "abcd1234",
                          "grants": [{"item": "calendar", "verbs": ["see"], "expires_at": None}]}],
       "cards": [{"id": "c9", "type": "request", "name": "Pepe", "status": "pending"}],
       "recent": [{"op": "query", "cid": "marta", "dir": "in", "ok": True, "label": "freebusy", "item": "calendar"}],
       "items": []}

PAGE = """async ([dict, live, wish]) => {
  document.body.innerHTML = '<div id="conn" style="height:600px;width:420px"></div><div id="red" style="width:420px"></div>';
  const t = (k, p) => { let s = dict[k] ?? k; for (const x in (p || {})) s = s.split('{' + x + '}').join(String(p[x])); return s; };
  const seen = { loads: 0, manage: [], want: [], answer: [], revoke: [], refresh: 0 };
  window.__seen = seen; window.__data = { live, wish }; window.__net = null; window.__redraw = [];
  const conn = await import('/frontend/side/conectores/conectores.js');
  const red = await import('/frontend/side/red/red.js');
  const watch = (fn) => { window.__redraw.push(fn); fn(); return () => {}; };
  window.__conn = conn.mount(document.getElementById('conn'), { t, watch,
    load: async () => { seen.loads++; return window.__data; },
    manage: (id) => seen.manage.push(id), want: async (m) => { seen.want.push(m.id); } });
  window.__red = red.mount(document.getElementById('red'), { t, watch, network: () => window.__net,
    refresh: () => { seen.refresh++; }, answer: async (id, yes) => { seen.answer.push([id, yes]); return true; },
    revoke: (cid, item) => seen.revoke.push([cid, item]) });
}"""
TEXTS = "(sel) => [...document.querySelectorAll(sel)].map(e => e.textContent)"


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


@pytest.fixture
def page(browser_and_port):
    br, port = browser_and_port
    pg = br.new_page(viewport={"width": 600, "height": 900})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/frontend/side/red/red.css", wait_until="domcontentloaded")
    pg.evaluate(PAGE, [EN, LIVE, WISH])
    yield pg
    assert not errors, errors
    pg.close()


def test_the_connectors_column_paints_and_acts_through_its_bridge(page):
    pg = page
    assert pg.evaluate("() => [...document.scripts].length") == 0, "a blank page: nothing of the app loaded"
    assert pg.evaluate(TEXTS, "#conn .cw-empty") == [EN["chat.connEmpty"]], "before a read: the empty state"
    pg.evaluate("() => __conn.show()")
    until_sync(lambda: pg.evaluate(TEXTS, "#conn .cl-list > .cn-fam"), "the families painted")
    assert pg.evaluate(TEXTS, "#conn .cl-list > .cn-fam") == [
        "Google", EN["chat.connFamily.mensajeria"], EN["chat.connFamily.musica"], "chat.connFamily.zeta"]
    assert pg.evaluate(TEXTS, "#conn .cl-list > .cl-row .cl-meta")[0] == EN["config.cx.of_services"].replace(
        "{n}", "2").replace("{total}", "3")
    assert pg.evaluate("() => document.querySelectorAll('#conn .cl-list > .cl-row .cl-dot.on').length") == 2
    pg.click("#conn .cl-row:has-text('Telegram') .cl-b")
    assert pg.evaluate("() => __seen.manage") == ["telegram"]
    # the wishlist: folded, by family, «I want it» once, a not-possible entry with no button and its reason
    soon = pg.evaluate("() => { const d = document.querySelector('#conn details.cn-soon'); return [d.open, d.querySelector('summary').textContent]; }")
    assert soon == [False, EN["chat.connSoon"].replace("{n}", "2")]
    pg.click("#conn details.cn-soon > summary")
    want = "#conn .cn-soon .cl-row:has-text('Slack') .cl-b"
    pg.click(want)
    pg.evaluate("() => document.querySelector('#conn .cn-soon .cl-row .cl-b').onclick()")   # past the disabled button
    assert pg.evaluate("() => __seen.want") == ["slack"], "«I want it» is sent once"
    assert pg.text_content(want) == EN["chat.connWantedBtn"] and pg.is_disabled(want)
    assert pg.evaluate("() => document.querySelector('#conn details.cn-soon').open"), "sending does not fold the list"
    imp = pg.evaluate("() => { const r = document.querySelector('#conn .cl-row.cn-imposs'); return [r.title, !!r.querySelector('button')]; }")
    assert imp == ["CloudKit only gives the app's own container", False]
    assert pg.evaluate("() => document.querySelectorAll('link[href$=\"conectores.css\"]').length") == 1
    pg.evaluate("() => __conn.unmount()")
    assert pg.evaluate("() => document.querySelector('#conn').children.length") == 0


def test_an_empty_read_is_retried_while_shown_and_never_while_hidden(page):
    pg = page
    pg.evaluate("() => { __data = { live: [], wish: [] }; __conn.show(); }")
    until_sync(lambda: pg.evaluate("() => __seen.loads") == 1, "the first read")
    pg.evaluate("() => __conn.hide()")
    pg.wait_for_timeout(2400)
    assert pg.evaluate("() => __seen.loads") == 1, "a hidden column reads nothing"
    pg.evaluate("() => __conn.show()")
    until_sync(lambda: pg.evaluate("() => __seen.loads") == 3, "the retry of an empty read", timeout_s=5)


def test_the_network_column_paints_its_four_blocks_and_acts_through_its_bridge(page):
    pg = page
    redraw = "() => __redraw.forEach(f => f())"
    assert pg.evaluate("() => document.querySelector('#red .cl-list').children.length") == 0, "off: no body"
    pg.evaluate(f"() => {{ __net = {{}}; ({redraw})(); }}")
    assert pg.evaluate("() => document.querySelector('#red .cl-list').children.length") == 0, "a stub answer is off too"
    pg.evaluate("() => __red.show()")
    assert pg.evaluate("() => __seen.refresh") == 1, "show() re-reads"
    pg.evaluate(f"(n) => {{ __net = n; ({redraw})(); }}", NET)
    assert pg.evaluate(TEXTS, "#red .a2a-sec > .cn-fam") == [EN[k] for k in ("a2a.pending", "a2a.relationships", "a2a.grants", "a2a.recent")]
    assert pg.text_content("#red .a2a-card .cl-q") == EN["a2a.card_request"].replace("{name}", "Pepe")
    assert pg.evaluate(TEXTS, "#red .a2a-ev span") == ["← freebusy · calendar", "Marta"]
    pg.click("#red .a2a-card .cl-b.on")
    until_sync(lambda: EN["a2a.answered_yes"] in (pg.text_content("#red .a2a-card") or ""), "the card to say what he answered")
    assert pg.evaluate("() => __seen.answer") == [["c9", True]]
    pg.click("#red .a2a-chip .cl-b")
    assert pg.evaluate("() => __seen.revoke") == [["marta", "calendar"]]
    pg.evaluate(f"() => {{ __net = null; ({redraw})(); }}")
    assert pg.evaluate("() => document.querySelectorAll('#red .a2a-sec').length") == 0, "off again: no body"

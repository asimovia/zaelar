"""V2-931 · An answered confirmation leaves ONE record line, in the system's own colour — RENDERED, both themes.

«Ricard confirms that the message is sent» is neither his bubble nor the agent's: it wears the question card's surface
and accent edge (`shared-surfaces.css`, tokens only), so it reads as the end of that card. The engine writes it
(`nucleo/conversation_host/wall_notes.record`, writer `record`, a note of kind `record`): its `wall` event, as the engine
emits it, goes through the production router into the real ChatWall in Chromium; the line's class (`cw-msg record`) and its computed colours are
read from the DOM, in the dark and in the light theme. The phone's sheet (the same wall, its own classes) must class
that line `zm-msg record`: it is mounted for real and read, and the same rule is checked with the phone's stylesheet.
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
LINE = {"es": "Ricard confirma que mandemos el mensaje a Odile", "en": "Quinn confirms that the message to Odile is sent"}

pytest.importorskip("playwright.sync_api")

LOG = """() => localStorage.getItem('hb_wall_lines') || JSON.stringify({ lines: [] })"""


def _wall_events(*lines):
    """The `wall` events the engine emits for his line, ours and the record line — on the wire, as `observer` flattens
    them (`{kind: "wall", writer, op}`)."""
    from nucleo.conversation_host import wall, wall_notes
    from voice import observer
    got, emit = [], observer.emit
    observer.emit = lambda kind, label, text="", role="", extra=None, piece=None: got.append(
        {"kind": kind, "label": label, **(extra or {})})
    try:
        wall._reset_for_tests()
        for role, text in lines:
            if role == "record":
                wall_notes.record(text)
            else:
                wall._say("keyboard:t" if role == "you" else "mouth", {"op": "append", "id": f"l_{len(got)}",
                                                                      "role": role, "state": "final", "text": text})
    finally:
        observer.emit = emit
        wall._reset_for_tests()
    return got
COLOURS = """(sel) => { const e = document.querySelector(sel); const s = getComputedStyle(e);
    return { cls: [...e.classList], bg: s.backgroundColor, ink: s.color, edge: s.borderLeftColor,
             edgeW: s.borderLeftWidth, text: (e.textContent || '').trim() }; }"""


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


def _wall(browser, port):
    pg = browser.new_page(viewport={"width": 1280, "height": 800})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"strings": _EN})))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async () => {
        localStorage.clear();
        for (const h of ['/frontend/app/core/palette.css', '/frontend/app/styles.css', '/frontend/app/core/shared-surfaces.css']) {
          const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle('en'); if (i18n.applyLang) await i18n.applyLang('en');
        const store = await import('/frontend/app/core/store.js?v=2');
        const wall = await import('/frontend/app/components/ChatWall.js?v=5');
        window.__sse = await import('/frontend/app/services/sse.js?v=2');
        document.body.append(wall.ChatWall());
        window.__store = store;
        store.openChatFrom('orb'); store.setChatTab('chat');
    }""")
    pg.wait_for_selector("#chatwall.open", timeout=5000)
    pg._errors = errors
    return pg


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_record_line_is_neither_bubble_in_either_theme(browser_and_port, lang):
    br, port = browser_and_port
    pg = _wall(br, port)
    pg.evaluate("(evs) => evs.forEach(d => window.__sse.routeEvent(null, d))",
                _wall_events(("you", "send it"), ("agent", "on it"), ("record", LINE[lang])))
    pg.wait_for_selector("#chatwall .cw-msg.record", timeout=5000)
    for theme in ("dark", "light"):
        pg.evaluate("(t) => { if (t === 'light') document.documentElement.dataset.theme = 'light'; "
                    "else delete document.documentElement.dataset.theme; }", theme)
        rec, you, agent = (pg.evaluate(COLOURS, f"#chatwall .cw-msg.{c}") for c in ("record", "you", "agent"))
        assert rec["text"] == LINE[lang] and "record" in rec["cls"], rec
        assert not {"you", "agent", "sys"} & set(rec["cls"]), f"[{theme}] the record line is drawn as a bubble: {rec['cls']}"
        assert rec["bg"] not in (you["bg"], agent["bg"]), f"[{theme}] its surface is a bubble's: {rec['bg']}"
        assert rec["bg"] not in ("rgba(0, 0, 0, 0)", "transparent"), f"[{theme}] it has no surface of its own"
        assert rec["ink"] not in (you["ink"],), f"[{theme}] its ink is his bubble's"
        assert rec["edgeW"] == "3px" and rec["edge"] != rec["bg"], f"[{theme}] it lost the question card's accent edge"
    card = pg.evaluate("""() => { const d = document.createElement('div'); d.className = 'tq'; document.body.append(d);
        const s = getComputedStyle(d); const r = { bg: s.backgroundColor, edge: s.borderLeftColor }; d.remove(); return r; }""")
    rec = pg.evaluate(COLOURS, "#chatwall .cw-msg.record")
    assert (rec["bg"], rec["edge"]) == (card["bg"], card["edge"]), "it does not wear the question card's surface and edge"
    until_sync(lambda: any(m.get("role") == "note" and m.get("kind") == "record" and m.get("text") == LINE[lang]
                           and m.get("state") == "final" for m in json.loads(pg.evaluate(LOG))["lines"]),
               "the record line is kept with the history")
    assert not pg._errors, pg._errors
    pg.close()


def test_the_phones_sheet_classes_the_record_line_as_a_record(browser_and_port):
    """The phone's sheet mounts the same wall with its own classes: the answered question's line must wear
    `zm-msg record` there, never a bubble's or a plain system note's class (the colour rule below keys on it)."""
    br, port = browser_and_port
    pg = br.new_page(viewport={"width": 390, "height": 800})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"strings": _EN})))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async () => {
        localStorage.clear();
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle('en'); if (i18n.applyLang) await i18n.applyLang('en');
        const store = await import('/frontend/app/core/store.js?v=2');
        const m = await import('/frontend/mobile/app/shell/ChatSheet.js?v=1');
        document.body.append(m.ChatSheet());
        store.setChatTab('chat'); store.setChatOpen(true);
    }""")
    pg.evaluate("""async (evs) => { const { routeWall } = await import('/frontend/app/services/wall-bridge.js?v=1');
                                   evs.forEach(routeWall); }""",
                _wall_events(("you", "send it"), ("agent", "on it"), ("record", LINE["en"])))
    rows = until_sync(lambda: (lambda xs: xs if len(xs) == 3 else None)(pg.evaluate(
        """() => [...document.querySelectorAll('.zm-msgs > *')].filter(n => !n.hidden)
               .map(n => ({ cls: [...n.classList], text: (n.textContent || '').trim() }))""")),
        "the three lines on the phone's sheet", timeout_s=10)
    rec = [r for r in rows if r["text"] == LINE["en"]]
    assert rec, rows
    assert "zm-msg" in rec[0]["cls"] and "record" in rec[0]["cls"], f"the phone draws the record line as {rec[0]['cls']}"
    assert not {"you", "agent", "sys"} & set(rec[0]["cls"]), f"the phone draws the record line as a bubble or a note: {rec[0]['cls']}"
    assert not errors, errors
    pg.close()


def test_the_phones_stylesheet_gives_the_record_class_its_own_colour(browser_and_port):
    br, port = browser_and_port
    pg = br.new_page(viewport={"width": 390, "height": 800})
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async () => {
        for (const h of ['/frontend/app/core/palette.css', '/frontend/mobile/app/styles.css', '/frontend/app/core/shared-surfaces.css']) {
          await new Promise((ok) => { const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h;
                                      l.onload = ok; l.onerror = ok; document.head.append(l); }); }
        const box = document.createElement('div'); box.className = 'zm-msgs';
        for (const role of ['you', 'agent', 'record']) {
          const row = document.createElement('div'); row.className = 'zm-msg ' + role; row.textContent = role; box.append(row); }
        document.body.append(box);
    }""")
    for theme in ("dark", "light"):
        pg.evaluate("(t) => { if (t === 'light') document.documentElement.dataset.theme = 'light'; "
                    "else delete document.documentElement.dataset.theme; }", theme)
        rec, you, agent = (pg.evaluate(COLOURS, f".zm-msg.{c}") for c in ("record", "you", "agent"))
        assert rec["bg"] not in (you["bg"], agent["bg"], "rgba(0, 0, 0, 0)"), f"[{theme}] phone: {rec}"
        assert rec["edgeW"] == "3px", f"[{theme}] phone: no accent edge"
    pg.close()

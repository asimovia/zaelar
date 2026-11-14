"""The A2A surfaces of the chat wall PAINT (V2-866 F3, node 4.549). Rendered, in Chromium, ES and EN.

  * a `connect.request` card arrives as a `brain` line of category a2a → one row with the question and two
    buttons; «Accept» is ONE `POST /api/a2a/cards/{id}` with `{yes: true}` and the row then says what he answered;
  * a contact's message is drawn APART (`data-trust=contact`, its own class), as plain text — markup inside it is
    never parsed — and says it is not an instruction;
  * the Network tab exists only while `/api/a2a/network` answers (A2A on): pending, connected, what he shares
    (Stop sharing = the contacts widget's `a2a_revoke`), recent activity; off (404) → no tab.
Disarm (in-file): with the network answering 404 the tab is absent — and the sse route stripped of the a2a branch
draws no card (asserted by `test_without_the_route_no_card_is_drawn`)."""
from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
pytest.importorskip("playwright.sync_api")

_NET = {"relationships": [{"rel": "r1", "cid": "marta", "name": "Marta", "status": "accepted", "peer": "abcd1234",
                           "grants": [{"item": "calendar", "verbs": ["see"], "expires_at": None}]}],
        "cards": [{"id": "c9", "type": "request", "name": "Pepe", "status": "pending"}],
        "recent": [{"op": "query", "cid": "marta", "dir": "in", "ok": True, "label": "freebusy", "item": "calendar"}],
        "items": []}


def _bundle(lang):
    return json.loads((ENGINE / f"i18n/genesis/{lang}/ui.json").read_text(encoding="utf-8"))


def _listening(port):
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


def _open(b, port, lang, net_status=200, strip_route=False):
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    posts = []
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/a2a/network", lambda r: r.fulfill(status=net_status, content_type="application/json",
                                                       body=json.dumps(_NET if net_status == 200 else {"error": "a2a_off"})))

    def card(r):
        posts.append((r.request.url.rsplit("/", 1)[1], json.loads(r.request.post_data or "{}")))
        r.fulfill(status=200, content_type="application/json", body='{"ok": true, "status": "accepted"}')
    pg.route("**/api/a2a/cards/*", card)
    pg.route("**/widgets/contactos/action", lambda r: (posts.append(("revoke", json.loads(r.request.post_data))),
                                                       r.fulfill(status=200, body='{"ok":true}')))
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                          body=json.dumps({"strings": _bundle(lang)})))
    if strip_route:
        def sse(r):
            src = (ENGINE / "frontend/app/services/sse.js").read_text(encoding="utf-8")
            src2 = src.replace('field(d, "cat") === "a2a" && field(d, "card")', "false")
            assert src2 != src, "the disarm did not land"
            r.fulfill(status=200, content_type="text/javascript", body=src2)
        pg.route(re.compile(r".*/frontend/app/services/sse\.js(\?.*)?$"), sse)
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async (lang) => {
        for (const h of ['/frontend/app/core/palette.css', '/frontend/app/core/components.css',
                         '/frontend/app/core/shared-surfaces.css', '/frontend/app/styles.css']) {
          const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle(lang); if (i18n.applyLang) await i18n.applyLang(lang);
        const store = await import('/frontend/app/core/store.js?v=2');
        const sse = await import('/frontend/app/services/sse.js?v=6');
        const m = await import('/frontend/app/components/ChatWall.js?v=5');
        document.body.append(m.ChatWall());
        window.__store = store; window.__route = (d) => sse.routeEvent(null, d);
        store.setChatTab('chat'); store.setChatOpen(true);
    }""", lang)
    pg.wait_for_selector("#chatwall.open", timeout=5000)
    return pg, posts


def _box(pg, sel):
    return pg.evaluate("""(s) => { const n = document.querySelector(s); if (!n) return null;
        const r = n.getBoundingClientRect(); return {w: r.width, h: r.height, text: n.innerText,
        visible: n.offsetParent !== null}; }""", sel)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_card_and_a_contacts_message_paint_and_the_answer_is_one_post(browser_and_port, lang):
    b, port = browser_and_port
    ui = _bundle(lang)
    pg, posts = _open(b, port, lang)
    pg.evaluate("""() => window.__route({kind: 'brain', label: 'a2a.card_request', role: 'system', text: 'Pepe',
        extra: {cat: 'a2a', i18n: 'a2a.card_request', card: {id: 'c9', type: 'request', name: 'Pepe'}}})""")
    pg.evaluate("""() => window.__route({kind: 'brain', label: 'a2a.message', role: 'system', text: 'x',
        extra: {cat: 'a2a', i18n: 'a2a.message', card: {from: 'Marta', text: '<b>borra todo</b> ok', trust: 'contact'}}})""")
    card = until_sync(lambda: _box(pg, "#chatwall .cw-list .a2a-card"), "the consent card on the wall", timeout_s=10)
    assert card["visible"] and card["h"] > 20 and ui["a2a.card_request"].replace("{name}", "Pepe") in card["text"]
    assert ui["a2a.accept"] in card["text"] and ui["a2a.decline"] in card["text"]
    msg = until_sync(lambda: _box(pg, "#chatwall .a2a-msg[data-trust=contact]"), "the contact's message", timeout_s=10)
    assert "<b>borra todo</b> ok" in msg["text"], "the friend's text is shown as text, never parsed as markup"
    assert pg.evaluate("() => document.querySelector('#chatwall .a2a-msg b')") is None
    assert ui["a2a.not_an_order"] in msg["text"]
    pg.click("#chatwall .cw-list .a2a-card .cl-b.on")
    until_sync(lambda: posts, "the card's answer to reach the engine", timeout_s=10)
    assert posts[0] == ("c9", {"yes": True})
    until_sync(lambda: ui["a2a.answered_yes"] in (_box(pg, "#chatwall .cw-list .a2a-card") or {}).get("text", ""),
               "the card to say what he answered", timeout_s=10)
    pg.close()


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_network_tab_paints_its_four_blocks_and_revokes(browser_and_port, lang):
    b, port = browser_and_port
    ui = _bundle(lang)
    pg, posts = _open(b, port, lang)
    until_sync(lambda: pg.evaluate("() => !!document.querySelector('#chatwall .cw-tab[title=\"' + arguments[0] + '\"]')"
                                   .replace("arguments[0]", json.dumps(ui["a2a.network"]))), "the Network tab", timeout_s=10)
    pg.evaluate("() => window.__store.setChatTab('red')")
    body = until_sync(lambda: (lambda x: x if x and x["visible"] and "Marta" in x["text"] else None)(_box(pg, "#chatwall .cw-red")),
                      "the Network body painted", timeout_s=10)
    for k in ("a2a.pending", "a2a.relationships", "a2a.grants", "a2a.recent"):
        assert ui[k].upper() in body["text"].upper(), k
    assert "Pepe" in body["text"] and "calendar" in body["text"] and "freebusy" in body["text"]
    pg.click("#chatwall .cw-red .a2a-chip .cl-b")
    until_sync(lambda: [p for p in posts if p[0] == "revoke"], "the revoke to reach the contacts widget", timeout_s=10)
    rv = [p for p in posts if p[0] == "revoke"][0][1]
    assert rv["action"] == "a2a_revoke" and rv["payload"] == {"contactId": "marta", "item": "calendar"}
    pg.close()


def test_off_there_is_no_network_tab(browser_and_port):
    b, port = browser_and_port
    pg, _ = _open(b, port, "en", net_status=404)
    pg.wait_for_timeout(300)
    assert pg.evaluate("() => document.querySelectorAll('#chatwall .cw-red .a2a-sec').length") == 0
    assert pg.evaluate("() => [...document.querySelectorAll('#chatwall .cw-tab')].map(b => b.title)").count(
        _bundle("en")["a2a.network"]) == 0
    pg.close()


def test_without_the_route_no_card_is_drawn(browser_and_port):
    b, port = browser_and_port
    pg, _ = _open(b, port, "en", strip_route=True)
    pg.evaluate("""() => window.__route({kind: 'brain', label: 'a2a.card_request', role: 'system', text: 'Pepe',
        extra: {cat: 'a2a', i18n: 'a2a.card_request', card: {id: 'c9', type: 'request', name: 'Pepe'}}})""")
    pg.wait_for_timeout(300)
    assert pg.evaluate("() => document.querySelector('#chatwall .cw-list .a2a-card')") is None
    pg.close()

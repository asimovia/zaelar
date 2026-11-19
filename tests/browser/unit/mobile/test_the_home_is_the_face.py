"""With the agent's face on, the phone's home IS the face, as the desktop's empty desk is (V2-928, node 4.595).

RENDERED: the real `Deck.js` + `HomeToday.js` + `deck-screen.js` + `app/presence/state.js`, at 393×852 with touch.
Face on (everyone's default) and the home in view: nothing over the face is painted — no title, no today, no hint, no
tiles, even with apps open — the agenda is never read for a today nobody sees, and the screen document says the home
holds `face` alone. Turning the face off brings the launcher back with today's lines. Disarm: the deck stops marking the
face home and the launcher is painted over the face again.
"""
from __future__ import annotations

import json
import pathlib

from tests.browser.unit.mobile.phone_page import open_phone

ENGINE = pathlib.Path(__file__).resolve().parents[4]
DECK = ENGINE / "frontend" / "mobile" / "app" / "shell" / "Deck.js"
_MARK = 'home.classList.toggle("zm-home-face", this._faceHome);'
_AGENDA = {"meetings": [{"date": "2099-01-01", "startTime": "09:00", "title": "Coffee with Ana"}]}


def _widgets(route):
    path = route.request.url.split("?")[0].split("/widgets", 1)[1]
    if path.endswith("/widget.js"):
        return route.fulfill(status=200, content_type="text/javascript",
                             body="export function render(el) { el.innerHTML = '<p>mounted</p>'; }")
    if path.startswith("/agenda/data"):
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(_AGENDA))
    body = {"registry": [{"id": "timer", "name": "Timer", "surface": "user", "origin": "builtin"}]} \
        if path == "/registry" else {}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


# What a person SEES of the home: every child of it that takes up room on screen.
_PAINTED = """() => [...document.querySelector('.zm-home').children]
    .filter((c) => { const r = c.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
    .map((c) => c.className)"""


def _run(deck_src: str | None = None) -> dict:
    agenda: list[str] = []

    def widgets(route):
        if "/agenda/data" in route.request.url:
            agenda.append(route.request.url)
        _widgets(route)

    routes = [(lambda u: "/widgets" in u and "/frontend/" not in u, widgets)]
    if deck_src is not None:
        routes.append(("**/frontend/mobile/app/shell/Deck.js*", lambda r: r.fulfill(
            status=200, content_type="text/javascript", body=deck_src)))
    with open_phone("", routes=routes) as pg:
        pg.evaluate("""async () => {
            const stage = document.createElement('div'); stage.id = 'zm-deck-wrap'; document.body.append(stage);
            window.__presence = await import('/frontend/app/presence/state.js?v=1');
            const { Deck } = await import('/frontend/mobile/app/shell/Deck.js?v=face');
            window.__deck = new Deck(stage);
            window.__deck.home();
        }""")
        pg.wait_for_timeout(700)
        empty = pg.evaluate(_PAINTED)                           # nothing open: the deck's «talk to me» hint is ON
        band = pg.evaluate("() => { const r = document.querySelector('.zm-pips').getBoundingClientRect(); return r.height; }")
        pg.evaluate("async () => { await window.__deck.show('timer'); window.__deck.home(); }")
        pg.wait_for_timeout(700)
        on = {"presence": pg.evaluate("() => window.__presence.presenceOn()"), "painted": pg.evaluate(_PAINTED), "empty": empty, "band": band,
              "agenda": len(agenda)}
        reps = [p["body"] for p in pg._posts if p["url"] == "/api/screen/report"]
        on["holds"] = reps[-1]["doc"]["home"]["holds"] if reps else None
        pg.evaluate("() => window.__presence.setPresenceOn(false)")
        pg.wait_for_timeout(700)
        reps = [p["body"] for p in pg._posts if p["url"] == "/api/screen/report"]
        off = {"painted": pg.evaluate(_PAINTED), "holds": reps[-1]["doc"]["home"]["holds"], "agenda": len(agenda)}
        assert not pg._errors, pg._errors
        return {"on": on, "off": off}


def test_with_the_face_on_the_home_is_only_the_face():
    r = _run()
    assert r["on"]["presence"] is True, "the face is on by default"
    assert r["on"]["empty"] == [], f"nothing over the face with no app open, not even the hint: {r['on']['empty']}"
    assert r["on"]["band"] == 0, "with no app open the page row draws no empty band above the dock"
    assert r["on"]["painted"] == [], f"nothing over the face with apps open, not even their tiles: {r['on']['painted']}"
    assert r["on"]["holds"] == ["face"], f"the screen document says what the home holds: {r['on']['holds']}"
    assert r["on"]["agenda"] == 0, "a today nobody sees is not read"
    assert "apps" in r["off"]["holds"] and "greeting" in r["off"]["holds"], r["off"]
    assert any("zm-today" in c for c in r["off"]["painted"]), f"face off, the launcher is back: {r['off']['painted']}"
    assert r["off"]["agenda"] >= 1, "face off, the home reads today's agenda again"


def test_disarm_a_deck_that_does_not_mark_the_face_home_paints_over_the_face():
    src = DECK.read_text(encoding="utf-8")
    assert src.count(_MARK) == 1, "disarm did not land"
    r = _run(src.replace(_MARK, ""))
    assert r["on"]["painted"] != [] and r["on"]["empty"] != [], r["on"]

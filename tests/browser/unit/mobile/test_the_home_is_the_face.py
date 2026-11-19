"""The phone's home draws NOTHING, whatever the face's switch (V2-928, operator 2026-11-19; node 4.595).

The operator's words: no welcome screen on the phone, no hello, no good afternoon, nothing — the agent's face on a dark
ground. RENDERED: the real `Deck.js` + `deck-screen.js` + `app/presence/state.js`, at 393×852 with touch. With the face
on and with it off, with no app open and with apps open, nothing on the home takes up room on screen; the agenda is
never read for it; the screen document says the home holds nothing; and with no app open the page row draws no empty
band above the dock. Disarm: the deck draws a line on its home again.
"""
from __future__ import annotations

import json
import pathlib

from tests.browser.unit.mobile.phone_page import open_phone

ENGINE = pathlib.Path(__file__).resolve().parents[4]
DECK = ENGINE / "frontend" / "mobile" / "app" / "shell" / "Deck.js"
_MOUNT = "    this._home = home;\n"


def _widgets(route, agenda):
    path = route.request.url.split("?")[0].split("/widgets", 1)[1]
    if path.startswith("/agenda/data"):
        agenda.append(path)
    if path.endswith("/widget.js"):
        return route.fulfill(status=200, content_type="text/javascript",
                             body="export function render(el) { el.innerHTML = '<p>mounted</p>'; }")
    body = {"registry": [{"id": "timer", "name": "Timer", "surface": "user", "origin": "builtin"}]} \
        if path == "/registry" else {}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


# What a person SEES of the home: every element inside it that takes up room on screen.
_PAINTED = """() => [...document.querySelector('.zm-home').querySelectorAll('*')]
    .filter((c) => { const r = c.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
    .map((c) => c.className || c.tagName)"""
_BAND = "() => document.querySelector('.zm-pips').getBoundingClientRect().height"


def _holds(pg):
    reps = [p["body"] for p in pg._posts if p["url"] == "/api/screen/report"]
    return reps[-1]["doc"]["home"]["holds"] if reps else None


def _run(deck_src: str | None = None) -> dict:
    agenda: list[str] = []
    routes = [(lambda u: "/widgets" in u and "/frontend/" not in u, lambda r: _widgets(r, agenda))]
    if deck_src is not None:
        routes.append(("**/frontend/mobile/app/shell/Deck.js*", lambda r: r.fulfill(
            status=200, content_type="text/javascript", body=deck_src)))
    out = {}
    with open_phone("", routes=routes) as pg:
        pg.evaluate("""async () => {
            const stage = document.createElement('div'); stage.id = 'zm-deck-wrap'; document.body.append(stage);
            window.__presence = await import('/frontend/app/presence/state.js?v=1');
            const { Deck } = await import('/frontend/mobile/app/shell/Deck.js?v=face');
            window.__deck = new Deck(stage); window.__deck.home();
        }""")
        for face in (True, False):
            pg.evaluate("(on) => window.__presence.setPresenceOn(on)", face)
            pg.evaluate("async () => { window.__deck.closeAll({ by: 'hand' }); window.__deck.home(); }")
            pg.wait_for_timeout(500)
            empty = {"painted": pg.evaluate(_PAINTED), "band": pg.evaluate(_BAND), "holds": _holds(pg)}
            pg.evaluate("async () => { await window.__deck.show('timer'); window.__deck.home(); }")
            pg.wait_for_timeout(500)
            out["on" if face else "off"] = {"empty": empty, "apps": {"painted": pg.evaluate(_PAINTED), "holds": _holds(pg)}}
        out["agenda"] = len(agenda)
        assert not pg._errors, pg._errors
    return out


def test_the_phone_home_draws_nothing_face_on_or_off():
    r = _run()
    for face in ("on", "off"):
        for state in ("empty", "apps"):
            got = r[face][state]
            assert got["painted"] == [], f"face {face}, {state}: something is drawn on the home: {got['painted']}"
            assert got["holds"] == [], f"face {face}, {state}: the screen document says the home holds {got['holds']}"
        assert r[face]["empty"]["band"] == 0, f"face {face}: an empty page row is drawn above the dock"
    assert r["agenda"] == 0, "the home reads no agenda: there is no today to draw"


def test_disarm_a_deck_that_draws_a_line_on_its_home_turns_it_red():
    src = DECK.read_text(encoding="utf-8")
    assert src.count(_MOUNT) == 1, "disarm did not land"
    line = ("    home.append(Object.assign(document.createElement('h2'), { className: 'zm-greet', "
            "textContent: 'Good afternoon' }));\n")
    r = _run(src.replace(_MOUNT, _MOUNT + line))
    assert r["on"]["empty"]["painted"] and r["off"]["apps"]["painted"], r

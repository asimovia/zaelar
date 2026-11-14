"""The phone deck's screen document equals what the deck SHOWS (V2-907 T8, node 4.543).

RENDERED: the real `Deck.js` + `deck-screen.js` + `HomeToday.js` + the shared `screen-reporter.js`, at 393×852 with
touch, the engine's orders driven through the REAL `services/sse.js` (`routeEvent`, with a `seq`), his hand through
the card's own ⌂ ‹ › × buttons. After every step the last document the deck POSTed to `/api/screen/report` is compared
with the DOM (the card painted `live` is the front, every other card is behind, the home painted `live` is the home
in view), and every order's answer is checked. Closing the last app leaves `front: ""` with the home shown and saying
what it holds. Parametrized over every app in `widgets/*/manifest.json`. Disarm: `_goTo` stops reporting.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from tests.browser.unit.mobile.phone_page import open_phone

ENGINE = pathlib.Path(__file__).resolve().parents[4]
APPS = sorted(p.parent.name for p in (ENGINE / "widgets").glob("*/manifest.json"))
_STUB = "export function render(el) { el.innerHTML = '<p class=\"stub\">mounted</p>'; }"
DECK = ENGINE / "frontend" / "mobile" / "app" / "shell" / "Deck.js"
_GOTO_REPORT = "    this._paint(); this._reportOpen();               // V2-903: a page change changes the app in front — say it"


def _widgets(route):
    path = route.request.url.split("?")[0].split("/widgets", 1)[1]
    if path.endswith("/widget.js"):
        return route.fulfill(status=200, content_type="text/javascript", body=_STUB)
    body = {"widgets": [{"id": w} for w in APPS]} if path in ("", "/") else \
        {"registry": [{"id": w, "name": w, "surface": "user", "origin": "builtin"} for w in APPS]} if path == "/registry" else {}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


SETUP = """
  window.__sse = await import('/frontend/app/services/sse.js?v=6');
  window.__newDeck = async (v) => {
    document.querySelectorAll('.zm-deck').forEach((s) => { s.remove(); });
    const stage = document.createElement('div'); stage.id = 'zm-deck-wrap'; document.body.append(stage);
    const { Deck } = await import('/frontend/mobile/app/shell/Deck.js?v=' + (v || '5'));
    if (window.__deck && window.__deck._screen) window.__deck._screen.rep.dispose();
    window.__deck = new Deck(stage);
  };
"""

_TRUTH = """() => {
  const deck = window.__deck, out = {};
  for (const c of deck.stage.querySelectorAll('.zm-card[data-wid]')) {
    if (!deck.cards.has(c.dataset.wid)) continue;
    out[c.dataset.wid] = c.classList.contains('live') ? 'front' : 'behind';
  }
  const home = deck.stage.querySelector('.zm-home');
  return { open: out, home: !!(home && home.classList.contains('live')), mount: deck._screen && deck._screen.rep.mount };
}"""

_LAYOUT = ("**/api/canvas/layout*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                      body=json.dumps({"items": [], "live": [], "elsewhere": []})))


@pytest.fixture(scope="module")
def phone():
    with open_phone(SETUP, routes=[(lambda u: "/widgets" in u and "/frontend/" not in u, _widgets), _LAYOUT]) as pg:
        yield pg


def _reports(pg, mount):
    return [p["body"] for p in pg._posts if p["url"] == "/api/screen/report" and p["body"].get("mount") == mount]


def _order(pg, label, id_="", seq=0):
    pg.evaluate("(d) => window.__sse.routeEvent(window.__deck, d)",
                {"kind": "widget", "label": label, **({"id": id_} if id_ else {}), "seq": seq, "src": "brain"})
    pg.wait_for_timeout(320)


def _hand(pg, id_, which):
    pg.evaluate("([id, k]) => { const c = window.__deck.cards.get(id).card;"
                " const bs = c.querySelectorAll('.zm-head > button'); (k === 'x' ? bs[bs.length - 1] : c.querySelector('.zm-' + k)).click(); }",
                [id_, which])
    pg.wait_for_timeout(320)


def _same(pg, step) -> dict:
    t = pg.evaluate(_TRUTH)
    reps = _reports(pg, t["mount"])
    assert reps, f"{step}: the deck never reported"
    doc = reps[-1]["doc"]
    assert doc["layout"] == "deck"
    got = {r["id"]: r["vis"] for r in doc["open"]}
    assert got == t["open"], f"{step}: the document {got} is not the deck {t['open']}"
    fronts = [i for i, v in t["open"].items() if v == "front"]
    assert doc["front"] == (fronts[0] if fronts else ""), f"{step}: front {doc['front']!r} vs {fronts}"
    assert doc["home"]["shown"] is t["home"], f"{step}: home shown {doc['home']} vs {t['home']}"
    assert not fronts or doc["open"][0]["id"] == fronts[0], f"{step}: the front is not layer 0: {doc['open']}"
    return doc


def _scenario(pg, app, version: str = "5") -> dict:
    pg.evaluate("(v) => window.__newDeck(v)", version)
    pg.wait_for_timeout(300)
    a, b = [x for x in APPS if x != app][:2]
    _order(pg, "show", app, 1); _same(pg, f"show {app}")
    _order(pg, "show", a, 2); _order(pg, "show", b, 3); _same(pg, "three shown, the last in front")
    _order(pg, "show", app, 4); _same(pg, f"{app} brought to the front by order")
    _order(pg, "show", app, 5)
    _hand(pg, app, "next"); _same(pg, "paged forward by hand")
    _hand(pg, a, "home-b") if pg.evaluate(f"() => window.__deck.order[window.__deck.at] === {json.dumps(a)}") else \
        pg.evaluate("() => window.__deck.home()")
    pg.wait_for_timeout(320)
    doc = _same(pg, "the home by hand")
    assert doc["front"] == "" and "greeting" in doc["home"]["holds"] and "apps" in doc["home"]["holds"], doc["home"]
    _order(pg, "minimize", a, 6)
    _order(pg, "show", b, 7); _hand(pg, b, "x"); _same(pg, f"close {b} by hand")
    _order(pg, "close", a, 8); _same(pg, f"close {a} by order")
    _order(pg, "close", "nope", 9)
    _order(pg, "close", app, 10)
    doc = _same(pg, "the last app closed")
    assert doc["open"] == [] and doc["front"] == "" and doc["home"]["shown"] is True, doc
    assert "apps" not in doc["home"]["holds"] and "greeting" in doc["home"]["holds"], doc["home"]
    _order(pg, "close", "", 11)
    mount = pg.evaluate(_TRUTH)["mount"]
    ns = [r["n"] for r in _reports(pg, mount)]
    assert ns == sorted(set(ns)), f"n went back: {ns}"
    return {a_["seq"]: a_["why"] for r in _reports(pg, mount) for a_ in r.get("acks", [])}


@pytest.mark.parametrize("app", APPS)
def test_the_deck_reports_what_it_shows(phone, app):
    got = _scenario(phone, app)
    want = {1: "done", 2: "done", 3: "done", 4: "done", 5: "already_front", 6: "done", 7: "done", 8: "done",
            9: "not_open", 10: "done", 11: "already_closed"}
    assert {k: got.get(k) for k in want} == want, got
    assert not phone._errors, phone._errors


def test_disarm_a_page_change_that_does_not_report_turns_it_red(phone):
    src = DECK.read_text(encoding="utf-8")
    assert src.count(_GOTO_REPORT) == 1, "disarm did not land"
    mutated = src.replace(_GOTO_REPORT, "    this._paint();")
    phone.route("**/frontend/mobile/app/shell/Deck.js?v=disarm", lambda r: r.fulfill(
        status=200, content_type="text/javascript", body=mutated))
    try:
        with pytest.raises(AssertionError, match="by order|by hand"):
            _scenario(phone, "agenda", "disarm")
    finally:
        phone.unroute("**/frontend/mobile/app/shell/Deck.js?v=disarm")
        phone.evaluate("() => window.__newDeck()")

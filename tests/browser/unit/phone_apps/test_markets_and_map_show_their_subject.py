"""Markets and map show their own subject on a phone, or an honest empty page — never a sentence over black
(V2-877 #8, V2-876 P-41/P-42), RENDERED at 393×852 inside the deck's card.

What a phone showed: Markets and Map opened as one line of text at the top and a black page below. The data path
behind it: neither card had been filled — the quote and the places were answered in the chat, and a card only shows
what its own action (`show`) stored. So:

  · markets declares a quote question as its own («what's Apple's stock price» → `show`), and empty it is a page with
    the request that fills it and a field that runs the same `show` by hand; its period tabs are 44pt;
  · the map always draws its base map — the area a screen of his reported (`here`), else the world — with the request
    over it, zoom controls at a corner (44pt), and one-finger pan marked `[data-hpan]` so the deck leaves that swipe
    to the map and still pages from the screen's edge (V2-124).

Disarm: return early before the base map when the map has no places → red.
"""
from __future__ import annotations

import json
import pathlib

import pytest

pytest.importorskip("playwright.sync_api")

from tests.browser.unit.phone_apps._phone import phone  # noqa: E402

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
_PLACES = [{"name": "Sightglass Coffee", "address": "270 7th St", "lat": 37.7766, "lon": -122.4087},
           {"name": "Ritual Coffee", "address": "1026 Valencia St", "lat": 37.7564, "lon": -122.4213}]


def test_markets_declares_a_quote_question_as_its_own():
    m = json.loads((_ENGINE / "widgets/markets/manifest.json").read_text())
    assert "price" in m["whenToUse"] and "price" in m["actions"]["show"]["desc"]
    assert len(m["actions"]["show"]["desc"]) <= 200, "a descriptor is read up to 200 characters"


def test_markets_empty_is_a_page_with_its_request_and_a_field_that_fills_it():
    with phone("markets") as pg:
        pg.route("**/*", lambda r: r.abort() if "127.0.0.1" not in r.request.url else r.continue_())
        pg.evaluate("(d) => window.__render(d)", {"symbol": ""})
        m = pg.evaluate("""() => { const el = document.querySelector('.hb-mkt'), sc = document.querySelector('.zm-scroll');
            const b = el.querySelector('button'), i = el.querySelector('input');
            return {h: el.getBoundingClientRect().height, sh: sc.clientHeight, bh: b.getBoundingClientRect().height,
                    ih: i.getBoundingClientRect().height, ifs: parseFloat(getComputedStyle(i).fontSize)}; }""")
        assert m["h"] >= 0.9 * m["sh"], f"the empty state is the page, not a line on top: {m}"
        assert m["bh"] >= 44 and m["ih"] >= 44 and m["ifs"] >= 16, m
        pg.fill(".hb-mkt input", "Apple")
        pg.click(".hb-mkt button")
        assert ["show", {"symbol": "Apple"}] in pg.evaluate("() => window.__acts")
        pg.evaluate("(d) => window.__render(d)", {"symbol": "AAPL", "name": "Apple Inc.", "price": 226.31,
                    "currency": "USD", "change_pct": -0.53, "range": "1d", "points": [[1, 225.0], [2, 226.3]]})
        q = pg.evaluate("""() => ({tabs: Math.min(...[...document.querySelectorAll('.mkttab')].map(b => b.getBoundingClientRect().height)),
            num: getComputedStyle(document.querySelector('.mktprice')).fontVariantNumeric,
            sign: document.querySelector('.mktchg').textContent, down: document.querySelector('.mktchg').classList.contains('down')})""")
        assert q["tabs"] >= 44 and "tabular-nums" in q["num"], q
        assert "▼" in q["sign"] and q["down"], f"the sign is said by arrow AND colour: {q}"


def _map(pg, data):
    pg.evaluate("(d) => window.__render(d)", data)
    pg.wait_for_timeout(150)
    return pg.evaluate("""() => { const v = document.querySelector('.mapview'), sc = document.querySelector('.zm-scroll');
        const r = v.getBoundingClientRect(), ctl = [...document.querySelectorAll('.mapctl button')].map(b => b.getBoundingClientRect());
        return {tiles: v.querySelectorAll('.maptile').length, h: r.height, sh: sc.clientHeight, hpan: v.hasAttribute('data-hpan'),
                ctl: ctl.map(c => [Math.round(c.width), Math.round(c.height), c.right <= r.right && c.bottom <= r.bottom]),
                note: (v.querySelector('.mapnote') || {}).textContent || '', pins: v.querySelectorAll('.mappin').length}; }""")


def test_the_empty_map_draws_its_base_map_with_the_request_over_it():
    with phone("map") as pg:
        pg.route("https://tile.openstreetmap.org/**", lambda r: r.fulfill(status=200, content_type="image/png", body=b""))
        m = _map(pg, {"places": [], "empty": True})
        assert m["tiles"] > 0, "no base map: a sentence over black"
        assert m["h"] >= 0.5 * m["sh"], f"the map takes the page: {m}"
        assert "show them on a map" in m["note"], m
        assert m["hpan"], "the map owns its one-finger pan; the deck still pages from the edge"
        assert len(m["ctl"]) == 2 and all(w >= 44 and h >= 44 and inside for w, h, inside in m["ctl"]), m
        zoomed = _map(pg, {"places": [], "empty": True, "area": {"lat": 37.77, "lon": -122.42}})
        z = pg.evaluate("() => document.querySelector('.maptile').src")
        assert "/11/" in z, f"with his area known, the empty map opens on it: {z}"
        full = _map(pg, {"places": _PLACES, "title": "Coffee"})
        assert full["pins"] == 2 and not full["note"], full


def test_the_map_pans_with_one_finger_and_zooms_from_its_corner():
    with phone("map") as pg:
        pg.route("https://tile.openstreetmap.org/**", lambda r: r.fulfill(status=200, content_type="image/png", body=b""))
        _map(pg, {"places": _PLACES})
        pin = lambda: pg.evaluate("() => document.querySelector('.mappin').getBoundingClientRect().left")
        x0 = pin()
        box = pg.evaluate("() => { const r = document.querySelector('.mapview').getBoundingClientRect(); return [r.left + 40, r.top + 200]; }")
        pg.mouse.move(*box); pg.mouse.down(); pg.mouse.move(box[0] + 80, box[1], steps=4); pg.mouse.up()
        assert abs(pin() - x0 - 80) <= 2, "a drag moves the map under the finger"
        z0 = pg.evaluate("() => document.querySelector('.maptile').src.split('/')[3]")
        pg.evaluate("() => document.querySelector('.mapctl button').click()")
        z1 = pg.evaluate("() => document.querySelector('.maptile').src.split('/')[3]")
        assert int(z1) == int(z0) + 1, (z0, z1)


def test_the_empty_map_reads_his_area_from_the_state(monkeypatch):
    import memory.api as memory
    from widgets.map import data
    monkeypatch.setattr(data, "_load", lambda: data._seed())
    monkeypatch.setattr(memory, "state", lambda: {"here": {"place": "Lyon", "lat": 45.7640, "lon": 4.8357}})
    assert data.view_data()["area"] == {"lat": 45.76, "lon": 4.84}
    monkeypatch.setattr(memory, "state", lambda: {})
    assert "area" not in data.view_data() or data.view_data()["area"] is None

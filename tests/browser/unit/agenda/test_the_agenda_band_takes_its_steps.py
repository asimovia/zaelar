"""The agenda's band is the house bar: ONE line in its order, then a second row, then a ⋯ menu (V2-882).

The operator's screenshot (2026-11-11), the agenda at desk-app width: the band had wrapped into two misaligned
lines — the switch, ‹ Today ›, the week and, far right, the account, three provider icons and the plug on the first;
Day · Week · Month · List alone under the title on the second — and «New appointment at 11:00», a grid cell's
tooltip, was painted over ‹ Today ›. RENDERED at the three widths every widget is checked at (maximized, a narrow
desk app, the phone), inside the real app chrome with the house stylesheets the shells load.

Disarms: `bar()` that never measures (the band stays at step 0) → the narrow and phone cases go red; `tip()` writing
a `title` again → the tooltip case goes red.
"""
from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys

import pytest

from tests.waiting import port_listening

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
_DATA = json.loads((_ENGINE / "tests/browser/unit/phone_apps/agenda_week.json").read_text())
# The band the operator photographed: an account picker and three providers beside the plug (invented account).
_DATA.update(calendars=[{"id": "google", "label": "Google Calendar", "status": "connected"},
                        {"id": "icloud", "label": "iCloud", "status": "unavailable"},
                        {"id": "outlook", "label": "Outlook", "status": "unavailable"}],
             googleCalendars=[{"id": "a", "summary": "nadia.ferrer.long@example.com"}, {"id": "b", "summary": "Family"}],
             defaultCalendarId="a")

_HEAD = ("<link rel='stylesheet' href='/frontend/app/core/palette.css'>"
         "<link rel='stylesheet' href='/frontend/app/core/components.css'><body style='margin:0'>")
_DESK = ("<div class='hb-win' style='position:fixed;left:20px;top:20px;width:{w}px;height:620px;display:flex;"
         "flex-direction:column;overflow:hidden;box-sizing:border-box'><div class='hb-scroll' style='flex:1 1 auto;"
         "min-height:0;overflow:auto;padding:16px'><div id='w'></div></div></div>")
_PHONE = ("<div class='zm-scroll' style='width:393px;height:780px;overflow:auto;box-sizing:border-box;padding:0 12px;"
          "display:flex;flex-direction:column'><div id='w' style='flex:1 1 auto;min-height:0;display:flex;"
          "flex-direction:column'></div></div>")


@pytest.fixture(scope="module")
def page():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=_ENGINE,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_listening(port)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(viewport={"width": 1560, "height": 900})
            pg._hb_origin = f"http://127.0.0.1:{port}"
            yield pg
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _mount(page, width: int | None) -> dict:
    page.goto(page._hb_origin + "/widgets/agenda/")
    page.set_content(_HEAD + (_PHONE if width is None else _DESK.format(w=width)))
    page.evaluate("""async ([src, d]) => { const mod = await import(src);
        const ctx = { action(){ return Promise.resolve({ok: true}); }, close(){}, top(){}, openConnector(){}, lang: 'es', running: true };
        mod.render(document.getElementById('w'), d, ctx); }""", [page._hb_origin + "/widgets/agenda/widget.js", _DATA])
    page.wait_for_timeout(150)
    return _band(page)


def _band(page) -> dict:
    return page.evaluate("""() => {
        const b = document.querySelector('.agsub'), q = s => b.querySelector(s);
        const box = e => { if(!e || e.offsetParent === null) return null; const r = e.getBoundingClientRect();
                           return {t: Math.round(r.top), b: Math.round(r.bottom), l: Math.round(r.left), r: Math.round(r.right)}; };
        const iv = [...b.querySelectorAll('button,select,.agrange')].filter(e => e.offsetParent !== null)
          .map(e => e.getBoundingClientRect()).map(r => [r.top, r.bottom]).sort((x, y) => x[0] - y[0]);
        const rows = []; for(const [t, bt] of iv){ const l = rows[rows.length - 1];
          if(l && t < l[1] - 2) l[1] = Math.max(l[1], bt); else rows.push([t, bt]); }
        const cut = [b, ...b.querySelectorAll('.hb-bar-lead,.agrange,.agviews,.agviewsright')]
          .filter(e => e.offsetParent !== null && e.scrollWidth > e.clientWidth + 1).map(e => e.className);
        return {step: b.dataset.step, rows: rows.length, cut, band: box(b), sec: box(q('.agsec')), nav: box(q('.agnav')),
                range: box(q('.agrange')), tabs: box(q('.agtab')), sel: box(q('.agviewsel')), aux: box(q('.agviewsright')),
                plug: box(q('.agcalbtn')), more: box(q('.hb-bar-more'))};
    }""")


def test_a_wide_card_holds_the_band_on_ONE_line_in_its_order(page):
    g = _mount(page, 1470)
    assert g["step"] == "0" and g["rows"] == 1 and not g["cut"], g
    lefts = [g[k]["l"] for k in ("sec", "nav", "range", "tabs", "aux")]
    assert lefts == sorted(lefts), f"switch · ‹ Today › · range · views · account+providers+plug: {g}"
    assert g["plug"]["r"] <= g["band"]["r"] and g["more"] is None, g


def test_a_card_dragged_narrow_takes_two_declared_rows_never_a_ragged_wrap(page):
    g = _mount(page, 560)
    assert g["step"] in ("1", "2") and g["rows"] <= 2 and not g["cut"], g
    assert g["tabs"] is None and g["sel"] is not None, "the four tabs give way to their <select>"
    assert abs(g["sec"]["t"] - g["nav"]["t"]) <= 8 and g["range"]["t"] < g["sec"]["b"], \
        f"the switch, ‹ Today › and the range share the first row: {g}"
    if g["step"] == "2":
        assert g["aux"]["t"] >= g["nav"]["b"] - 1 and abs(g["aux"]["r"] - g["band"]["r"]) <= 12, \
            f"the account, providers and plug are the second row, on the band's right edge: {g}"


def test_the_phone_keeps_switch_today_and_title_and_folds_the_rest_into_one_menu(page):
    g = _mount(page, None)
    assert g["step"] == "3" and g["rows"] <= 2 and not g["cut"], g
    assert g["more"] is not None and abs(g["more"]["t"] - g["sec"]["t"]) <= 8, "the ⋯ on the switch's row"
    assert g["range"]["t"] >= g["sec"]["b"] - 1, "the week has its own row, whole"
    assert g["aux"] is None and g["sel"] is None and g["tabs"] is None, "views and connectors live in the menu"
    page.click(".hb-bar-more")
    page.click(".agtab[data-view=month]")
    assert page.locator(".agmgrid").count() == 1, "a view chosen in the menu is the view on screen"


def test_a_grid_cells_tooltip_stays_inside_the_calendar(page):
    _mount(page, 1470)
    assert page.evaluate("() => [...document.querySelectorAll('.agslot,.agev')].filter(e => e.title).length") == 0, \
        "no content element carries a `title` the operating system could paint over the band"
    page.hover(".agcol >> nth=5 >> .agslot >> nth=22")
    t = page.evaluate("""() => { const tip = document.querySelector('.hb-tipbox'), body = document.querySelector('.agbody');
        const r = tip.getBoundingClientRect(), s = body.getBoundingClientRect(), band = document.querySelector('.agsub').getBoundingClientRect();
        return {shown: !tip.hidden, inside: body.contains(tip), text: tip.textContent, top: r.top, bodyTop: s.top,
                bandBottom: band.bottom, right: r.right, bodyRight: s.right}; }""")
    assert t["shown"] and t["inside"] and t["text"], t
    assert t["top"] >= t["bandBottom"] and t["top"] >= t["bodyTop"] and t["right"] <= t["bodyRight"] + 1, t

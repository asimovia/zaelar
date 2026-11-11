"""A widget's bar is ONE line, then a second row, then a ⋯ menu — never a ragged wrap, never a third row (V2-882).

The operator, on a calendar band that had wrapped into two misaligned lines at full desk width: «order the data…
ideally ONE header line… when we need 2 rows we use 2; when we need menus that unfold, we add them. This must be so
for ALL widgets.» The class: a toolbar laid out as a loose flex-wrap, so each control lands where it runs out of
room. The house bar (`core/components.css` `.hb-bar` + `lib/toolbar.js`) declares the order and the steps, and
measures which step the bar needs. RENDERED, because «fits on one line» is a question only layout answers.

Disarms: `fit()` that always leaves step 0 → the narrow and phone cases go red (the line is cut); the step-3 grid
rule removed → the phone case goes red (a third row). The gate half: `_own_wrapping_bar` returning None → red.
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys

import pytest

from tests.waiting import port_listening

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

_ENGINE = pathlib.Path(__file__).resolve().parents[4]

# A bar with every part, in the order of importance; the labels are long enough that 560px cannot hold one line.
_BAR = """
<div id='card' style='box-sizing:border-box;padding:0 12px'>
 <div id='bar'>
  <div class='hb-bar-lead'><button class='hb-btn'><span class='hb-bar-label'>Calendar</span><i class='hb-bar-icon'>C</i></button>
       <button class='hb-btn'>‹</button><button class='hb-btn'>Today</button><button class='hb-btn'>›</button></div>
  <div class='hb-bar-title'>9 – 15 November 2026</div>
  <div class='hb-bar-tray'>
   <div class='hb-bar-views'><button class='hb-btn hb-wide'>Day</button><button class='hb-btn hb-wide'>Week</button>
        <button class='hb-btn hb-wide'>Month</button><button class='hb-btn hb-wide'>List</button>
        <select class='hb-select hb-narrow' style='width:auto'><option>Week</option></select></div>
   <div class='hb-bar-aux'><select class='hb-select' style='width:auto'><option>someone.long@example.com</option></select>
        <button class='hb-iconbtn'>G</button><button class='hb-iconbtn'>A</button><button class='hb-iconbtn'>O</button>
        <button class='hb-iconbtn hb-iconbtn--framed'>P</button></div>
  </div>
 </div>
 <div id='content' style='position:relative;height:200px;overflow:auto'>
   <div style='height:600px;position:relative'>
     <div id='cell' data-hb-tip='New appointment at 11:00' aria-label='New appointment at 11:00'
          style='position:absolute;left:0;right:0;top:0;height:24px'></div></div></div>
</div>"""


@pytest.fixture(scope="module")
def page():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=_ENGINE,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_listening(port)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(viewport={"width": 1500, "height": 800})
            pg._hb_origin = f"http://127.0.0.1:{port}"
            yield pg
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _mount(page, width: int) -> dict:
    page.goto(page._hb_origin + "/frontend/app/lib/")
    page.set_content("<link rel='stylesheet' href='/frontend/app/core/palette.css'>"
                     "<link rel='stylesheet' href='/frontend/app/core/components.css'>"
                     f"<body style='margin:0'><div style='width:{width}px'>{_BAR}</div></body>")
    page.evaluate("""async (src) => { const m = await import(src); window.__m = m;
        m.bar(document.getElementById('bar'), {more: 'More'}); m.tips(document.getElementById('content')); }""",
                  page._hb_origin + "/frontend/app/lib/toolbar.js")
    page.wait_for_timeout(120)
    return _geo(page)


def _geo(page) -> dict:
    return page.evaluate("""() => {
        const b = document.getElementById('bar'), q = s => b.querySelector(s);
        const box = e => { if(!e || e.offsetParent === null) return null; const r = e.getBoundingClientRect();
                           return {t: Math.round(r.top), b: Math.round(r.bottom), l: Math.round(r.left), r: Math.round(r.right)}; };
        const shown = [...b.querySelectorAll('button,select,.hb-bar-title')].filter(e => e.offsetParent !== null);
        // a row = a band of overlapping vertical extents; two controls of different heights on one line are one row
        const iv = shown.map(e => e.getBoundingClientRect()).map(r => [r.top, r.bottom]).sort((x, y) => x[0] - y[0]);
        const rows = []; for(const [t, bt] of iv){ const last = rows[rows.length - 1];
          if(last && t < last[1] - 2) last[1] = Math.max(last[1], bt); else rows.push([t, bt]); }
        const cut = [b, ...b.querySelectorAll('.hb-bar-lead,.hb-bar-title,.hb-bar-views,.hb-bar-aux')]
          .filter(e => e.offsetParent !== null && e.scrollWidth > e.clientWidth + 1).map(e => e.className);
        return {step: b.dataset.step, rows: rows.length, cut, bar: box(b), lead: box(q('.hb-bar-lead')),
                title: box(q('.hb-bar-title')), views: box(q('.hb-bar-views')), aux: box(q('.hb-bar-aux')),
                more: box(q('.hb-bar-more')), narrow: box(q('.hb-narrow')), wide: box(q('.hb-wide'))};
    }""")


def test_a_maximized_card_holds_the_whole_bar_on_ONE_line_in_its_order(page):
    g = _mount(page, 1400)
    assert g["step"] == "0" and g["rows"] == 1, g
    assert not g["cut"], g
    order = [g["lead"]["l"], g["title"]["l"], g["views"]["l"], g["aux"]["l"]]
    assert order == sorted(order), f"lead · title · views · aux, left to right: {g}"
    assert g["more"] is None, "no menu while everything fits"


def test_a_narrow_card_takes_its_steps_instead_of_wrapping(page):
    g = _mount(page, 560)
    assert g["step"] in ("1", "2"), g
    assert not g["cut"], f"nothing is cut at the step it chose: {g}"
    assert g["rows"] <= 2, f"never a third row: {g}"
    assert g["wide"] is None and g["narrow"] is not None, "the switcher shows its compact face"
    if g["step"] == "2":
        assert g["aux"]["t"] > g["lead"]["b"] - 2, "the least important group is the one on the second row"
        assert abs(g["aux"]["r"] - g["bar"]["r"]) <= 2, "…on the bar's own right edge, not wherever it fell"


def test_a_phone_folds_the_tray_into_ONE_menu_and_keeps_the_lead_and_the_title(page):
    g = _mount(page, 366)
    assert g["step"] == "3", g
    assert g["views"] is None and g["aux"] is None, "the switcher and the secondary group are in the menu"
    assert g["more"] is not None and g["lead"] is not None and g["title"] is not None, g
    assert g["rows"] <= 2, f"never a third row: {g}"
    assert abs(g["more"]["t"] - g["lead"]["t"]) <= 8, "the ⋯ sits on the lead's row"
    assert g["title"]["t"] >= g["lead"]["b"] - 1 and not g["cut"], f"the title has its own row and is whole: {g}"
    page.click(".hb-bar-more")
    opened = _geo(page)
    assert opened["views"] is not None and opened["aux"] is not None, "the menu unfolds with what it holds"
    assert opened["aux"]["r"] <= opened["bar"]["r"] + 1 and opened["views"]["l"] >= opened["bar"]["l"] - 1, \
        f"the menu stays inside the bar's width: {opened}"
    page.click(".hb-bar-views .hb-wide >> nth=1")
    assert _geo(page)["views"] is None, "a choice made in the menu closes it"


def test_the_step_is_measured_not_a_breakpoint(page):
    """The same width, longer labels: the bar steps earlier. A fixed breakpoint cannot see this difference."""
    _mount(page, 1400)
    short = page.evaluate("() => document.getElementById('bar').dataset.step")
    page.evaluate("""() => { document.querySelector('.hb-bar-title').textContent =
        'Monday the ninth of November to Sunday the fifteenth of November, two thousand and twenty-six';
        window.__m.fit(document.getElementById('bar')); }""")
    longer = _geo(page)
    assert short == "0" and longer["step"] != "0" and not longer["cut"], (short, longer)


def test_a_content_tooltip_is_drawn_inside_its_scroller_never_over_the_bar(page):
    _mount(page, 1400)
    page.hover("#cell")
    t = page.evaluate("""() => { const tip = document.querySelector('.hb-tipbox'), sc = document.getElementById('content');
        const r = tip.getBoundingClientRect(), s = sc.getBoundingClientRect(), b = document.getElementById('bar').getBoundingClientRect();
        return {text: tip.textContent, inside: sc.contains(tip), shown: !tip.hidden, top: r.top, sTop: s.top, barBottom: b.bottom,
                left: r.left, right: r.right, sLeft: s.left, sRight: s.right}; }""")
    assert t["shown"] and t["inside"] and t["text"] == "New appointment at 11:00", t
    assert t["top"] >= t["sTop"] and t["top"] >= t["barBottom"], f"under the cell, inside the content: {t}"
    assert t["left"] >= t["sLeft"] - 1 and t["right"] <= t["sRight"] + 1, t


def test_the_gate_rejects_a_bar_of_its_own_that_wraps_and_accepts_the_house_bar():
    from widgets import validator_js
    own = 'const CSS = `.hb-x .xbar{display:flex;flex-wrap:wrap;gap:8px}`;\nexport function render(el){}'
    msg = validator_js._scan_widget_js(own)
    assert msg and ".xbar" in msg and "hb-bar" in msg and "toolbar.js" in msg, msg
    kit = ('import { bar } from "/frontend/app/lib/toolbar.js";\n'
           'const CSS = `.hb-x .xbar{padding:4px} .hb-x .chips{display:flex;flex-wrap:wrap}`;\nexport function render(el){}')
    assert validator_js._scan_widget_js(kit) is None, "the house bar, and a wrapping row that is not a bar, pass"

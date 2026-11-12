# V2-885 — the video app works like the music app. Operator, 2026-11-11 (three screenshots: Home after a search with
# «Sonando ahora» ABOVE the results, an empty Lists tab with only a save field, the Queue as a flat list): «if I am
# searching, the FIRST thing shown is the search results… no app works like that»; with no search, a catalogue of
# rows; while something plays, the controls with the video in miniature at the very bottom; the search in the
# permanent bar at the far right; an empty section says so and offers the options; the queue as items well apart with
# a larger thumbnail, channel and data below the title, and clear buttons to remove it or move it up/down.
# Every case RENDERS the real widget.js — layout and flow live client-side.
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from tests.waiting import port_listening

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
_GIF = bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002020401003b")


def _data(**over):
    d = {"videoId": "", "title": "", "channel": "", "volume": 70, "muted": False, "paused": False, "cmd_seq": 0,
         "list": [], "pos": -1, "adding": "", "platforms": [], "suggested": [], "search_results": [],
         "search_query": "", "channels": [], "history": [], "prefs": {}, "prefs_notes": [], "lists": [],
         "connector_shelf": []}
    d.update(over)
    return d


_PLAY = {"videoId": "MMMMMMMMMM1", "title": "Madonna - Music (Official Video)", "channel": "Madonna"}
_RES = [{"videoId": "BBBBBBBBBB%d" % i, "title": "Bruce %d" % i, "channel": "Bruce Springsteen"} for i in range(1, 7)]
_Q = [{"videoId": "QQQQQQQQQQ%d" % i, "title": "Clip %d" % i, "channel": "Solo Fonseca", "published": "hace %d d" % i}
      for i in range(1, 4)]


@pytest.fixture(scope="module")
def _browser():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_listening(port)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            b._hb_port = port
            yield b
            b.close()
    finally:
        srv.terminate()


@pytest.fixture()
def page(_browser):
    p = _browser.new_page(viewport={"width": 1500, "height": 900})
    p.route("**://i.ytimg.com/**", lambda r: r.fulfill(status=200, content_type="image/gif", body=_GIF))
    p.route("**://www.youtube.com/**", lambda r: r.fulfill(status=200, content_type="text/html", body="<html></html>"))
    p._hb_port = _browser._hb_port
    yield p
    p.close()


def _mount(page, data, width=660, height=600):
    port = page._hb_port
    page.goto(f"http://127.0.0.1:{port}/widgets/youtube/")
    page.set_content(f"<div id='w' style='width:{width}px;height:{height}px'></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__mod = mod;
             window.__ctx = {action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve({ok: true}); },
                             top: () => {}, running: true};
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""", [f"http://127.0.0.1:{port}/widgets/youtube/widget.js", data])


def _calls(page):
    return page.evaluate("window.__calls")


def _tab(page, tid):
    page.evaluate("(t) => document.getElementById('w')._hbYtSelectTab(t)", tid)


def _shown(page, sel):
    return page.evaluate("(s) => { const e = document.querySelector(s); return !!e && e.getClientRects().length > 0; }", sel)


# ── Home: the results come FIRST; nothing of «what plays» above or between ────────────────────────────────────────

def test_with_a_search_the_results_are_the_first_thing_under_the_search_box(page):
    _mount(page, _data(search_results=_RES, search_query="bruce", history=_Q, **_PLAY))
    _tab(page, "inicio")
    order = page.evaluate("""() => [...document.querySelector('.hb-yt-home').children].map(e => e.className)""")
    assert order[0].startswith("hb-yt-hometitle"), order
    assert "Resultados" in page.inner_text(".hb-yt-home > :first-child")
    assert "Sonando ahora" not in page.inner_text(".hb-yt-home"), "what plays is the mini-player's, never Home's"
    assert page.locator(".hb-yt-shelf").count() == 0, "a live search IS Inicio: no catalogue rows under it"
    assert page.locator(".hb-yt-home .hb-yt-rnum").count() == 6
    # the search box sits ON TOP of Inicio, full width of the body
    box = page.evaluate("""() => { const s = document.querySelector('.hb-yt-search').getBoundingClientRect();
        const b = document.querySelector('.hb-yt-body').getBoundingClientRect();
        const h = document.querySelector('.hb-yt-home').getBoundingClientRect();
        return {sw: s.width, bw: b.width, above: s.bottom <= h.top}; }""")
    assert box["above"] and box["sw"] >= box["bw"] - 40, box


def test_without_a_search_home_is_a_catalogue_of_rows_and_an_empty_row_is_omitted(page):
    _mount(page, _data(history=_Q, channels=[{"name": "MUNDO DE LA VELA"}],
                       lists=[{"name": "tarde", "items": _Q[:2]}]))
    shelves = page.eval_on_selector_all(".hb-yt-shelf", "els => els.map(e => e.dataset.shelf)")
    assert shelves == ["history", "channels", "lists"], "no account connected → no suggestions row at all"
    # «ver todo» opens the row's tab
    page.locator(".hb-yt-shelf[data-shelf=lists] .hb-yt-seeall").click()
    assert "hb-yt-t-listas" in page.get_attribute(".hb-yt", "class")
    _tab(page, "inicio")
    page.locator(".hb-yt-shelf[data-shelf=channels] .hb-yt-seeall").click()
    assert "hb-yt-t-subs" in page.get_attribute(".hb-yt", "class")


def test_an_empty_catalogue_says_one_sentence_and_offers_search_and_the_account(page):
    _mount(page, _data(**_PLAY))
    _tab(page, "inicio")
    st = page.locator(".hb-yt-home .hb-empty-state")
    assert st.count() == 1
    assert "No hay ningún vídeo" not in st.inner_text(), "a video is playing: the catalogue is empty, not the card"
    assert page.eval_on_selector_all(".hb-yt-home [data-opt]", "els => els.map(e => e.dataset.opt)") == ["search", "connect"]
    page.click(".hb-yt-home [data-opt=connect]")
    assert "hb-yt-connmode" in page.get_attribute(".hb-yt", "class")


# ── The mini-player: off the player tab, never on it, gone with nothing current ───────────────────────────────────

def test_the_mini_player_shows_off_the_player_tab_and_drives_the_video(page):
    _mount(page, _data(list=_Q, **_PLAY))
    assert "hb-yt-t-player" in page.get_attribute(".hb-yt", "class")
    assert not _shown(page, ".hb-yt-mini"), "on the player tab the player itself is the controls"
    for t in ("inicio", "cola", "subs", "listas"):
        _tab(page, t)
        assert _shown(page, ".hb-yt-mini"), t
    geo = page.evaluate("""() => { const m = document.querySelector('.hb-yt-mini').getBoundingClientRect();
        const r = document.querySelector('.hb-yt').getBoundingClientRect();
        return {foot: Math.abs(m.bottom - r.bottom), pos: getComputedStyle(document.querySelector('.hb-yt-mini')).position}; }""")
    assert geo["foot"] <= 1 and geo["pos"] != "fixed", geo
    assert "Madonna - Music" in page.inner_text(".hb-yt-mini .hb-yt-mtitle")
    page.click(".hb-yt-mini .hb-yt-mbtn.main")
    page.click(".hb-yt-mini .hb-yt-mbtn[aria-label=Siguiente]")
    assert _calls(page)[:2] == [["pause", {}], ["next", {}]]
    page.click(".hb-yt-mini .hb-yt-minfo")
    assert "hb-yt-t-player" in page.get_attribute(".hb-yt", "class"), "tapping the title opens the player"


def test_the_mini_player_is_absent_with_nothing_current(page):
    _mount(page, _data(list=_Q))
    for t in ("inicio", "cola"):
        _tab(page, t)
        assert not _shown(page, ".hb-yt-mini"), t


# ── The queue: one card per video, a larger face, the controls named ──────────────────────────────────────────────

def test_the_queue_rows_are_cards_with_a_face_the_words_and_four_named_controls(page):
    _mount(page, _data(list=_Q, pos=1, **_PLAY))
    _tab(page, "cola")
    geo = page.evaluate("""() => { const rows = [...document.querySelectorAll('.hb-yt-list .hb-yt-qrow')];
        return rows.map((r, i) => ({img: r.querySelector('.hb-yt-rimg').getBoundingClientRect().width,
            gap: i ? r.getBoundingClientRect().top - rows[i-1].getBoundingClientRect().bottom : null,
            sub: r.querySelector('.hb-yt-rowc').textContent,
            labels: [...r.querySelectorAll('.hb-yt-qacts button')].map(b => b.getAttribute('aria-label')),
            disabled: [...r.querySelectorAll('.hb-yt-qacts button')].map(b => b.disabled)})); }""")
    assert len(geo) == 3
    assert all(g["img"] >= 110 for g in geo), geo
    assert all(g["gap"] >= 10 for g in geo[1:]), "well separated: --sp-3 between rows"
    assert geo[0]["sub"] == "Solo Fonseca · hace 1 d"
    assert geo[0]["labels"] == ["Reproducir desde aquí", "Subir", "Bajar", "Quitar de la lista"]
    assert geo[0]["disabled"] == [False, True, False, False] and geo[2]["disabled"] == [False, False, True, False]
    row = page.locator(".hb-yt-list .hb-yt-qrow").nth(1)
    row.locator("button[aria-label=Subir]").click()
    row.locator("button[aria-label=Bajar]").click()
    row.locator("button[aria-label='Quitar de la lista']").click()
    assert _calls(page) == [["move", {"item": "2", "to": "1"}], ["move", {"item": "2", "to": "3"}],
                            ["remove", {"item": "2"}]], "the voice's own move/remove, nothing new"
    assert "hb-yt-t-cola" in page.get_attribute(".hb-yt", "class"), "a control never plays the row underneath it"
    row.locator("button[aria-label='Reproducir desde aquí']").click()
    assert ["play_item", {"item": "2"}] in _calls(page)


def test_on_the_phone_the_queue_face_is_full_width_and_the_controls_44_points(page):
    _mount(page, _data(list=_Q), width=366)
    _tab(page, "cola")
    geo = page.evaluate("""() => { const r = document.querySelector('.hb-yt-qrow');
        return {img: r.querySelector('.hb-yt-rimg').getBoundingClientRect().width, row: r.getBoundingClientRect().width,
                btn: Math.min(...[...r.querySelectorAll('.hb-yt-qacts button')].map(b => b.getBoundingClientRect().height))}; }""")
    assert geo["img"] >= geo["row"] - 20 and geo["btn"] >= 44, geo


# ── Empty sections offer their options ───────────────────────────────────────────────────────────────────────────

def test_every_empty_tab_offers_its_options(page):
    _mount(page, _data())
    want = {"cola": ["search", "paste"], "listas": ["new", "search"], "subs": ["connect", "search"]}
    for t, opts in want.items():
        _tab(page, t)
        got = page.evaluate("""(t) => { const box = {cola: '.hb-yt-list', listas: '.hb-yt-mylists', subs: '.hb-yt-subs'}[t];
            return [...document.querySelectorAll(box + ' .hb-empty-state [data-opt]')].map(e => e.dataset.opt); }""", t)
        assert got == opts, (t, got)
    _tab(page, "cola")
    page.click(".hb-yt-list [data-opt=search]")
    assert "hb-yt-t-inicio" in page.get_attribute(".hb-yt", "class")
    assert page.evaluate("document.activeElement === document.querySelector('.hb-yt-search input')")


def test_a_new_list_comes_prefilled_with_todays_date_and_enter_saves_the_queue(page):
    _mount(page, _data(list=_Q))
    _tab(page, "listas")
    page.evaluate("window.__ctx.lang = 'es'")       # the host's language, not the page's <html lang> (here: none)
    page.click(".hb-yt-mylists [data-opt=new]")
    inp = page.locator(".hb-yt-newlist input")
    assert inp.is_visible()
    want = page.evaluate("new Intl.DateTimeFormat('es', {day: 'numeric', month: 'short', year: 'numeric'})"
                         ".format(new Date())")
    assert inp.input_value() == "Lista del " + want, "the date is named in ctx.lang"
    assert "3 vídeos" in page.inner_text(".hb-yt-newlist")
    # a repaint never eats the name he is typing
    inp.fill("tarde de vela")
    page.evaluate("(d) => window.__mod.render(document.getElementById('w'), d, window.__ctx)", _data(list=_Q))
    assert inp.input_value() == "tarde de vela"
    inp.press("Enter")
    assert ["save_list", {"name": "tarde de vela"}] in _calls(page)


def test_a_new_list_over_an_empty_queue_says_why_it_cannot_save(page):
    _mount(page, _data())
    _tab(page, "listas")
    page.click(".hb-yt-mylists [data-opt=new]")
    assert page.locator(".hb-yt-newlist button[type=submit]").is_disabled()
    assert "vacía" in page.inner_text(".hb-yt-newlist")
    page.locator(".hb-yt-newlist input").press("Enter")
    assert _calls(page) == []


# ── The bar at three widths ───────────────────────────────────────────────────────────────────────────────────────

_BAR = """() => { const r = (s) => { const e = document.querySelector(s); const b = e.getBoundingClientRect();
    return e.getClientRects().length ? {l: b.left, r: b.right, t: b.top, b: b.bottom} : null; };
    const tabs = [...document.querySelectorAll('.hb-yt-tab')].filter(t => t.getClientRects().length).map(t => t.dataset.tab);
    return {nav: r('.hb-yt-nav'), tabs, tabsBox: r('.hb-yt-tabs'), plug: r('.hb-yt-plug'), find: r('.hb-yt-find'),
            more: r('.hb-yt-menubtn'), wraps: [...document.querySelectorAll('.hb-yt-tab')].some(t => t.getClientRects().length > 1)}; }"""


def test_wide_the_bar_is_one_line_with_the_search_closing_it(page):
    _mount(page, _data(), width=900)
    g = page.evaluate(_BAR)
    assert g["tabs"] == ["inicio", "player", "cola", "subs", "listas"] and g["more"] is None
    assert abs(g["plug"]["t"] - g["find"]["t"]) < 2 and abs(g["tabsBox"]["t"] - g["nav"]["t"]) < 12, "one line"
    assert g["nav"]["r"] - g["find"]["r"] <= 16, "the search closes the bar at its right edge"
    assert 28 <= g["find"]["l"] - g["plug"]["r"] <= 36, "~30 px between the icons and the search"


def test_narrower_the_tools_take_a_second_row_aligned_right(page):
    _mount(page, _data(), width=520)
    g = page.evaluate(_BAR)
    assert len(g["tabs"]) == 5 and not g["wraps"]
    assert g["plug"]["t"] >= g["tabsBox"]["b"] - 1, "the tools sit on their own row under the tabs"
    assert g["nav"]["r"] - g["find"]["r"] <= 16, "…aligned to the right edge"


def test_on_the_phone_inicio_and_the_search_stay_and_the_rest_goes_behind_the_menu(page):
    _mount(page, _data(), width=366)
    _tab(page, "inicio")
    g = page.evaluate(_BAR)
    assert g["tabs"] == ["inicio"] and g["plug"] is None and g["find"] and g["more"]
    assert abs(g["find"]["t"] - g["tabsBox"]["t"]) < 8, "one row"
    page.click(".hb-yt-menubtn")
    items = page.eval_on_selector_all(".hb-yt-menu .hb-yt-mitem", "els => els.map(e => e.dataset.tab)")
    assert items == ["player", "cola", "subs", "listas"]
    page.click(".hb-yt-menu .hb-yt-mitem[data-tab=cola]")
    assert "hb-yt-t-cola" in page.get_attribute(".hb-yt", "class")
    assert page.locator(".hb-yt-menu").is_hidden()
    assert page.evaluate(_BAR)["tabs"] == ["inicio", "cola"], "the face on screen stays named in the bar"


def test_the_search_button_lands_on_inicio_with_the_box_focused_from_any_tab(page):
    _mount(page, _data(list=_Q, **_PLAY))
    assert "hb-yt-t-player" in page.get_attribute(".hb-yt", "class")
    assert page.get_attribute(".hb-yt-find", "aria-label") == "Buscar vídeos"
    page.click(".hb-yt-find")
    assert "hb-yt-t-inicio" in page.get_attribute(".hb-yt", "class")
    assert page.evaluate("document.activeElement === document.querySelector('.hb-yt-search input')")

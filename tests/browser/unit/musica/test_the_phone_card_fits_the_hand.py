# V2-876 P-20…P-23 — the music card on the phone, measured at 393x852 (iPhone 15/16/17) inside the phone shell's own
# geometry (Deck.js: a 48 px head, the scroller padding its child 12/12/40, the dock under it). The audit
# (TMP/phone-audit 66-69b) found up to FOUR strips at the foot (mini-player + the card's tabs + the pips + the dock),
# a 16:9 thumbnail letterboxed in a square frame, the embed's own pause glyph and logo over the art, «Unknown artist»,
# the «Up next» sheet half over the art and the Search tab prefilled with the playing query saying «Nothing for…».
# Every claim here is geometry or a rendered string, so it is asserted on a rendered document. The last test pins the
# desktop arrangements: the phone pass must not move one desktop pixel of layout.
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys

import pytest
from tests.waiting import port_listening

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
W, H = 393, 852

# YouTube's guaranteed thumbnail: a 16:9 picture with black bars baked into a 4:3 file.
_BARRED_SVG = ("<svg xmlns='http://www.w3.org/2000/svg' width='480' height='360'><rect width='480' height='360' "
               "fill='black'/><rect y='45' width='480' height='270' fill='#c06'/></svg>")
_ART = "https://i.ytimg.com/vi/VID00000001/hqdefault.jpg"

_SHELL = """<meta name='viewport' content='width=device-width,initial-scale=1'>
<style>body{margin:0}.zm-card{position:absolute;inset:0;bottom:110px;display:flex;flex-direction:column}
.zm-head{height:48px;flex:0 0 auto}.zm-scroll{flex:1 1 auto;min-height:0;overflow:auto;display:flex;flex-direction:column}
.zm-scroll > *{padding:12px 12px 40px;margin-block:0;min-height:100%;box-sizing:border-box}
.zm-dock{position:fixed;left:0;right:0;bottom:0;height:110px}</style>
<div class='zm-card'><div class='zm-head'></div><div class='zm-scroll'><div id='w'></div></div></div>
<div class='zm-dock'></div>"""

_DESK = """<style>body{margin:0}.hb-win{position:fixed;left:20px;top:20px;display:flex;flex-direction:column;
padding:30px 16px 16px;overflow:hidden;box-sizing:border-box;background:#fff}
.hb-scroll{flex:1 1 auto;min-height:0;overflow:auto}</style>"""


def _t(title, artist="", art="", **kw):
    d = {"title": title, "artist": artist, "album": "", "art": art, "query": f"{title} {artist}".strip(), "uri": ""}
    d.update(kw)
    return d


RECENT = [_t("Relaxing Jazz Piano Radio - 24/7 Live Stream - Slow Jazz Music for Work", "Cafe Music BGM", _ART),
          _t("Music For Work & Study", "Lofi", _ART), _t("Bossa Nova Morning", "Cafe", _ART),
          _t("Night Jazz", "Smooth", _ART)]


def _data(**over):
    d = {"connected": False, "mode": "youtube", "now_playing": None, "local": {}, "playlists": [],
         "recent": RECENT, "top": [], "fav_current": False,
         "yt": {"videoId": "VID00000001", "title": RECENT[0]["title"], "artist": "", "paused": False,
                "cmd_seq": 1, "art": _ART, "volume": 70},
         "modes": {"shuffle": False, "repeat": "off", "supported": True}, "volume": {"level": 70, "muted": False},
         "queue": {"items": RECENT[1:], "editable": True, "source": "youtube"},
         # what the agent's own play request leaves in the store (browse.after_play)
         "browse": {"search": {"query": "relaxing jazz", "candidates": [], "chosen": "youtube:track:x"}},
         "view": {"kind": "now", "id": ""}}
    d.update(over)
    return d


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


def _open(browser, phone=True):
    ctx = browser.new_context(viewport={"width": W, "height": H} if phone else {"width": 1400, "height": 1000},
                              has_touch=phone, is_mobile=phone)
    page = ctx.new_page()
    page.route("https://i.ytimg.com/**", lambda r: r.fulfill(status=200, content_type="image/svg+xml", body=_BARRED_SVG))
    page.route("https://www.youtube-nocookie.com/**", lambda r: r.fulfill(status=200, content_type="text/html",
                                                                       body="<body></body>"))
    page._hb_port = browser._hb_port
    return page


def _mount(page, data, desk=None):
    port = page._hb_port
    page.goto(f"http://127.0.0.1:{port}/widgets/musica/")
    if desk:
        w, h = desk
        page.set_content(f"{_DESK}<div class='hb-win' style='width:{w}px;height:{h}px'>"
                         f"<div class='hb-scroll'><div id='w'></div></div></div>")
    else:
        page.set_content(_SHELL)
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__ctx = {action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve({ok: true}); },
                             openConnector: () => {}, running: true};
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""", [f"http://127.0.0.1:{port}/widgets/musica/widget.js", data])
    page.wait_for_timeout(350)     # the 250 ms tick that lays the embed over its slot


@pytest.fixture()
def phone(_browser):
    page = _open(_browser)
    yield page
    page.context.close()


# ── rule 1: one bar at the bottom, and it is the shell's ─────────────────────────────────────────────────────

@pytest.mark.parametrize("view", ["library", "search", "collection", "now", "queue"])
def test_the_card_draws_no_bar_at_its_foot_and_its_tabs_sit_on_top(phone, view):
    _mount(phone, _data(view={"kind": view, "id": ""}))
    geo = phone.evaluate("""() => {
        const sc = document.querySelector('.hb-mus2-scroll').getBoundingClientRect();
        const tabs = document.querySelector('.hb-mus2-ptabs').getBoundingClientRect();
        // every piece of the card that is not the scrolling content must sit ABOVE it — nothing at the foot
        const below = [...document.querySelectorAll('.hb-mus2 > *, .hb-mus2-main > *, .hb-mus2-body > *')]
          .filter(e => !e.matches('.hb-mus2-body, .hb-mus2-main, .hb-mus2-scroll'))
          .filter(e => e.getBoundingClientRect().height && e.getBoundingClientRect().top >= sc.bottom - 1)
          .map(e => e.className);
        return {tabsBottom: tabs.bottom, scTop: sc.top, below, n: document.querySelectorAll('[role=tablist]').length,
                old: document.querySelectorAll('.hb-mus2-bnav, .hb-mus2-mini, .hb-mus2-bar').length};
    }""")
    assert geo["old"] == 0, "no bottom navigation, no mini-player strip, no desktop bar on the phone"
    assert geo["below"] == [], f"{view}: something stacks under the content: {geo['below']}"
    assert geo["tabsBottom"] <= geo["scTop"] + 1, "the four destinations are segmented tabs ABOVE the content"
    labels = phone.eval_on_selector_all(".hb-mus2-psegb > span", "els => els.map(e => e.textContent)")
    assert labels == ["Inicio", "Buscar", "Tu música", "Sonando"]


def test_the_mini_player_folds_into_the_tab_row(phone):
    _mount(phone, _data(view={"kind": "library", "id": ""}))
    pp = phone.query_selector(".hb-mus2-ptabs .hb-mus2-ptabpp")
    assert pp is not None, "off the player, a play/pause rides in the tab row"
    assert phone.query_selector(".hb-mus2-psegb:last-child .hb-mus2-eq") is not None, "«Now Playing» says it sounds"
    pp.click()
    assert phone.evaluate("() => window.__calls.map(c => c[0])")[-1] == "pause"
    _mount(phone, _data(view={"kind": "now", "id": ""}))
    assert phone.query_selector(".hb-mus2-ptabpp") is None, "on the player itself it would say the same thing twice"


# ── rule 2: 44 pt targets ───────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("view", ["library", "now"])
def test_tabs_and_transport_are_44_points(phone, view):
    _mount(phone, _data(view={"kind": view, "id": ""}))
    small = phone.evaluate("""() => [...document.querySelectorAll(
        '.hb-mus2-psegb, .hb-mus2-ptabpp, .hb-mus2-barc.big button, .hb-mus2-nowxb, .hb-mus2-nowacts button')]
        .filter(b => { const r = b.getBoundingClientRect(); return r.width < 44 || r.height < 44; })
        .map(b => b.className + ' ' + Math.round(b.getBoundingClientRect().width) + 'x'
                  + Math.round(b.getBoundingClientRect().height))""")
    assert small == [], small
    assert phone.evaluate("() => document.scrollingElement.scrollWidth <= innerWidth"), "no sideways scroll"


# ── rule 3: artwork never letterboxed; a missing artist is no line at all ────────────────────────────────────

def test_a_barred_thumbnail_is_cropped_to_its_picture_in_a_square(phone):
    _mount(phone, _data(view={"kind": "library", "id": ""}))
    imgs = phone.evaluate("""() => [...document.querySelectorAll('.hb-mus2-shelf .hb-mus2-art img')].map(i => {
        const f = i.parentElement.getBoundingClientRect(), r = i.getBoundingClientRect();
        // the bars are the top and bottom 12.5 % of the picture; cropped means they fall outside the frame
        return {lb: i.classList.contains('lb'), top: r.top + r.height * .125 <= f.top + .5,
                bottom: r.bottom - r.height * .125 >= f.bottom - .5}; })""")
    assert imgs and all(i["lb"] and i["top"] and i["bottom"] for i in imgs), imgs


def test_the_video_slot_takes_the_videos_ratio_and_a_paused_embed_leaves_the_art(phone):
    _mount(phone, _data(view={"kind": "now", "id": ""}))
    geo = phone.evaluate("""() => { const a = document.querySelector('.hb-mus2-nowart').getBoundingClientRect();
        const v = document.querySelector('.hb-mus2-audio').getBoundingClientRect();
        return {ar: a.width / a.height, vis: document.querySelector('.hb-mus2-audio').classList.contains('vis'),
                same: Math.abs(a.width - v.width) < 1 && Math.abs(a.height - v.height) < 1}; }""")
    assert abs(geo["ar"] - 16 / 9) < 0.02, f"a 16:9 picture in a {geo['ar']:.2f} frame is letterboxed"
    assert geo["vis"] and geo["same"], "the playing embed fills the slot exactly — no bars"
    d = _data(view={"kind": "now", "id": ""})
    d["yt"] = {**d["yt"], "paused": True}
    _mount(phone, d)
    assert not phone.evaluate("() => document.querySelector('.hb-mus2-audio').classList.contains('vis')"), \
        "paused, the embed's own pause glyph and logo must not paint over the art"
    assert phone.query_selector(".hb-mus2-nowart img") is not None


def test_an_unknown_artist_prints_nothing_and_a_long_title_keeps_its_end(phone):
    _mount(phone, _data(view={"kind": "now", "id": ""}))
    assert phone.query_selector(".hb-mus2-nowa") is None
    text = phone.inner_text(".hb-mus2")
    assert "desconocido" not in text and "Unknown artist" not in text
    geo = phone.evaluate("""() => { const t = document.querySelector('.hb-mus2-nowt').getBoundingClientRect();
        const tail = document.querySelector('.hb-mus2-nowtt'), head = document.querySelector('.hb-mus2-nowth');
        return {tail: tail.textContent, inside: tail.getBoundingClientRect().right <= t.right + 1,
                cut: head.scrollWidth > head.clientWidth, lines: Math.round(t.height)}; }""")
    assert RECENT[0]["title"].endswith(geo["tail"]) and geo["tail"].strip(), geo
    assert geo["inside"] and geo["cut"], "the ellipsis is in the MIDDLE: the head is cut, the end stays on screen"


# ── the queue, search and home ─────────────────────────────────────────────────────────────────────────────

def test_the_queue_is_a_page_not_a_sheet_over_the_art(phone):
    _mount(phone, _data(view={"kind": "queue", "id": ""}))
    assert phone.query_selector(".hb-mus2-qlayer") is None
    assert phone.query_selector(".hb-mus2-now") is None, "nothing half-covered under it"
    assert len(phone.query_selector_all(".hb-mus2-tr[data-idx]")) == 3
    phone.click(".hb-mus2-back")
    assert phone.evaluate("() => window.__calls.at(-1)") == ["open_view", {"kind": "now"}]


def test_search_never_opens_on_the_query_that_is_playing(phone):
    _mount(phone, _data(view={"kind": "search", "id": ""}))
    assert phone.input_value(".hb-mus2-sinp") == ""
    assert "Nada para" not in phone.inner_text(".hb-mus2-scroll")
    # a search he made himself, with results, stays as he left it
    d = _data(view={"kind": "search", "id": ""})
    d["browse"] = {"search": {"query": "bossa", "tracks": RECENT[2:3]}}
    _mount(phone, d)
    assert phone.input_value(".hb-mus2-sinp") == "bossa"


def test_continue_listening_hints_it_scrolls_and_shows_whole_titles(phone):
    _mount(phone, _data(view={"kind": "library", "id": ""}))
    geo = phone.evaluate("""() => { const s = document.querySelector('.hb-mus2-shelf'), c = getComputedStyle(s);
        const n = document.querySelector('.hb-mus2-shelf .hb-mus2-plname');
        return {scrolls: s.scrollWidth > s.clientWidth, mask: (c.maskImage || c.webkitMaskImage || '').includes('gradient'),
                peek: [...s.children].some(k => { const r = k.getBoundingClientRect();
                                                  return r.left < s.getBoundingClientRect().right && r.right > s.getBoundingClientRect().right; }),
                wrap: getComputedStyle(n).whiteSpace}; }""")
    assert geo["scrolls"] and geo["mask"] and geo["peek"], geo
    assert geo["wrap"] == "normal", "titles wrap to two lines instead of «/ork & Jazz Pian»"


# ── the desktop does not move ──────────────────────────────────────────────────────────────────────────────
# Geometry measured on origin/main (1431ca974) before the phone pass, with an artist and no art so the two rule-3
# fixes (no placeholder line, no baked bars) leave the boxes where they were.

_DESK_SNAPSHOT = {
    (1280, 900): {".hb-mus2-side": [36, 50, 200, 767], ".hb-mus2-headfix": [236, 50, 708, 47],
                  ".hb-mus2-nowart": [430, 221, 320, 320], ".hb-mus2-bar": [36, 817, 1248, 87]},
    (468, 540): {".hb-mus2-headfix": [36, 50, 436, 41], ".hb-mus2-nowart": [142, 105, 225, 225],
                 ".hb-mus2-bar": [36, 457, 436, 87]},
}


@pytest.mark.parametrize("size", list(_DESK_SNAPSHOT))
def test_the_desktop_layout_is_unchanged(_browser, size):
    page = _open(_browser, phone=False)
    d = _data(view={"kind": "now", "id": ""})
    d["yt"] = {**d["yt"], "artist": "Cafe Music BGM", "art": ""}
    _mount(page, d, desk=size)
    got = page.evaluate("""(sels) => Object.fromEntries(sels.map(s => { const e = document.querySelector(s);
        if(!e) return [s, null]; const r = e.getBoundingClientRect();
        return [s, [r.left, r.top, r.width, r.height].map(Math.round)]; }))""", list(_DESK_SNAPSHOT[size]))
    page.context.close()
    assert got == _DESK_SNAPSHOT[size]

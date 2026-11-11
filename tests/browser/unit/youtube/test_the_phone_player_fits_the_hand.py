# V2-876 P-24 + V2-877 #6 — the video card on the phone, measured at 393x852 inside the phone shell's scroller. The audit
# (TMP/phone-audit 7a) found the Home tab a dead end («No video loaded» over a video that was playing), the tabs in a
# sideways scroller cut at «Subscriptio…», the player stretched to fill instead of 16:9, controls under 44 pt, the
# «blocked by its owner» notice amber-on-amber, and the embed's own «Watch on YouTube» in another language. The last
# test pins the desktop card's geometry: the phone rules live under `.zm-scroll` and must not move it.
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys

import pytest
from tests.waiting import port_listening

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from tests.browser.unit.youtube.test_the_player_wears_tabs_and_a_dashboard import _RESULTS, _data

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
_GIF = bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002020401003b")
_SHELL = """<meta name='viewport' content='width=device-width,initial-scale=1'>
<style>body{margin:0;background:#1b1f27}.zm-card{position:absolute;inset:0;bottom:110px;display:flex;flex-direction:column}
.zm-head{height:48px;flex:0 0 auto}.zm-scroll{flex:1 1 auto;min-height:0;overflow:auto;display:flex;flex-direction:column}
.zm-scroll > *{padding:12px 12px 40px;margin-block:0;min-height:100%;box-sizing:border-box}</style>
<div class='zm-card'><div class='zm-head'></div><div class='zm-scroll'><div id='w'></div></div></div>"""
_TITLE = "Golden Gate Bridge: The Structure that Defined an Era | FD Engineering"


def _playing(**over):
    d = _data(videoId="GGGGGGGGGG1", title=_TITLE, channel="Free Documentary", paused=False, muted=False,
              search_results=_RESULTS, search_query="golden gate",
              blocked_notice={"kind": "swapped", "from": "Colossal Construction of the Golden Gate Bridge",
                              "to": _TITLE, "code": "150"})
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
    ctx = browser.new_context(viewport={"width": 393, "height": 852} if phone else {"width": 1000, "height": 900},
                              has_touch=phone, is_mobile=phone)
    page = ctx.new_page()
    page.route("**://i.ytimg.com/**", lambda r: r.fulfill(status=200, content_type="image/gif", body=_GIF))
    page.route("**://www.youtube.com/**", lambda r: r.fulfill(status=200, content_type="text/html", body="<html></html>"))
    page._hb_port = browser._hb_port
    return page


def _mount(page, data, desk=False):
    port = page._hb_port
    page.goto(f"http://127.0.0.1:{port}/widgets/youtube/")
    page.set_content("<div id='w' style='width:660px;height:600px'></div>" if desk else _SHELL)
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src);
             // the host's i18n door: a key reads back as itself, so the test sees WHICH key each label used
             window.__ctx = {action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve({ok: true}); },
                             top: () => {}, running: true, lang: 'en',
                             t: (k) => k === 'widgets.youtube.tab_subs_short' ? 'Channels' : k};
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""", [f"http://127.0.0.1:{port}/widgets/youtube/widget.js", data])


@pytest.fixture()
def phone(_browser):
    page = _open(_browser)
    yield page
    page.context.close()


def test_the_tabs_share_one_row_with_no_sideways_scroll_and_44_points(phone):
    _mount(phone, _playing())
    geo = phone.evaluate("""() => { const s = document.querySelector('.hb-yt-tabs');
        const tabs = [...document.querySelectorAll('.hb-yt-tab')].map(t => { const r = t.getBoundingClientRect();
            return {h: r.height, cut: t.scrollWidth > t.clientWidth + 1, right: r.right}; });
        return {scrolls: s.scrollWidth > s.clientWidth + 1, tabs, edge: document.querySelector('.hb-yt').getBoundingClientRect().right,
                plug: !!document.querySelector('.hb-yt-plug').getClientRects().length}; }""")
    assert not geo["scrolls"], "every tab in sight — no strip to scroll"
    assert all(t["h"] >= 44 and not t["cut"] and t["right"] <= geo["edge"] + 1 for t in geo["tabs"]), geo["tabs"]
    assert not geo["plug"], "the connector is not a phone control (rule 5)"
    assert phone.evaluate("() => getComputedStyle(document.querySelector('[data-tab=subs]'), '::after').content") \
        == '"Channels"', "the long tab wears its short label, from the bundle"


def test_home_is_reachable_and_shows_what_plays(phone):
    _mount(phone, _playing(search_results=[], search_query=""))
    phone.tap(".hb-yt-tab[data-tab=inicio]")
    assert "hb-yt-t-inicio" in phone.get_attribute(".hb-yt", "class")
    home = phone.inner_text(".hb-yt-home")
    assert "No hay ningún vídeo" not in home, "never «No video loaded» over a video that is loaded"
    assert "Sonando ahora" in home and "Golden Gate" in home
    phone.tap(".hb-yt-nowtile")
    assert "hb-yt-t-player" in phone.get_attribute(".hb-yt", "class"), "and the way back to the player is one tap"


def test_the_player_is_16_9_with_44_point_controls(phone):
    _mount(phone, _playing())
    geo = phone.evaluate("""() => { const f = document.querySelector('.hb-yt-frame').getBoundingClientRect();
        const small = [...document.querySelectorAll('.hb-yt-ctrls button')].filter(b => {
            const r = b.getBoundingClientRect(); return r.width < 44 || r.height < 44; }).length;
        return {ar: f.width / f.height, small, home: document.querySelector('[data-tab=inicio]').getBoundingClientRect().top}; }""")
    assert abs(geo["ar"] - 16 / 9) < 0.02, geo
    assert geo["small"] == 0
    assert 0 <= geo["home"] < 200, "«back to the catalog» — the Home tab — is on screen above the video"


def test_the_notice_is_legible_and_only_for_the_video_it_swapped_to(phone):
    _mount(phone, _playing())
    c = phone.evaluate("""() => [getComputedStyle(document.querySelector('.hb-yt-blockmsg')).color,
                                 getComputedStyle(document.querySelector('.hb-yt-title')).color]""")
    assert c[0] == c[1], f"the notice reads in the card's ink, not amber on amber: {c}"
    assert phone.is_visible(".hb-yt-blockmsg")
    _mount(phone, _playing(title="Golden Gate timelapse 4K", videoId="TTTTTTTTTT1"))
    assert not phone.is_visible(".hb-yt-blockmsg"), "another video plays now: the swap happened to nothing on screen"


def test_the_embed_speaks_the_cards_language(phone):
    _mount(phone, _playing())
    assert "hl=en" in phone.get_attribute(".hb-yt-frame iframe", "src")


# Desktop: geometry of the card at 660x600 measured on origin/main (1431ca974) before this pass, on the player tab with
# no notice (the notice's own padding is the one intended change).
_DESK = {".hb-yt-nav": [8, 8, 660, 49], ".hb-yt-frame": [8, 91, 660, 462], ".hb-yt-ctrls": [8, 553, 660, 55]}


def test_the_desktop_card_is_unchanged(_browser):
    page = _open(_browser, phone=False)
    _mount(page, _playing(blocked_notice={}), desk=True)
    got = page.evaluate("""(sels) => Object.fromEntries(sels.map(s => { const r = document.querySelector(s).getBoundingClientRect();
        return [s, [r.left, r.top, r.width, r.height].map(Math.round)]; }))""", list(_DESK))
    page.context.close()
    assert got == _DESK

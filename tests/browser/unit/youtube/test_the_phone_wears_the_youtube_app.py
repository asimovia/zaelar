# 2026-11-17 — the video widget on the phone, modelled on the YouTube app after the operator called it «malísimo»
# (iPhone screenshots: a ⋯ menu dropped over iOS's own Paste callout, two search doors, «Results 0 · Searching…» over an
# empty page, a two-column grid with badges over the pictures, a mini-player a fifth of the screen tall, a watch page
# with no seek bar and no title). Every case RENDERS the real widget.js inside the phone shell's scroller (393×852),
# with the kit's stylesheet, as test_the_phone_player_fits_the_hand.py does.
from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")

from tests.browser.unit.youtube.test_the_phone_player_fits_the_hand import _browser, _mount, _open, _playing, phone  # noqa: F401
from tests.browser.unit.youtube.test_the_player_wears_tabs_and_a_dashboard import _RESULTS

_RECENT = ["golden gate", "paella valenciana", "regatas"]
_RES = [dict(r, duration=d, published="3 years ago") for r, d in zip(_RESULTS, ["52:11", "", "1:02:45"])]
_Q = [{"videoId": "QQQQQQQQQQ%d" % i, "title": "Clip %d" % i, "channel": "Solo Fonseca"} for i in range(1, 4)]


def _cls(page):
    return page.get_attribute(".hb-yt", "class")


def _calls(page):
    return page.evaluate("window.__calls")


def test_the_search_is_the_bar_itself_and_an_empty_field_lists_his_recent_searches(phone):
    _mount(phone, _playing(search_results=[], search_query="", recent_queries=_RECENT))
    phone.tap(".hb-yt-tab[data-tab=cola]")
    phone.tap(".hb-yt-find")
    vis = phone.evaluate("""() => { const v = (s) => [...document.querySelectorAll(s)].some(e => e.getClientRects().length);
        return {field: v('.hb-yt-search input'), chips: v('.hb-yt-tab'), find: v('.hb-yt-find'), mini: v('.hb-yt-mini'),
                focus: document.activeElement === document.querySelector('.hb-yt-search input'),
                rows: [...document.querySelectorAll('.hb-yt-recent .hb-yt-rq')].filter(e => e.getClientRects().length)
                      .map(e => [e.textContent, !!e.querySelector('svg')])}; }""")
    assert vis["field"] and vis["focus"] and not vis["chips"] and not vis["find"], vis
    assert not vis["mini"], "the keyboard is up: the mini-player would float mid-screen"
    assert vis["rows"] == [[q, True] for q in _RECENT], "his recent searches, newest first, each with its clock"
    assert "hb-yt-t-inicio" in _cls(phone), "results land on Inicio"
    phone.fill(".hb-yt-search input", "paella")
    assert phone.eval_on_selector_all(".hb-yt-recent .hb-yt-rq", "els => els.map(e => e.textContent)") == ["paella valenciana"]
    phone.tap(".hb-yt-recent .hb-yt-rq")
    assert _calls(phone) == [["search", {"query": "paella valenciana"}]], "a recent row IS the voice's own search"


def test_a_search_in_flight_shows_skeletons_never_a_count_of_nothing(phone):
    _mount(phone, _playing(search_results=[], search_query="", adding="golden gate"))
    phone.tap(".hb-yt-tab[data-tab=inicio]")
    home = phone.evaluate("""() => ({skels: document.querySelectorAll('.hb-yt-home .hb-yt-skel').length,
        text: document.querySelector('.hb-yt-home').innerText.trim(), q: document.querySelector('.hb-yt-search input').value,
        pic: (() => { const r = document.querySelector('.hb-yt-skel .hb-yt-ithumb').getBoundingClientRect(); return r.width / r.height; })()})""")
    assert home["skels"] >= 3 and home["text"] == "" and abs(home["pic"] - 16 / 9) < 0.05, home
    assert home["q"] == "golden gate", "the question being answered is in the bar while it runs"


def test_results_are_one_column_of_full_width_pictures_and_the_more_button_opens_a_sheet_inside_the_card(phone):
    _mount(phone, _playing(search_results=_RES, search_query="golden gate", channels=[{"name": "C1"}]))
    phone.tap(".hb-yt-tab[data-tab=inicio]")
    geo = phone.evaluate("""() => { const body = document.querySelector('.hb-yt-body').getBoundingClientRect();
        const items = [...document.querySelectorAll('.hb-yt-home .hb-yt-item')].map(it => {
            const p = it.querySelector('.hb-yt-ithumb').getBoundingClientRect(), t = it.querySelector('.hb-yt-ititle').getBoundingClientRect();
            return {w: p.width, top: p.top, under: t.top >= p.bottom - 1, dur: (it.querySelector('.hb-yt-dur') || {}).textContent || "",
                    num: it.querySelector('.hb-yt-ititle .hb-yt-rnum').textContent}; });
        return {bw: body.width, items, badges: document.querySelectorAll('.hb-yt-ithumb button, .hb-yt-ithumb .hb-yt-rnum').length}; }""")
    its = geo["items"]
    assert len(its) == 3 and all(i["w"] >= geo["bw"] - 40 and i["under"] for i in its), geo
    assert its[1]["top"] > its[0]["top"] + 100, "one column: each picture under the last"
    assert [i["dur"] for i in its] == ["52:11", "", "1:02:45"] and [i["num"] for i in its] == ["1", "2", "3"]
    assert geo["badges"] == 0, "nothing laid over the picture but its length"
    phone.locator(".hb-yt-item").nth(0).locator(".hb-yt-more3").tap()
    sheet = phone.evaluate("""() => { const s = document.querySelector('.hb-yt-sheet'), c = document.querySelector('.hb-yt').getBoundingClientRect();
        const r = s.getBoundingClientRect(), sc = document.querySelector('.hb-yt-scrim').getBoundingClientRect();
        return {pos: getComputedStyle(s).position, z: +getComputedStyle(s).zIndex, inCard: r.bottom <= c.bottom + 1 && r.top >= c.top,
                foot: Math.abs(r.bottom - c.bottom) <= 1, scrim: sc.top >= c.top - 1 && sc.bottom <= c.bottom + 1,
                opts: [...s.querySelectorAll('[data-opt]')].map(e => e.dataset.opt)}; }""")
    assert sheet["pos"] != "fixed" and sheet["z"] <= 5 and sheet["inCard"] and sheet["foot"] and sheet["scrim"], sheet
    assert sheet["opts"] == ["play", "queue", "unfollow", "block"], "C1 is followed: the sheet offers to unfollow"
    phone.keyboard.press("Escape")
    assert phone.locator(".hb-yt-sheet").count() == 0
    phone.locator(".hb-yt-item").nth(2).locator(".hb-yt-more3").tap()
    phone.tap(".hb-yt-sheet [data-opt=block]")
    phone.locator(".hb-yt-item").nth(1).locator(".hb-yt-more3").tap()
    phone.tap(".hb-yt-scrim", position={"x": 20, "y": 20})
    assert phone.locator(".hb-yt-sheet").count() == 0, "a tap outside closes it"
    phone.locator(".hb-yt-item").nth(1).tap()
    assert _calls(phone) == [["block_channel", {"channel": "C3"}], ["play_result", {"item": "2"}]]
    assert "hb-yt-t-player" in _cls(phone)


def test_the_mini_player_is_one_slim_row_and_offers_sound_only_while_muted(phone):
    """The phone shell WRAPS any row of buttons (styles.css, so a toolbar never pushes the card sideways) — that wrap
    is what stacked the mini-player into a fifth of the screen. It is a `data-strip`, the shell's declared exception;
    measured here under the shell's own stylesheet."""
    _mount(phone, _playing(search_results=[], search_query="", muted=True))
    phone.add_style_tag(url="/frontend/mobile/app/styles.css")
    phone.tap(".hb-yt-tab[data-tab=inicio]")
    geo = phone.evaluate("""() => { const m = document.querySelector('.hb-yt-mini');
        const kids = [...m.children].filter(e => e.getClientRects().length && !e.classList.contains('hb-yt-mline'));
        const mid = (e) => { const r = e.getBoundingClientRect(); return r.top + r.height / 2; };
        return {h: m.getBoundingClientRect().height, row: Math.max(...kids.map(mid)) - Math.min(...kids.map(mid)),
                snd: !!m.querySelector('.snd').getClientRects().length, line: m.querySelector('.hb-yt-mline').getBoundingClientRect().height}; }""")
    assert geo["h"] <= 64 and geo["row"] <= 2 and geo["snd"] and 1 <= geo["line"] <= 3, geo
    _mount(phone, _playing(search_results=[], search_query="", muted=False))
    phone.tap(".hb-yt-tab[data-tab=inicio]")
    assert not phone.is_visible(".hb-yt-mini .snd"), "with sound on, the row is play/pause and next"


_ECHO = "<script>addEventListener('message', (e) => parent.postMessage('ECHO:' + e.data, '*'))</script>"


def test_the_watch_page_has_a_seek_bar_fed_by_the_players_clock_and_a_tap_seeks(phone):
    phone.route("**://www.youtube.com/**", lambda r: r.fulfill(status=200, content_type="text/html", body=_ECHO))
    _mount(phone, _playing(blocked_notice={}, list=_Q, pos=0, channels=[]))
    phone.evaluate("""() => { window.__echo = []; addEventListener('message', (e) => {
        if(typeof e.data === 'string' && e.data.startsWith('ECHO:')) window.__echo.push(e.data.slice(5)); }); }""")
    phone.evaluate("""() => window.postMessage(JSON.stringify({event: 'infoDelivery', id: 'hb-youtube',
                                                              info: {currentTime: 83, duration: 765}}), '*')""")
    phone.wait_for_function("document.querySelector('.hb-yt-stime').textContent === '1:23 / 12:45'")
    order = phone.evaluate("""() => ['.hb-yt-frame', '.hb-yt-seek', '.hb-yt-ctrls', '.hb-yt-title', '.hb-yt-wchips', '.hb-yt-upnext']
        .map(s => document.querySelector(s).getBoundingClientRect().top)""")
    assert order == sorted(order), "video → seek bar → controls → title → chips → up next"
    phone.wait_for_timeout(800)                                  # the embed's `load` + its 700 ms state push
    phone.evaluate("window.__echo = []")
    box = phone.locator(".hb-yt-strack").bounding_box()
    phone.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    phone.wait_for_function("window.__echo.some(m => m.includes('seekTo'))")
    seek = [m for m in phone.evaluate("window.__echo") if "seekTo" in m][0]
    assert '"args":[383,true]' in seek, seek
    assert phone.inner_text(".hb-yt-stime") == "6:23 / 12:45"
    assert _calls(phone) == [], "his hand on the player: no server action"
    phone.tap(".hb-yt-wchip[data-chip=captions]")
    phone.tap(".hb-yt-follow")
    phone.locator(".hb-yt-unrow").nth(0).tap()
    assert _calls(phone) == [["captions_on", {}], ["follow_channel", {"channel": "Free Documentary"}],
                             ["play_item", {"item": "2"}]], "Subtítulos · Seguir · the next row of the queue"


# ── the audit of 2026-11-17: what a re-render, a rebuild or the player's own clock must not undo ──────────────────

def _render(page, data):
    """A re-render on the same card, as the host's next frame of data does."""
    port = page._hb_port
    page.evaluate("""async ([src, data]) => { const mod = await import(src);
        mod.render(document.getElementById('w'), data, window.__ctx); }""",
                  [f"http://127.0.0.1:{port}/widgets/youtube/widget.js", data])


def _clock(page, cur, dur=765):
    page.evaluate("""([c, d]) => window.postMessage(JSON.stringify({event: 'infoDelivery', id: 'hb-youtube',
                                                                    info: {currentTime: c, duration: d}}), '*')""", [cur, dur])


def test_a_drag_on_the_seek_bar_is_his_until_he_lets_go_and_a_stopped_agent_seeks_nothing(phone):
    phone.route("**://www.youtube.com/**", lambda r: r.fulfill(status=200, content_type="text/html", body=_ECHO))
    _mount(phone, _playing(blocked_notice={}))
    phone.evaluate("""() => { window.__echo = []; addEventListener('message', (e) => {
        if(typeof e.data === 'string' && e.data.startsWith('ECHO:')) window.__echo.push(e.data.slice(5)); }); }""")
    _clock(phone, 76)
    phone.wait_for_function("document.querySelector('.hb-yt-stime').textContent === '1:16 / 12:45'")
    phone.wait_for_timeout(800)
    phone.evaluate("window.__echo = []")
    box = phone.locator(".hb-yt-strack").bounding_box()
    assert box["height"] >= 44, "a thumb's target, however thin the line it draws"
    y = box["y"] + box["height"] / 2
    phone.mouse.move(box["x"] + box["width"] * 0.5, y)
    phone.mouse.down()
    phone.mouse.move(box["x"] + box["width"] * 0.8, y)
    _clock(phone, 80)                                              # the player keeps talking under his finger
    phone.wait_for_timeout(150)
    knob = phone.evaluate("parseFloat(document.querySelector('.hb-yt-sknob').style.left)")
    assert abs(knob - 80) < 1.5, f"the knob snapped back to the clock mid-drag: {knob}%"
    phone.mouse.up()
    phone.wait_for_function("window.__echo.some(m => m.includes('seekTo'))")
    assert '"args":[612,true]' in [m for m in phone.evaluate("window.__echo") if "seekTo" in m][0]
    # a stopped agent: his tap moves no player (V2-092)
    phone.evaluate("window.__echo = []; window.__ctx.running = false")
    phone.mouse.click(box["x"] + box["width"] * 0.2, y)
    phone.wait_for_timeout(300)
    assert not [m for m in phone.evaluate("window.__echo") if "seekTo" in m]


def test_a_video_arriving_while_he_types_a_search_is_one_screen_with_its_way_back(phone):
    _mount(phone, _playing(videoId="", title="", channel="", search_results=[], search_query="", recent_queries=_RECENT))
    phone.tap(".hb-yt-find")
    assert "hb-yt-typing" in _cls(phone)
    _render(phone, _playing(search_results=[], search_query="", recent_queries=_RECENT))
    cls = _cls(phone)
    assert "hb-yt-t-player" in cls and "hb-yt-typing" not in cls and "hb-yt-smode" not in cls, cls
    assert not phone.is_visible(".hb-yt-search") and not phone.is_visible(".hb-yt-recent")
    assert phone.is_visible(".hb-yt-down"), "the watch page's ⌄ is there"


def test_a_rebuild_keeps_what_he_is_typing_and_where_his_cursor_is(phone):
    _mount(phone, _playing(search_results=[], search_query="", recent_queries=_RECENT))
    phone.tap(".hb-yt-tab[data-tab=inicio]")
    phone.tap(".hb-yt-find")
    phone.keyboard.type("regat")
    _render(phone, _playing(videoId="NNNNNNNNNN2", title="The next one", search_results=[], search_query="",
                            recent_queries=_RECENT))                 # the queue moved on: a new player, a new bar
    st = phone.evaluate("""() => { const i = document.querySelector('.hb-yt-search input');
        return {v: i.value, focus: document.activeElement === i, cls: document.querySelector('.hb-yt').className}; }""")
    assert st["v"] == "regat" and st["focus"] and "hb-yt-typing" in st["cls"], st
    phone.keyboard.type("as")
    assert phone.input_value(".hb-yt-search input") == "regatas"


def test_an_open_sheet_closes_when_the_rows_under_it_change(phone):
    q = [{"videoId": "QQQQQQQQQQ%d" % i, "title": "Clip %d" % i, "channel": "Solo Fonseca"} for i in range(1, 5)]
    _mount(phone, _playing(list=q, pos=0))
    phone.tap(".hb-yt-tab[data-tab=cola]")
    more = phone.evaluate("""() => { const b = document.querySelectorAll('.hb-yt-list .hb-yt-qmore')[2].getBoundingClientRect();
        return [b.width, b.height]; }""")
    assert min(more) >= 44, f"the ⋮ is a thumb's target: {more}"
    phone.locator(".hb-yt-list .hb-yt-qmore").nth(2).tap()
    _render(phone, _playing(list=q, pos=0, paused=True))           # the same rows: the sheet stays
    assert phone.locator(".hb-yt-sheet").count() == 1
    phone.keyboard.press("Escape")
    assert phone.evaluate("document.activeElement === document.querySelectorAll('.hb-yt-list .hb-yt-qmore')[2]"), \
        "the focus goes back to the ⋮ that opened it"
    phone.locator(".hb-yt-list .hb-yt-qmore").nth(2).tap()
    _render(phone, _playing(list=q[1:], pos=0))                    # the voice removed the first row
    assert phone.locator(".hb-yt-sheet").count() == 0, "«Quitar» on row 3 would now remove another video"

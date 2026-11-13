"""The page player says when the browser keeps it silent, and offers the tap that fixes it (V2-812, V2-884 step 2).

When the music plays in the page of the screen that asked (no device of the connected account sits with it), it
starts muted — the only autoplay every browser allows — and is unmuted a moment later. A phone browser may refuse
that unmute, or refuse to start at all, until a real tap. Before, the store said «playing», the card drew the song
and the agent said «it's playing» over a silent phone. Now the card's page player REPORTS what it does through the
card's one state door (whether it plays, which song, its sound and volume — the protocol every card's player shares,
`/frontend/app/lib/player-report.js`); sound wanted and the player silent or not playing is the FACT `audio_blocked`,
derived on every read and never stored: the card shows a tap row from it, the brain's state line says it, and its
declared tell reaches him only over an agent order (`late_report`). A refused song, a pause or his own mute is not a
blocked browser. Disarmed (named) → red.
"""
from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys

import pytest

from widgets.musica import data as md

from tests.browser.unit.musica.page_player import page_player

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def store_tmp(monkeypatch, tmp_path):
    import widgets.store as store
    from connectors.spotify import auth
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))   # the store's own layout: `has_state` reads it too
    monkeypatch.setattr(auth, "status", lambda: {"logged_in": True, "can_connect": True})
    import widgets.store as st
    st.save("musica", {"yt": {"videoId": "VID00000001", "title": "Dai Dai", "paused": False, "cmd_seq": 3,
                              "volume": 70}, "source": {"provider": "youtube", "screen": "mobile:aa11"}})


def test_a_silent_page_player_is_the_fact_and_a_heard_one_clears(store_tmp, monkeypatch):
    from widgets import state_render
    says = page_player(monkeypatch)
    assert says(playing=True, playing_id="VID00000001", muted=True, volume=70)["facts"] == ["audio_blocked"]
    assert "audio_blocked" in state_render.read("musica")["surfaces"][0]["facts"]
    assert says(muted=False)["facts"] == [], "a heard player clears it on its own report"
    assert says(playing=False)["facts"] == ["audio_blocked"], "a page that never starts the song is silent too"
    assert "audio_blocked" not in md._load_db()["yt"], "a silence is a fact, never a stored flag"


@pytest.mark.parametrize("order", [{"paused": True}, {"muted": True}, {"player_error": "150"}])
def test_a_pause_his_mute_or_a_refused_song_is_not_a_blocked_browser(store_tmp, monkeypatch, order):
    db = md._load_db()
    db["yt"].update(order)
    md._persist(db)
    says = page_player(monkeypatch)
    assert says(playing=False, playing_id="VID00000001", muted=True)["facts"] == []


def test_the_page_player_is_what_the_card_shows_even_with_spotify_connected(store_tmp):
    live = md._live_fields(md._load_db())
    assert live["mode"] == "youtube" and live["now_playing"] is None, (
        "the song sounds in the page: a Spotify reading of a device elsewhere is not what he hears")


def test_the_brain_reads_where_it_sounds_and_that_it_is_silent(store_tmp, monkeypatch):
    from nucleo.flash import widget_read
    d = md.prompt_digest()
    assert "Dai Dai" in d and "page player" in d and "phone" in d
    assert "volume 70%" not in d and "playing" not in d, "the ORDER is never painted as what the page player does"
    page_player(monkeypatch)(playing=True, playing_id="VID00000001", muted=True, volume=70)
    got = widget_read.read("musica")
    assert "musica@phone: playing, playing_id=VID00000001, muted, volume=70 · facts: audio_blocked" in got, got
    man = json.load(open("widgets/musica/manifest.json", encoding="utf-8"))
    assert man["state"]["facts"]["audio_blocked"]["tell"] == "music.audio_blocked"
    assert "player_audio" not in man["actions"], "the store-written report is retired"


# ── the card, rendered ───────────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def _page():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    from tests.waiting import port_listening
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_listening(port)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page._hb_port = port
            yield page
            browser.close()
    finally:
        srv.terminate()


def _data(**yt):
    y = {"videoId": "VID00000001", "title": "Dai Dai", "artist": "Shakira", "paused": False, "cmd_seq": 1,
         "art": "", "volume": 70}
    y.update(yt)
    return {"connected": True, "mode": "youtube", "now_playing": None, "yt": y, "local": {}, "playlists": [],
            "recent": [], "counts": {}, "top": [], "fav_current": False, "fav": {"id": "", "name": "Favoritos"},
            "modes": {"shuffle": False, "repeat": "off", "supported": True}, "volume": {"level": 70, "muted": False},
            "queue": {"items": [], "editable": True, "source": "youtube"}, "browse": {},
            "view": {"kind": "home", "id": ""}}


def _mount(page, data):
    """The real card; `ctx.state` keeps every report and answers the facts the test sets (`window.__facts`)."""
    port = page._hb_port
    page.goto(f"http://127.0.0.1:{port}/widgets/musica/")
    page.set_content("<div style='width:420px;height:520px;display:flex;flex-direction:column'><div id='w'></div></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = []; window.__states = []; window.__facts = [];
             const mod = await import(src);
             window.__ctx = {action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve({ok: true}); },
                             state: (p, o) => { window.__states.push([p, o || {}]); return Promise.resolve(window.__facts); },
                             running: true};
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""", [f"http://127.0.0.1:{port}/widgets/musica/widget.js", data])


def _player_says(page, info):
    page.evaluate("(info) => window.dispatchEvent(new MessageEvent('message', {data: JSON.stringify("
                  "{event: 'infoDelivery', id: 'hb-musica', info})}))", info)


def _said(page, field):
    return [p[field] for p, _o in page.evaluate("() => window.__states") if field in p]


def test_the_page_player_says_what_it_does_through_the_door(_page):
    _mount(_page, _data())
    _player_says(_page, {"muted": False, "playerState": 1, "volume": 70, "videoData": {"video_id": "VID00000001"}})
    _page.wait_for_timeout(50)
    p = _page.evaluate("() => window.__states")[-1][0]
    assert p == {"playing": True, "muted": False, "volume": 70, "playing_id": "VID00000001"}, p
    assert not [c for c in _page.evaluate("() => window.__calls") if c[0] == "player_audio"], "the old store report"


def test_the_blocked_fact_shows_the_tap_and_its_end_hides_it(_page):
    _mount(_page, _data())
    _page.evaluate("() => { window.__facts = ['audio_blocked']; }")    # what the door answers from now on
    _player_says(_page, {"muted": True, "playerState": 1})
    _page.wait_for_timeout(100)
    tap = _page.query_selector(".hb-mus2-tapsound")
    assert tap is not None and tap.is_visible(), "the app says the browser keeps it silent and offers the tap"
    _page.evaluate("() => { window.__facts = []; }")
    _player_says(_page, {"muted": False, "playerState": 1})
    _page.wait_for_timeout(100)
    assert _page.query_selector(".hb-mus2-tapsound") is None


def test_a_player_that_never_says_a_word_says_it_does_not_play_and_acks(_page):
    """2026-11-02: on a phone the embed sent no `infoDelivery` at all — no report, no tap row, the song mute through six
    volume changes. A player that never speaks says it does not play, and the revision is acked so the fact is read."""
    _page.route("**/*youtube*/**", lambda route: route.abort())
    try:
        _mount(_page, {**_data(videoId="VIDQUIET001"), "_rev": {"epoch": "e1", "rev": 4}})
        _page.wait_for_timeout(7000)
        states = _page.evaluate("() => window.__states")
        assert any(o.get("applied") for _p, o in states), states
        assert _said(_page, "playing") and all(v is False for v in _said(_page, "playing")), states
    finally:
        _page.unroute("**/*youtube*/**")


def test_a_released_player_acks_what_was_rendered(_page):
    """The song ends with nothing after it: no player is left to speak, so the revision that emptied it is acked on its
    own grace — else the order «nothing plays» would read unconfirmed for ever."""
    _mount(_page, {**_data(), "_rev": {"epoch": "e1", "rev": 4}})
    _page.evaluate("""async (d) => { const mod = await import('/widgets/musica/widget.js');
                         mod.render(document.getElementById('w'), d, window.__ctx); }""",
                   {**_data(videoId=""), "yt": {}, "_rev": {"epoch": "e1", "rev": 5}})
    _page.wait_for_timeout(1800)
    states = _page.evaluate("() => window.__states")
    assert any(o.get("applied") for _p, o in states), states


def test_a_message_from_another_frame_is_not_the_current_player(_page):
    _mount(_page, _data())
    n = len(_page.evaluate("() => window.__states"))
    _page.evaluate("""() => { const f = document.createElement('iframe'); document.body.appendChild(f);
        window.dispatchEvent(new MessageEvent('message', {source: f.contentWindow, data: JSON.stringify(
          {event: 'infoDelivery', id: 'hb-musica', info: {playerState: 1, muted: false}})})); }""")
    _page.wait_for_timeout(50)
    assert len(_page.evaluate("() => window.__states")) == n, "a replaced player's queued message spoke for the new one"

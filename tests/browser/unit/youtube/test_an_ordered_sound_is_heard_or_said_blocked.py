"""V2-791 · A video ordered to be watched plays WITH sound when the page allows it, and says so when it does not.

Measured (one session): «pon el vídeo de Madonna Like a Prayer» loaded fine and played silent — the store's seed is
`muted: true` (the autoplay policy) and `load` never touched it. «No se oye el vídeo» → the model called `unmute`;
the store flipped to `muted: false`, the card hid its «tap for sound» hint, and nothing ever checked whether the
embedded player obeyed: a cross-origin player can be unmuted from a voice order only once the page has had a real
gesture.

  · data: a video he asked to watch wants sound, unless the last word on sound was HIS mute;
  · data: what was ORDERED stays in the store; what is HEARD is the player's report through the card's state door, and
    «blocked» is the fact derived from both (V2-884 1a — its server half is
    `test_the_player_reports_what_it_shows.py`); `player_audio` only carries his hand on the player's own control;
  · card (rendered): the player's sound, volume and play state reach `ctx.state` on every change, the hint follows the
    facts the door answers, a new revision is acked by a full snapshot once applied, and his hand unmutes the card.
"""
from __future__ import annotations

import io
import json
import pathlib
import socket
import subprocess
import sys
import urllib.request

import pytest

from widgets import store
from widgets.youtube import data as yt

_V1, _V2 = "dQw4w9WgXcQ", "9bZkp7q19f0"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=6: io.BytesIO(
        json.dumps({"title": "Like a Prayer", "author_name": "Madonna"}).encode()))
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: "es")


# ── data: what was ordered ───────────────────────────────────────────────────────────────────────────────

def test_a_video_he_asks_to_watch_wants_sound():
    assert yt.view_data()["muted"] is True, "the seed is the autoplay policy's silence"
    r = yt.apply_action("load", {"videoId": _V1})
    assert r["muted"] is False and yt.view_data()["muted"] is False


def test_his_own_mute_survives_the_next_video():
    yt.apply_action("load", {"videoId": _V1})
    yt.apply_action("mute", {})
    yt.apply_action("load", {"videoId": _V2})
    assert yt.view_data()["muted"] is True, "a mute he gave is his, not the policy's"
    yt.apply_action("unmute", {})
    yt.apply_action("load", {"videoId": _V1})
    assert yt.view_data()["muted"] is False


def test_a_queue_item_he_plays_wants_sound_too():
    yt.apply_action("add", {"url": f"https://youtu.be/{_V1} https://youtu.be/{_V2}"})
    yt.apply_action("play_item", {"item": "2"})
    assert yt.view_data()["muted"] is False


# ── data: what the player lets be heard (the fact itself: test_the_player_reports_what_it_shows.py) ──────────

def test_a_report_through_player_audio_stores_no_flag_and_tells_nothing():
    yt.apply_action("load", {"videoId": _V1})
    r = yt.apply_action("player_audio", {"muted": True, "videoId": _V1})
    assert not r.get("tell") and "audio_blocked" not in yt.view_data()


def test_he_unmuted_from_the_players_own_control_and_the_card_follows():
    yt.apply_action("load", {"videoId": _V1})
    yt.apply_action("mute", {})
    yt.apply_action("player_audio", {"muted": False, "videoId": _V1})
    assert yt.view_data()["muted"] is False


def test_a_report_about_another_video_is_stale():
    yt.apply_action("load", {"videoId": _V1})
    yt.apply_action("mute", {})
    assert yt.apply_action("player_audio", {"muted": False, "videoId": _V2}).get("stale")
    assert yt.view_data()["muted"] is True


def test_the_report_is_declared_as_internal():
    man = json.loads((pathlib.Path(yt.__file__).parent / "manifest.json").read_text(encoding="utf-8"))
    assert man["actions"]["player_audio"]["desc"].startswith("Internal:")


# ── the card, rendered ──────────────────────────────────────────────────────────────────────────────────

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close(); return port


@pytest.fixture(scope="module")
def _page():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    from tests.waiting import port_listening
    port_listening(port)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.route("**://i.ytimg.com/**", lambda r: r.fulfill(status=200, content_type="image/gif", body=b"GIF89a"))
            page.route("**://www.youtube.com/**",
                       lambda r: r.fulfill(status=200, content_type="text/html", body="<html></html>"))
            page._hb_url = f"http://127.0.0.1:{port}/widgets/youtube/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/youtube/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _data(**over):
    d = {"videoId": _V1, "title": "Like a Prayer", "channel": "Madonna", "published": "hace 2 horas",
         "volume": 70, "muted": False, "captions": False, "paused": False,
         "last_cmd": "load", "cmd_seq": 1, "loading": False, "loading_query": "", "list": [], "player_error": "",
         "pos": -1, "adding": "", "list_filter": "", "list_name": "", "blocked_channels": [], "platforms": [],
         "platforms_at": 0, "suggested": [], "search_results": [], "search_query": "", "channels": [],
         "history": [], "prefs": {}, "lists": [], "platforms_stale": False, "accounts_enabled": False,
         "connector_shelf": []}
    d.update(over)
    return d


def _mount(page, data):
    page.goto(page._hb_origin)
    page.set_content("<div id='w' style='width:660px'></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = []; window.__states = []; window.__facts = window.__facts || [];
             const mod = await import(src);
             window.__mod = mod; window.__ctx = {
               action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve({ok: true}); },
               state: (p, o) => { window.__states.push([p || {}, o || {}]); return Promise.resolve(window.__facts); },
               top: () => {}, running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""", [page._hb_url, data])


def _remount(page, data):
    page.evaluate("(d) => window.__mod.render(document.getElementById('w'), d, window.__ctx)", data)


def _hint_shown(page) -> bool:
    return page.evaluate("() => { const h = document.querySelector('.hb-yt-unmute');"
                         " return !!h && getComputedStyle(h).display !== 'none'; }")


def _audio_reports(page):
    return page.evaluate("() => window.__calls.filter(c => c[0] === 'player_audio').map(c => c[1])")


def _player_says(page, muted: bool, until="() => window.__states.some(s => 'muted' in s[0])"):
    """The real player repeats `infoDelivery` several times a second; so does this, until the card reports."""
    page.evaluate("""([vid, m]) => { window.__tick = setInterval(() => window.postMessage(JSON.stringify(
                       {event: 'infoDelivery', id: 'hb-youtube', info: {muted: m, volume: 64,
                        videoData: {video_id: vid}}}), '*'), 200); }""", [_V1, muted])
    try:
        page.wait_for_function(until, timeout=5000)
    finally:
        page.evaluate("() => clearInterval(window.__tick)")


def _states(page):
    return page.evaluate("() => window.__states")


def test_the_players_sound_reaches_the_state_door_and_the_hint_follows_the_facts(_page):
    _mount(_page, _data())
    _page.evaluate("() => { window.__facts = ['audio_blocked']; }")    # what the door answers (after the mount)
    _player_says(_page, True)
    assert any(p.get("muted") is True and p.get("volume") == 64 for p, _o in _states(_page)), _states(_page)
    _page.wait_for_function("() => { const h = document.querySelector('.hb-yt-unmute');"
                            " return !!h && getComputedStyle(h).display !== 'none'; }", timeout=3000)
    _page.evaluate("() => { window.__facts = []; }")
    _player_says(_page, False, until="() => window.__states.some(s => s[0].muted === false)")
    _page.wait_for_function("() => getComputedStyle(document.querySelector('.hb-yt-unmute')).display === 'none'",
                            timeout=3000)
    assert not _audio_reports(_page), "a silence was sent as an action, not reported"


def test_a_repeated_report_is_sent_once(_page):
    """The real player repeats the same `infoDelivery` several times a second: one report, not one per message."""
    _mount(_page, _data())
    _page.evaluate("""(vid) => { for (let i = 0; i < 5; i++) window.postMessage(JSON.stringify(
                       {event: 'infoDelivery', id: 'hb-youtube', info: {muted: true, volume: 64,
                        videoData: {video_id: vid}}}), '*'); }""", _V1)
    _page.wait_for_timeout(500)
    assert sum(1 for p, _o in _states(_page) if "muted" in p) == 1, _states(_page)


def test_a_new_revision_is_acked_by_a_full_snapshot_once_applied(_page):
    _mount(_page, _data(_rev={"epoch": "e1", "rev": 7}))
    _player_says(_page, False, until="() => window.__states.some(s => s[0].muted === false)")
    _page.wait_for_function("() => window.__states.some(s => s[1].applied)", timeout=4000)
    full = next(p for p, o in _states(_page) if o.get("applied"))
    assert {"view", "muted", "volume"} <= set(full), full


def test_his_hand_on_the_players_own_control_unmutes_the_card(_page):
    _mount(_page, _data(muted=True))
    _player_says(_page, False, until="() => window.__calls.some(c => c[0] === 'player_audio')")
    assert {"muted": False, "videoId": _V1} in _audio_reports(_page)

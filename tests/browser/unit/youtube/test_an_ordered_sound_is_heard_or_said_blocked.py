"""V2-791 · A video ordered to be watched plays WITH sound when the page allows it, and says so when it does not.

Measured (one session): «pon el vídeo de Madonna Like a Prayer» loaded fine and played silent — the store's seed is
`muted: true` (the autoplay policy) and `load` never touched it. «No se oye el vídeo» → the model called `unmute`;
the store flipped to `muted: false`, the card hid its «tap for sound» hint, and nothing ever checked whether the
embedded player obeyed: a cross-origin player can be unmuted from a voice order only once the page has had a real
gesture.

  · data: a video he asked to watch wants sound, unless the last word on sound was HIS mute;
  · data: the player's own report (`player_audio`) separates what was ORDERED from what is HEARD — sound wanted and
    the player silent is `audio_blocked`, with a `tell` for the late-report seam and a line for the brain;
  · card (rendered): the hint stays while sound is blocked, and a voice `unmute` on a page with no gesture REPORTS
    the block instead of letting the store claim a sound the player cannot have.
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


# ── data: what the player lets be heard ─────────────────────────────────────────────────────────────────

def test_sound_ordered_and_the_player_silent_is_blocked_and_told():
    yt.apply_action("load", {"videoId": _V1})
    yt.apply_action("unmute", {})
    r = yt.apply_action("player_audio", {"muted": True, "videoId": _V1})
    assert r["audio_blocked"] is True and yt.view_data()["audio_blocked"] is True
    assert "navegador" in r.get("tell", ""), r
    assert "BLOQUEADO" in yt.prompt_digest(), "the brain must not say it is heard"
    again = yt.apply_action("player_audio", {"muted": True, "videoId": _V1})
    assert not again.get("tell"), "told once, not on every report"


def test_an_english_session_hears_it_in_english(monkeypatch):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: "en")
    yt.apply_action("load", {"videoId": _V1})
    assert "browser" in yt.apply_action("player_audio", {"muted": True, "videoId": _V1}).get("tell", "")


def test_the_player_heard_clears_the_block():
    yt.apply_action("load", {"videoId": _V1})
    yt.apply_action("player_audio", {"muted": True, "videoId": _V1})
    yt.apply_action("player_audio", {"muted": False, "videoId": _V1})
    assert yt.view_data()["audio_blocked"] is False
    assert "BLOQUEADO" not in yt.prompt_digest()


def test_a_muted_player_he_muted_is_not_blocked():
    yt.apply_action("load", {"videoId": _V1})
    yt.apply_action("mute", {})
    r = yt.apply_action("player_audio", {"muted": True, "videoId": _V1})
    assert not r.get("audio_blocked") and not r.get("tell")


def test_he_unmuted_from_the_players_own_control_and_the_card_follows():
    yt.apply_action("load", {"videoId": _V1})
    yt.apply_action("mute", {})
    yt.apply_action("player_audio", {"muted": False, "videoId": _V1})
    assert yt.view_data()["muted"] is False


def test_a_report_about_another_video_is_stale():
    yt.apply_action("load", {"videoId": _V1})
    assert yt.apply_action("player_audio", {"muted": True, "videoId": _V2}).get("stale")
    assert yt.view_data()["audio_blocked"] is False


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
         "volume": 70, "muted": False, "audio_blocked": False, "captions": False, "paused": False,
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
             window.__calls = [];
             const mod = await import(src);
             window.__mod = mod; window.__ctx = {
               action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve({ok: true}); },
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


def _player_says(page, muted: bool):
    """The real player repeats `infoDelivery` several times a second; so does this, until the card reports."""
    page.evaluate("""([vid, m]) => { window.__tick = setInterval(() => window.postMessage(JSON.stringify(
                       {event: 'infoDelivery', id: 'hb-youtube', info: {muted: m, videoData: {video_id: vid}}}), '*'),
                       200); }""", [_V1, muted])
    try:
        page.wait_for_function("() => window.__calls.some(c => c[0] === 'player_audio')", timeout=5000)
    finally:
        page.evaluate("() => clearInterval(window.__tick)")


def test_the_hint_stays_while_an_ordered_sound_is_blocked(_page):
    _mount(_page, _data(audio_blocked=True))
    assert _hint_shown(_page), "sound ordered and kept silent: the card must say how to get it"
    _remount(_page, _data(audio_blocked=False))
    assert not _hint_shown(_page)


def test_a_voice_unmute_on_a_page_with_no_gesture_reports_the_block(_page):
    """No click has happened on this page (`navigator.userActivation.hasBeenActive` is false): the voice order
    cannot give the player sound, and the card reports it instead of trusting the store. Playwright's own
    `evaluate` counts as a gesture, so the page's activation state is pinned to «never active» here."""
    _mount(_page, _data(muted=True, last_cmd="load", cmd_seq=1))
    _page.evaluate("() => Object.defineProperty(navigator, 'userActivation', {configurable: true,"
                   " value: {hasBeenActive: false, isActive: false}})")
    assert not _page.evaluate("() => navigator.userActivation.hasBeenActive"), "precondition: no gesture yet"
    _remount(_page, _data(muted=False, last_cmd="unmute", cmd_seq=2))
    assert {"muted": True, "videoId": _V1} in _audio_reports(_page)


def test_the_player_reporting_silence_past_the_grace_is_reported(_page):
    _mount(_page, _data())
    _player_says(_page, True)
    assert {"muted": True, "videoId": _V1} in _audio_reports(_page)


def test_the_player_heard_clears_a_stored_block(_page):
    _mount(_page, _data(audio_blocked=True))
    _player_says(_page, False)
    assert {"muted": False, "videoId": _V1} in _audio_reports(_page)

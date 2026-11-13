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

def test_no_card_action_reports_the_sound_any_more():
    """V2-884 1b: the player's sound is its reported state, and his hand on the player is adopted by the state door
    (`test_his_hand_on_the_player_is_the_order.py`) — no card action carries either."""
    man = json.loads((pathlib.Path(yt.__file__).parent / "manifest.json").read_text(encoding="utf-8"))
    assert "player_audio" not in man["actions"] and man["actions"]["player_adopt"]["internal"] is True
    yt.apply_action("load", {"videoId": _V1})
    assert "audio_blocked" not in yt.view_data()


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


_NEW_MOUNT = """async () => {
  const R = await import('/frontend/app/widgets/state-reporter.js?v=1');
  if (window.__rep) window.__rep.dispose();
  const stub = async (u, init) => { const b = JSON.parse(init.body); window.__posts.push(b);
      return {status: 200, json: async () => ({ok: true, facts: window.__facts})}; };
  const rep = window.__rep = R.stateReporter('youtube', 'youtube', {device: 'desktop:aaa',
    fetch: window.__realDoor ? undefined : stub});
  window.__ctx = {
    action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve({ok: true}); },
    state: (p, o) => rep.report(p, o), top: () => {}, running: true };
}"""


def _mount(page, data):
    """The real card with the REAL reporter (`frontend/app/widgets/state-reporter.js`): only `fetch` is a stand-in, so
    what reaches the engine's door is what the product would send."""
    page.goto(page._hb_origin)
    page.set_content("<div id='w' style='width:660px'></div>")
    page.evaluate("() => { window.__calls = []; window.__posts = []; window.__facts = []; }")
    page.evaluate(_NEW_MOUNT)
    page.evaluate("""async ([src, data]) => { const mod = await import(src); window.__mod = mod;
                       window.__rep.seen(data._rev);                   // what the host does with each data push
                       mod.render(document.getElementById('w'), data, window.__ctx); }""", [page._hb_url, data])


def _reopen(page, data):
    """The card closed and opened again on the same page: a new mount, the module (and its memory) cached."""
    page.evaluate(_NEW_MOUNT)
    page.evaluate("""(d) => { const el = document.getElementById('w'); el.innerHTML = ''; el._hbYt = null;
                       el._hbYtBuilt = false; window.__rep.seen(d._rev); window.__mod.render(el, d, window.__ctx); }""",
                  data)


def _remount(page, data):
    page.evaluate("(d) => { window.__rep.seen(d._rev); window.__mod.render(document.getElementById('w'), d, window.__ctx); }",
                  data)


def _hint_shown(page) -> bool:
    return page.evaluate("() => { const h = document.querySelector('.hb-yt-unmute');"
                         " return !!h && getComputedStyle(h).display !== 'none'; }")


def _audio_reports(page):
    return page.evaluate("() => window.__calls.filter(c => c[0] === 'player_audio').map(c => c[1])")


def _posts(page):
    return page.evaluate("() => window.__posts")


def _player_says(page, muted: bool, until="() => window.__posts.some(b => 'muted' in b.patch)", vid=_V1):
    """The real player repeats `infoDelivery` several times a second; so does this, until the door hears it."""
    page.evaluate("""([vid, m]) => { window.__tick = setInterval(() => window.postMessage(JSON.stringify(
                       {event: 'infoDelivery', id: 'hb-youtube', info: {muted: m, volume: 64,
                        videoData: {video_id: vid}}}), '*'), 200); }""", [vid, muted])
    try:
        page.wait_for_function(until, timeout=5000)
    finally:
        page.evaluate("() => clearInterval(window.__tick)")


def test_the_players_sound_reaches_the_door_and_the_hint_follows_the_facts(_page):
    _mount(_page, _data())
    _page.evaluate("() => { window.__facts = ['audio_blocked']; }")    # what the door answers
    _player_says(_page, True)
    assert any(b["patch"].get("muted") is True and b["patch"].get("volume") == 64 for b in _posts(_page))
    _page.wait_for_function("() => { const h = document.querySelector('.hb-yt-unmute');"
                            " return !!h && getComputedStyle(h).display !== 'none'; }", timeout=3000)
    _page.evaluate("() => { window.__facts = []; }")
    _player_says(_page, False, until="() => window.__posts.some(b => b.patch.muted === false)")
    _page.wait_for_function("() => getComputedStyle(document.querySelector('.hb-yt-unmute')).display === 'none'",
                            timeout=3000)
    assert not _audio_reports(_page), "a silence was sent as an action, not reported"


def test_a_repeated_report_reaches_the_door_once(_page):
    """The real player repeats the same `infoDelivery` several times a second: one report, not one per message."""
    _mount(_page, _data())
    _page.evaluate("""(vid) => { for (let i = 0; i < 5; i++) window.postMessage(JSON.stringify(
                       {event: 'infoDelivery', id: 'hb-youtube', info: {muted: true, volume: 64,
                        videoData: {video_id: vid}}}), '*'); }""", _V1)
    _page.wait_for_timeout(500)
    assert sum(1 for b in _posts(_page) if "muted" in b["patch"]) == 1, _posts(_page)


def test_a_card_reopened_on_the_same_page_says_everything_again(_page):
    _mount(_page, _data())
    _player_says(_page, True)
    _reopen(_page, _data())
    _player_says(_page, True, until="() => window.__posts.filter(b => b.patch.muted === true).length >= 2")
    second = [b for b in _posts(_page) if b["n"] >= 1 and b["mount"] == _page.evaluate("() => window.__rep.mount")]
    assert any(b["patch"].get("muted") is True for b in second), "the reopened card did not say the player is silent"
    assert any(b["patch"].get("view") == "player" for b in second), "the reopened card did not say its face"


def test_a_new_revision_is_acked_by_a_full_snapshot_once_the_player_spoke(_page):
    _mount(_page, _data(_rev={"epoch": "e1", "rev": 7}))
    _page.wait_for_timeout(1800)
    assert not any(b["ack"] for b in _posts(_page)), "acked before the player had said anything"
    _player_says(_page, False, until="() => window.__posts.some(b => b.patch.muted === false)")
    _page.wait_for_function("() => window.__posts.some(b => b.ack && b.ack.rev === 7)", timeout=4000)
    full = next(b for b in _posts(_page) if b["ack"] and b["ack"]["rev"] == 7)
    assert full["full"] and {"view", "muted", "volume"} <= set(full["patch"]), full


def test_another_video_forgets_the_old_player_and_waits_for_the_new_one(_page):
    _mount(_page, _data(_rev={"epoch": "e1", "rev": 7}))
    _player_says(_page, False, until="() => window.__posts.some(b => b.patch.muted === false)")
    _page.wait_for_function("() => window.__posts.some(b => b.ack && b.ack.rev === 7)", timeout=4000)
    n0 = len(_posts(_page))
    _remount(_page, _data(videoId=_V2, title="Otro", cmd_seq=2, _rev={"epoch": "e1", "rev": 8}))
    _page.wait_for_timeout(1900)                         # the new player is slow: nothing acks rev 8 meanwhile
    after = _posts(_page)[n0:]
    assert any(b["patch"].get("playing") is False and b["patch"].get("muted", "gone") is None for b in after), after
    assert not any(b["ack"] and b["ack"]["rev"] == 8 for b in after), "rev 8 acked with the OLD player's state"
    _player_says(_page, True, vid=_V2, until="() => window.__posts.some(b => b.ack && b.ack.rev === 8)")
    acked = next(b for b in _posts(_page) if b["ack"] and b["ack"]["rev"] == 8)
    assert acked["patch"].get("muted") is True and "playing_id" not in acked["patch"] or \
        acked["patch"].get("playing_id") == _V2, acked


def test_nothing_is_reported_after_the_card_closed(_page):
    _mount(_page, _data(_rev={"epoch": "e1", "rev": 7}))
    _player_says(_page, True)
    _page.evaluate("() => window.__rep.dispose()")
    n0 = len(_posts(_page))
    _page.evaluate("""(vid) => window.postMessage(JSON.stringify({event: 'infoDelivery', id: 'hb-youtube',
                       info: {muted: false, volume: 10, videoData: {video_id: vid}}}), '*')""", _V1)
    _page.wait_for_timeout(1900)
    assert len(_posts(_page)) == n0, "a closed card kept reporting (and would recreate what the close forgot)"


def test_the_face_he_sees_is_reported_after_an_order_and_on_his_click(_page):
    _mount(_page, _data())
    _remount(_page, _data(goto_tab={"seq": 5, "tab": "inicio"}))
    _page.wait_for_function("() => window.__posts.length && window.__posts.some(b => b.patch.view === 'inicio')",
                            timeout=3000)
    _page.wait_for_timeout(300)
    views = [b["patch"]["view"] for b in _posts(_page) if "view" in b["patch"]]
    assert views[-1] == "inicio", views
    _page.evaluate("() => document.getElementById('w')._hbYtSelectTab('cola')")
    _page.wait_for_function("() => window.__posts.some(b => b.patch.view === 'cola')", timeout=3000)


def test_his_hand_on_the_player_is_reported_never_sent_as_an_action(_page):
    _mount(_page, _data(muted=True))
    _player_says(_page, False, until="() => window.__posts.some(b => b.patch.muted === false)")
    assert not _audio_reports(_page) and not _page.evaluate("() => window.__calls.length"), \
        "his hand reached the card as an action instead of the state door's adoption"


def test_the_card_the_reporter_and_the_door_together(_page, monkeypatch):
    """No stand-in between the card and the engine: the real widget, the real reporter, and the request answered by the
    engine's own door (`widgets.state.report`) — the seam a double on either side cannot see (audit P2-6)."""
    from server import canvas_api
    from voice import screens
    from widgets import state, state_render
    state._reset_for_tests()
    screens._reset_for_tests()
    screens.attach("desktop:aaa")
    monkeypatch.setattr(canvas_api, "_BY_DEV", {"desktop:aaa": {"open": ["youtube"]}})
    screens.note_playing("youtube", "desktop:aaa")
    yt.apply_action("load", {"videoId": _V1})
    seen = []

    def _door(route):
        body = json.loads(route.request.post_data or "{}")
        seen.append(body)
        code, out = state.report("youtube", body)
        out.pop("_on", None), out.pop("_off", None)
        route.fulfill(status=code, content_type="application/json", body=json.dumps(out))
    _page.route("**/widgets/youtube/state", _door)
    try:
        _page.goto(_page._hb_origin)
        _page.evaluate("() => { window.__realDoor = true; }")
        _page.set_content("<div id='w' style='width:660px'></div>")
        _page.evaluate("() => { window.__calls = []; window.__posts = []; window.__facts = []; window.__realDoor = true; }")
        _page.evaluate(_NEW_MOUNT)
        data = {**yt.view_data(), "_rev": state.stamp("youtube")}
        _page.evaluate("""async ([src, data]) => { const mod = await import(src); window.__mod = mod;
                           window.__rep.seen(data._rev); mod.render(document.getElementById('w'), data, window.__ctx); }""",
                       [_page._hb_url, data])
        _page.evaluate("""(vid) => { window.postMessage(JSON.stringify({event: 'onStateChange', id: 'hb-youtube', info: 1}), '*');
                           window.postMessage(JSON.stringify({event: 'infoDelivery', id: 'hb-youtube',
                             info: {muted: true, volume: 70, playerState: 1, videoData: {video_id: vid}}}), '*'); }""", _V1)
        _page.wait_for_function("() => { const h = document.querySelector('.hb-yt-unmute');"
                                " return !!h && getComputedStyle(h).display !== 'none'; }", timeout=4000)
        clause = state_render.clause("youtube")
        assert clause.startswith("youtube@computer: playing") and "facts: audio_blocked" in clause, clause
        _page.wait_for_timeout(1800)                           # the ack after the player spoke and settled
        assert any(b.get("ack") and b.get("full") for b in seen), seen
        assert state_render.read("youtube")["surfaces"][0]["pending"] == [], "an applied revision stayed pending"
    finally:
        _page.unroute("**/widgets/youtube/state")
        state._reset_for_tests()
        screens._reset_for_tests()

"""The card says what the PLAYER plays through the one state door — never as an action into the store (V2-884 1b).

The end states of a start and a pause read `report.playing_id` / `report.playing`. This drives the real card module with
the REAL host reporter (`frontend/app/widgets/state-reporter.js`, only `fetch` stubbed) and feeds it the embedded
player's own postMessage stream (`infoDelivery` with the video it delivered, `onStateChange` 1 playing · 2 paused):
each change reaches the door ONCE (the player repeats its state several times a second), with the id it delivered;
another frame's messages say nothing; our own <video> (library, torrent) says the same fields — once it can, so a
stream left paused is still heard — and no `player_state` action is sent any more. Disarm: the stream's
`loadedmetadata` report removed → the paused stream says nothing (red).
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys

import pytest

_V1 = "dQw4w9WgXcQ"
_ENGINE = pathlib.Path(__file__).resolve().parents[4]
_DATA = {"title": "Uno", "channel": "C", "volume": 70, "muted": False, "paused": False, "list": [], "player_error": "",
         "pos": -1, "search_results": [], "platforms": [], "blocked_channels": [], "lists": [], "history": [],
         "prefs": {}, "channels": [], "suggested": [], "connector_shelf": [], "cmd_seq": 1}


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close(); return port


@pytest.fixture(scope="module")
def browser_page():
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
            pg = browser.new_page()
            pg.route("**://i.ytimg.com/**", lambda r: r.fulfill(status=200, content_type="image/gif", body=b"GIF89a"))
            pg.route("**://www.youtube.com/**", lambda r: r.fulfill(status=200, content_type="text/html", body="<html></html>"))
            pg.route("**/api/library/**", lambda r: r.fulfill(status=404, body=""))
            pg._hb = (f"http://127.0.0.1:{port}/widgets/youtube/", f"http://127.0.0.1:{port}/widgets/youtube/widget.js")
            yield pg
            browser.close()
    finally:
        srv.terminate()


def _mount(pg, data: dict):
    origin, src = pg._hb
    pg.goto(origin)
    pg.set_content("<div id='w' style='width:660px'></div>")
    pg.evaluate("""async ([src, data]) => {
        window.__calls = []; window.__posts = [];
        const R = await import('/frontend/app/widgets/state-reporter.js?v=1');
        const rep = R.stateReporter('youtube', 'youtube', {device: 'desktop:aaa', fetch: async (u, init) => {
            window.__posts.push(JSON.parse(init.body)); return {status: 200, json: async () => ({ok: true, facts: []})}; }});
        window.__ctx = {action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve({ok: true}); },
                        state: (p, o) => rep.report(p, o), top: () => {}, running: true};
        const mod = await import(src);
        mod.render(document.getElementById('w'), data, window.__ctx);
      }""", [src, data])
    pg.wait_for_timeout(250)


def _post(pg, msg: dict, times: int = 1):
    pg.evaluate("([m, n]) => { for (let i = 0; i < n; i++) window.postMessage(JSON.stringify(m), '*'); }", [msg, times])
    pg.wait_for_timeout(250)


def _said(pg, field: str) -> list:
    """Every value of `field` that reached the door, in order (a full snapshot repeats nothing new)."""
    out = []
    for b in pg.evaluate("() => window.__posts"):
        if field in (b.get("patch") or {}) and (not out or out[-1] != b["patch"][field]):
            out.append(b["patch"][field])
    return out


def test_each_state_the_player_reports_reaches_the_door_once_with_its_video(browser_page):
    pg = browser_page
    _mount(pg, {**_DATA, "videoId": _V1})
    n0 = len(pg.evaluate("() => window.__posts"))
    _post(pg, {"event": "infoDelivery", "id": "hb-youtube", "info": {"videoData": {"video_id": _V1}}})
    _post(pg, {"event": "onStateChange", "id": "hb-youtube", "info": 1}, times=4)
    posts = pg.evaluate("() => window.__posts")[n0:]
    assert len([b for b in posts if (b.get("patch") or {}).get("playing") is True]) == 1, posts
    assert any((b.get("patch") or {}).get("playing_id") == _V1 for b in posts), posts
    _post(pg, {"event": "onStateChange", "id": "hb-youtube", "info": 2}, times=3)
    assert _said(pg, "playing")[-2:] == [True, False]
    assert not [c for c in pg.evaluate("() => window.__calls") if c[0] == "player_state"], "the store report is retired"


def test_another_frames_messages_say_nothing(browser_page):
    pg = browser_page
    _mount(pg, {**_DATA, "videoId": _V1})
    n = len(pg.evaluate("() => window.__posts"))
    _post(pg, {"event": "onStateChange", "id": "someone-else", "info": 1})
    assert len(pg.evaluate("() => window.__posts")) == n


def test_our_own_video_says_the_same_fields_even_left_paused(browser_page):
    pg = browser_page
    _mount(pg, {**_DATA, "videoId": "", "src": "/api/library/stream/a.mp4", "source": "local", "paused": True})
    assert pg.evaluate("() => !!document.querySelector('video.hb-yt-video')")
    pg.evaluate("() => document.querySelector('video.hb-yt-video').dispatchEvent(new Event('loadedmetadata'))")
    pg.wait_for_timeout(250)
    last = {}
    for b in pg.evaluate("() => window.__posts"):
        last.update(b.get("patch") or {})
    assert last.get("playing") is False and last.get("muted") is False and last.get("volume") == 100, last
    pg.evaluate("() => document.querySelector('video.hb-yt-video').dispatchEvent(new Event('playing'))")
    pg.wait_for_timeout(250)
    assert _said(pg, "playing")[-1] is True
    assert "playing_id" not in last, "a stream of ours has no video id to say"
    assert not [c for c in pg.evaluate("() => window.__calls") if c[0] == "player_state"]


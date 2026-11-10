"""The card reports what the PLAYER plays, from the player's own state — never from the order (V2-873).

The end states of a start and a pause read `playing_id`/`playing` (`widgets/youtube/sound.player_state`); this drives
the real card module in a browser and feeds it the embedded player's own postMessage stream (`infoDelivery` with the
video it delivered, `onStateChange` 1 playing · 2 paused · 0 ended): each change is reported ONCE as `player_state`,
with the id the player delivered. Disarm: the reporter left unbound reports nothing.
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys

import pytest

_V1 = "dQw4w9WgXcQ"
_ENGINE = pathlib.Path(__file__).resolve().parents[4]


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close(); return port


@pytest.fixture(scope="module")
def page():
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
            pg.goto(f"http://127.0.0.1:{port}/widgets/youtube/")
            pg.set_content("<div id='w' style='width:660px'></div>")
            pg.evaluate("""async (src) => {
                window.__calls = [];
                const mod = await import(src);
                window.__ctx = {action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve({ok: true}); },
                                top: () => {}, running: true};
                mod.render(document.getElementById('w'), {videoId: %r, title: "Uno", channel: "C", volume: 70,
                  muted: false, paused: false, list: [], player_error: "", pos: -1, search_results: [], platforms: [],
                  blocked_channels: [], lists: [], history: [], prefs: {}, channels: [], suggested: [],
                  connector_shelf: [], cmd_seq: 1}, window.__ctx);
              }""" % _V1, f"http://127.0.0.1:{port}/widgets/youtube/widget.js")
            yield pg
            browser.close()
    finally:
        srv.terminate()


def _post(page, msg: dict, times: int = 1):
    page.evaluate("([m, n]) => { for (let i = 0; i < n; i++) window.postMessage(JSON.stringify(m), '*'); }", [msg, times])
    page.wait_for_timeout(150)


def _reports(page):
    return page.evaluate("() => window.__calls.filter(c => c[0] === 'player_state').map(c => c[1])")


def test_each_state_the_player_reports_is_said_once_with_its_video(page):
    _post(page, {"event": "infoDelivery", "id": "hb-youtube", "info": {"videoData": {"video_id": _V1}}})
    _post(page, {"event": "onStateChange", "id": "hb-youtube", "info": 1}, times=4)
    assert _reports(page) == [{"playing": True, "videoId": _V1}]
    _post(page, {"event": "onStateChange", "id": "hb-youtube", "info": 2}, times=3)
    assert _reports(page)[-1] == {"playing": False, "videoId": _V1} and len(_reports(page)) == 2
    _post(page, {"event": "infoDelivery", "id": "hb-youtube", "info": {"playerState": 1, "videoData": {"video_id": _V1}}})
    assert _reports(page)[-1] == {"playing": True, "videoId": _V1} and len(_reports(page)) == 3


def test_another_frames_messages_report_nothing(page):
    n = len(_reports(page))
    _post(page, {"event": "onStateChange", "id": "someone-else", "info": 2})
    assert len(_reports(page)) == n

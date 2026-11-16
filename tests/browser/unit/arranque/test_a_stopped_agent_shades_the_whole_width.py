"""A stopped agent shades the whole width of the screen, the chat column included (node 4.555).

Measured by the operator on the desktop (2026-11-16): with the agent stopped the dark veil covered the desk and left
the docked chat lit and clickable — «el chat queda exento de ese overlay… el usuario puede seguir clicando». The veil
lives inside `#desk`, which ends where a docked chat begins. Now, while the agent is stopped or in transit, the chat
wears the same shade (a layer over it that takes the clicks) and the veil's box is centred in the WINDOW. The bottom
rail stays usable: the ⏻ is there. Asleep and «moved» were already black over everything, the chat included.

Disarmed (seen red): the chat's shade rule removed → a click lands on the chat's own control.
"""
from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

FRONT = Path("frontend")
pytest.importorskip("playwright.sync_api")

PAGE = """<!doctype html><html><head>
<link rel="stylesheet" href="/app/core/palette.css"><link rel="stylesheet" href="/app/core/shared-surfaces.css">
<link rel="stylesheet" href="/app/styles.css">
<style>:root{--chatdock-l:420px}</style></head><body class="chatdock-l">
<div id="chatwall" class="chatwall open" style="top:0;bottom:0;left:0;width:420px;height:auto">
  <button id="chatbtn" style="position:absolute;left:40px;top:300px;width:120px;height:40px">send</button></div>
<div id="desk"><div class="zv FACE" id="veil"><div class="zv-box"><h2 class="zv-title">t</h2>
  <button class="zv-btn primary" id="go">go</button></div></div></div>
</body></html>"""


@pytest.fixture(scope="module")
def page_of():
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=FRONT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _up():
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return True
        except OSError:
            return False
    until_sync(_up, "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()

            def make(face):
                pg = b.new_page(viewport={"width": 1400, "height": 800})
                pg.route("**/__veil", lambda r: r.fulfill(status=200, content_type="text/html", body=PAGE.replace("FACE", face)))
                pg.goto(f"http://127.0.0.1:{port}/__veil", wait_until="load")
                return pg
            yield make
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


HIT = "() => { const e = document.elementFromPoint(100, 320); return e ? (e.id || e.className) : ''; }"
SHADE = "() => getComputedStyle(document.getElementById('chatwall'), '::after').backgroundColor"
BOX = "() => { const r = document.querySelector('.zv-box').getBoundingClientRect(); return (r.left + r.right) / 2; }"


@pytest.mark.parametrize("face", ["on off", "on pausing", "on starting"])
def test_stopped_or_in_transit_the_chat_is_shaded_and_takes_no_click(page_of, face):
    pg = page_of(face)
    assert pg.evaluate(HIT) == "chatwall", "a click over the chat's control lands on the shade, never on the control"
    assert pg.evaluate(SHADE) == "rgba(6, 8, 14, 0.72)", "the chat wears the veil's own shade"
    assert pg.evaluate(BOX) == pytest.approx(700, abs=2), "the veil's box is centred in the window, not beside the chat"
    pg.close()


def test_with_no_veil_the_chat_is_itself(page_of):
    pg = page_of("")
    assert pg.evaluate(HIT) == "chatbtn"
    assert pg.evaluate(SHADE) in ("rgba(0, 0, 0, 0)", "transparent", ""), "no shade without a veil"
    pg.close()


@pytest.mark.parametrize("face", ["on sleep", "on moved"])
def test_asleep_or_moved_the_black_veil_is_over_the_chat_itself(page_of, face):
    pg = page_of(face)
    assert pg.evaluate(HIT) in ("veil", "zv-box"), "the black veil sits above the chat: its click is the veil's"
    pg.close()

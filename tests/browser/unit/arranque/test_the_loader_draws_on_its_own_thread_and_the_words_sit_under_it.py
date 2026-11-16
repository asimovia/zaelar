"""The loader draws on its own thread from the first byte, and on a phone the words sit under it (node 4.554).

Measured by the operator on his phone (2026-11-16): a black screen for seconds, then a loader that moved in jerks and
stood still at times, with its words on top of the drawing. The brain was drawn on the page's own thread — the thread
that is busy loading the whole agent while the loader is on screen — and it only started once the module graph had
loaded. Now `core/preboot.js` starts it on the first byte in a worker (`core/boot-worker.js`, an OffscreenCanvas), where
it moves at its own pace; `components/boot-anim.js` takes everything it needs as an `env`, so it runs with no page at
all; and on a screen held upright the words live in a band at the foot (`CAPTION_BAND`) and the brain above it.

Disarmed (seen red): the worker start cut from `preboot.js` → nothing grows before the modules; `placement` keeping no
band → the brain is drawn into the words' band.
"""
from __future__ import annotations

import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

SCRIPT = Path(__file__).with_name("test_the_loader_draws_on_its_own_thread_and_the_words_sit_under_it.mjs")
FRONT = Path("frontend")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_animation_runs_with_no_page_and_keeps_the_words_band_free():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_the_worker_and_the_page_draw_the_same_animation():
    """One animation, two hosts: the worker imports the very module the page falls back to, and both shells load the
    script that starts it."""
    worker = (FRONT / "app/core/boot-worker.js").read_text(encoding="utf-8")
    assert 'import { startBootAnim } from "../components/boot-anim.js' in worker
    pre = (FRONT / "app/core/preboot.js").read_text(encoding="utf-8")
    assert "transferControlToOffscreen" in pre and "/static/app/core/boot-worker.js" in pre
    overlay = (FRONT / "app/components/BootOverlay.js").read_text(encoding="utf-8")
    assert "window.__zaelarBootAnim" in overlay, "BootOverlay drives the animation that already runs, never a second one"
    for shell in ("index.html", "mobile/index.html"):
        assert "/static/app/core/preboot.js" in (FRONT / shell).read_text(encoding="utf-8")


pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def page_factory():
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

            def make(shell, viewport):
                pg = b.new_page(viewport={"width": viewport[0], "height": viewport[1]})
                pg.route("**/static/**", lambda r: r.continue_(url=r.request.url.replace("/static/", "/", 1)))
                pg.route("**/main.js*", lambda r: r.abort())             # NO module of the agent ever arrives
                pg.route("**/vad/**", lambda r: r.abort())
                pg.route("**/healthz", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
                pg.goto(f"http://127.0.0.1:{port}{shell}", wait_until="domcontentloaded")
                return pg
            yield make
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


GROWN = "() => (window.__zaelarBootAnim ? window.__zaelarBootAnim.shown() : -1)"


def test_the_brain_grows_before_any_module_of_the_agent_has_loaded(page_factory):
    pg = page_factory("/mobile/index.html", (390, 844))
    until_sync(lambda: pg.evaluate(GROWN) > 0.02, "the loader to draw with no module loaded", timeout_s=6)
    a = pg.evaluate(GROWN)
    pg.evaluate("() => { const t = performance.now(); while (performance.now() - t < 1500) {} }")   # the page is BUSY
    pg.wait_for_timeout(150)                       # the worker's reports queued while the page could not listen
    b = pg.evaluate(GROWN)
    assert b > a + 0.05, f"the brain stood still while the page was busy: {a} -> {b}"
    assert pg.evaluate("() => document.getElementById('preboot').classList.contains('anim')")
    pg.close()


@pytest.mark.parametrize("viewport", [(390, 844), (360, 640), (430, 932)])
def test_on_a_phone_held_upright_the_words_are_at_the_foot_under_the_drawing(page_factory, viewport):
    pg = page_factory("/mobile/index.html", viewport)
    until_sync(lambda: pg.evaluate("() => !!document.querySelector('#preboot .pb-title')?.textContent"),
               "the loader's words", timeout_s=6)
    box = pg.evaluate("""() => { const c = document.querySelector('#preboot .pb-cap').getBoundingClientRect();
        const t = document.querySelector('#preboot .pb-title').getBoundingClientRect();
        const r = document.querySelector('#preboot .pb-ring').getBoundingClientRect();
        return { capTop: c.top, capBottom: c.bottom, titleTop: t.top, ring: r.top + r.height / 2, h: innerHeight }; }""")
    assert box["capBottom"] == pytest.approx(box["h"], abs=1), f"the words' band is the foot of the screen: {box}"
    assert box["capTop"] == pytest.approx(box["h"] - 132, abs=1), box
    assert box["titleTop"] >= box["capTop"], box
    assert box["ring"] == pytest.approx((box["h"] - 132) / 2, abs=2), f"the drawing is centred in the screen above the band: {box}"
    pg.close()


def test_a_wide_screen_keeps_the_words_where_they_were(page_factory):
    pg = page_factory("/index.html", (1280, 800))
    until_sync(lambda: pg.evaluate("() => !!document.querySelector('#preboot .pb-cap')"), "the loader's words", timeout_s=6)
    top = pg.evaluate("() => document.querySelector('#preboot .pb-cap').getBoundingClientRect().top")
    assert top == pytest.approx(800 * 0.46 + 60, abs=2), top
    pg.close()

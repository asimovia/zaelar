"""ONE loader, from the first byte to «ready», on both shells (V2-881). Rendered.

The operator (2026-11-11): a visitor saw THREE loaders in a row — the inline splash («starting up…» with a progress
arc), then the neurons' own caption («Starting up zaelar…»), then the neurons. He wants one: the neurons. It starts as
a small ring of dots turning in the centre; the neurons GROW outwards in discrete steps («pa, pa, pa»); the growth is
the progress bar; and it ALWAYS finishes — when the system is ready the rest bursts out in under a second and the
veil lifts.

What this file holds, against the REAL `frontend/index.html` (and the phone's) in Chromium, with the app module held
back — «the modules have not arrived yet» is exactly the moment the first ring exists for:
  * the HTML paints the first ring and `core/preboot.js` narrates on it (cached bundle, English floor, never a key);
  * BootOverlay takes over that SAME element (one `.boot-ovl`, the same node) instead of mounting a second screen;
  * the growth (`aria-valuenow`, and the lit pixels of the canvas) advances on a PHASE signal and never on a timer;
  * `store.bootReady` completes it and the loader is gone within one second of it.

Disarm (in this file, `test_a_loader_that_does_not_hear_ready_is_caught`): BootOverlay is served with its
`store.bootReady` hook cut; the same measurement must fail. The test asserts the mutation landed before measuring.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
FRONT = ENGINE / "frontend"
OVERLAY = FRONT / "app/components/BootOverlay.js"
_EN = json.loads((ENGINE / "i18n/genesis/en/ui.json").read_text(encoding="utf-8"))
READY_HOOK = "if (!store.bootReady()) return;"

pytest.importorskip("playwright.sync_api")


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def browser_and_port():
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=FRONT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            yield b, port
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _page(browser, port, shell="/index.html", overlay_src: str | None = None, viewport=(1280, 800)):
    """The real shell HTML with its app module held back; `/static/…` served from `frontend/` as the engine does."""
    pg = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/static/**", lambda r: r.continue_(url=r.request.url.replace("/static/", "/", 1)))
    pg.route("**/main.js*", lambda r: r.abort())                 # the modules have not arrived yet
    pg.route("**/vad/**", lambda r: r.abort())
    pg.route("**/healthz", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true}'))
    if overlay_src is not None:
        pg.route("**/components/BootOverlay.js*", lambda r: r.fulfill(
            status=200, content_type="text/javascript", body=overlay_src))
    pg.goto(f"http://127.0.0.1:{port}{shell}", wait_until="domcontentloaded")
    pg._errors = errors
    return pg


#: What main.js does with this surface: import it and mount it. Returns the instant of the mount.
MOUNT = """async () => {
  window.__host = document.getElementById('preboot');
  window.__store = await import('/static/app/core/store.js?v=2');
  const m = await import('/static/app/components/BootOverlay.js?v=3');
  document.body.append(m.BootOverlay());
}"""

#: The bar, and how much of the canvas is lit — the growth as the browser has it, not as our maths says.
STATE = """() => {
  const h = document.getElementById('preboot');
  if (!h) return { gone: true };
  const c = h.querySelector('canvas'); let lit = 0;
  if (c && c.width) {
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    for (let i = 3; i < d.length; i += 16) if (d[i] > 40) lit++;
  }
  return { gone: false, now: Number(h.getAttribute('aria-valuenow') || -1), stage: h.dataset.stage, lit,
           same: h === window.__host, count: document.querySelectorAll('.boot-ovl').length,
           text: (h.querySelector('.pb-cap') || {}).textContent || '' };
}"""

#: Fire ready and time how long until the loader is out of the DOM (measured in the page, on the page's clock).
READY = """() => new Promise((resolve) => {
  const t0 = performance.now();
  new MutationObserver((_, ob) => {
    if (!document.getElementById('preboot')) { ob.disconnect(); resolve(performance.now() - t0); }
  }).observe(document.body, { childList: true });
  window.__store.setBootReady(true);
  setTimeout(() => resolve(-1), 2500);
})"""


def _mounted(pg):
    pg.evaluate(MOUNT)
    until_sync(lambda: pg.evaluate(STATE).get("now", -1) >= 0, "BootOverlay to take the loader over", timeout_s=5)


def test_the_first_byte_paints_the_ring_and_narrates_in_the_floor(browser_and_port):
    b, port = browser_and_port
    pg = _page(b, port)
    ring = pg.evaluate("""() => [...document.querySelectorAll('#preboot .pb-ring i')]
        .filter(i => { const r = i.getBoundingClientRect(); return r.width >= 4 && r.height >= 4; }).length""")
    assert ring == 8, f"the first ring is eight dots painted before any module: {ring}"
    until_sync(lambda: pg.evaluate("() => document.getElementById('preboot').dataset.stage") == "1",
               "/healthz answering to be the loader's first step", timeout_s=5)
    cap = pg.evaluate(STATE)["text"]
    assert _EN["preboot.boot.title"] in cap, cap
    assert "preboot." not in cap and "boot." not in cap, f"a raw key on the first screen: {cap!r}"
    assert not pg._errors, pg._errors
    pg.close()


@pytest.mark.parametrize("shell, viewport", [("/index.html", (1280, 800)), ("/mobile/index.html", (390, 844))])
def test_the_growth_follows_real_phases_and_ready_completes_it_within_a_second(browser_and_port, shell, viewport):
    b, port = browser_and_port
    pg = _page(b, port, shell, viewport=viewport)
    _mounted(pg)
    s0 = pg.evaluate(STATE)
    assert s0["same"] and s0["count"] == 1, f"one screen: BootOverlay took the inline loader over, never a second: {s0}"
    assert s0["now"] == 24, f"the interface loaded is the third step of the bar: {s0}"
    pg.wait_for_timeout(600)
    lit0 = pg.evaluate(STATE)["lit"]
    assert lit0 > 50, f"the canvas paints the mesh it reports: {lit0}"

    pg.wait_for_timeout(3000)                                   # no phase arrives: a wait shows as a wait
    s1 = pg.evaluate(STATE)
    assert s1["now"] == 24, f"the bar moved on a timer alone: {s0['now']} -> {s1['now']}"
    assert s1["lit"] < lit0 * 1.4, f"the mesh GREW with no phase: {lit0} -> {s1['lit']}"

    pg.evaluate("() => window.__store.setBootPhase('voz')")    # a real phase: one step, «pa»
    pg.wait_for_timeout(600)
    s2 = pg.evaluate(STATE)
    assert s2["now"] == 42, s2
    assert s2["lit"] > s1["lit"] * 1.15, f"the step did not grow the mesh on screen: {s1['lit']} -> {s2['lit']}"

    took = pg.evaluate(READY)
    assert 0 <= took < 1000, f"ready must complete the loader and lift it within one second; took {took} ms"
    assert not pg._errors, pg._errors
    pg.close()


def test_a_loader_that_does_not_hear_ready_is_caught(browser_and_port):
    """Disarm: the bootReady hook cut — the loader never completes, and the timing check above must say so."""
    src = OVERLAY.read_text(encoding="utf-8")
    assert READY_HOOK in src, "the hook this disarm cuts is gone — update the disarm"
    disarmed = src.replace(READY_HOOK, "return;")
    assert disarmed != src and READY_HOOK not in disarmed
    b, port = browser_and_port
    pg = _page(b, port, overlay_src=disarmed)
    _mounted(pg)
    took = pg.evaluate(READY)
    assert took == -1, f"with the ready hook cut the loader still lifted ({took} ms): the check proves nothing"
    pg.close()


def test_the_dead_loaders_are_gone():
    for shell in ("index.html", "mobile/index.html"):
        html = (FRONT / shell).read_text(encoding="utf-8")
        assert html.count('id="preboot"') == 1 and 'class="boot-ovl"' in html, shell
        assert "Starting up zaelar" not in html and "#preboot {" not in html, f"{shell} carries a second inline splash"
    overlay = OVERLAY.read_text(encoding="utf-8")
    assert "boot-caption" not in overlay and "i18n.js" not in overlay, "the loader grew its own caption again"
    for lang in ("en", "es"):
        pack = json.loads((ENGINE / f"i18n/genesis/{lang}/ui.json").read_text(encoding="utf-8"))
        assert not [k for k in pack if k.startswith("boot.")], f"{lang}: the dead caption's strings are back"

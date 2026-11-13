"""The real card, the real reporter, the real door — one harness for the shared data apps' state tests (V2-884 step 3).

A card is rendered in Chromium and mounted and refreshed through the same two functions the shells call
(`mountState`, `refreshed` in `frontend/app/widgets/state-reporter.js`); only `fetch` is a stand-in that keeps each body. `deliver()` hands those bodies to `widgets.state.report` — the engine's door — so what
the brain reads is what this card, through this reporter, would have said. Not a test file: the app suites import it.
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys

import pytest

from tests.waiting import port_listening

ENGINE = pathlib.Path(__file__).resolve().parents[4]

_NEW_MOUNT = """async ([app, dev, inst]) => {
  const R = await import('/frontend/app/widgets/state-reporter.js?v=1');
  if (window.__w && window.__w._rep) window.__w._rep.dispose();
  window.__posts = [];
  const stub = async (u, init) => { window.__posts.push(JSON.parse(init.body));
      return {status: 200, json: async () => ({ok: true, facts: []})}; };
  window.__R = R; window.__w = {}; window.__opts = {device: dev, fetch: stub}; window.__app = [app, inst];
  window.__ctx = { action: () => Promise.resolve(null), state: (p, o) => window.__w._rep.report(p, o), close() {},
                   top() {}, scroll() {}, openConnector() {}, lang: 'es', running: true, t: null,
                   device: async () => ({ details: async () => ({ sensors: {} }), activity: async () => ({ error: 'none' }) }) };
}"""


@pytest.fixture(scope="module")
def card_page():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=ENGINE,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_listening(port)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(viewport={"width": 1280, "height": 900})
            pg._hb_origin = f"http://127.0.0.1:{port}"
            yield pg
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def mount(page, app: str, data: dict, dev: str, instance: str = "") -> None:
    """A fresh mount of `app` (or its `instance`) on screen `dev`, rendered with `data` (whose `_rev` the host tells
    the reporter)."""
    page.goto(f"{page._hb_origin}/widgets/{app}/")
    page.set_content("<div id='w' style='width:900px;height:700px'></div>")
    page.evaluate(_NEW_MOUNT, [app, dev, instance or app])
    page.evaluate("""async ([src, d]) => { const mod = await import(src); window.__mod = mod;   // as the shells mount
                       window.__R.mountState(window.__w, window.__app[0], window.__app[1], d, window.__opts);
                       mod.render(document.getElementById('w'), d, window.__ctx); }""",
                  [f"{page._hb_origin}/widgets/{app}/widget.js", data])
    page.wait_for_timeout(200)


def push(page, data: dict) -> None:
    """A data push, as the host does it: the reporter is told the revision, then the card renders."""
    page.evaluate("(d) => { window.__R.refreshed(window.__w, d); window.__mod.render(document.getElementById('w'), d, window.__ctx); }",
                  data)
    page.wait_for_timeout(200)


def click(page, selector: str) -> None:
    page.click(selector)
    page.wait_for_timeout(200)


def posts(page) -> list[dict]:
    """The bodies the reporter sent since the last call (each one is what reached the door)."""
    return page.evaluate("() => window.__posts.splice(0)")


def deliver(app: str, bodies: list[dict]) -> list[int]:
    """The bodies through the engine's door, in order; the status of each."""
    from widgets import state
    return [state.report(app, b)[0] for b in bodies]

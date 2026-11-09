"""Shared harness for the daemon screen's rendered tests (V2-575): a static server over the engine tree and a
Chromium page whose `/api/daemon/status` (and `/api/daemon/pair`) answer whatever the test holds in `api`.

`api["status"]` is either one status dict or a LIST of them: a list is served one per request, the last one
repeated — which is how a test feeds a poll two successive answers. Every status request is counted in
`api["hits"]`, and every pair request in `api["pair_hits"]`.
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
BUNDLES = {lang: json.loads((ENGINE / f"i18n/genesis/{lang}/ui.json").read_text(encoding="utf-8"))
           for lang in ("es", "en")}

_CSS = ['/frontend/app/core/palette.css', '/frontend/app/core/shared-surfaces.css',
        '/frontend/app/core/components.css', '/frontend/app/styles.css']


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def server():
    pytest.importorskip("playwright.sync_api")
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    yield port
    srv.terminate(); srv.wait(timeout=10)


def _status_handler(api):
    def handle(route):
        api["hits"] = api.get("hits", 0) + 1
        seq = api["status"]
        if isinstance(seq, list):
            i = min(api.get("served", 0), len(seq) - 1)
            api["served"] = api.get("served", 0) + 1
            body = seq[i]
        else:
            body = seq
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    return handle


def _pair_handler(api):
    def handle(route):
        api["pair_hits"] = api.get("pair_hits", 0) + 1
        code, body = api.get("pair", (200, {"ok": False, "error": "relay_not_available"}))
        body = body() if callable(body) else body
        route.fulfill(status=code, content_type="application/json", body=json.dumps(body))
    return handle


def open_page(pw, port: int, api: dict, *, lang: str = "es", width: int = 1280, height: int = 900, touch=False):
    """A page with the shared stylesheets and the `lang` bundle loaded, nothing mounted yet."""
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": width, "height": height}, has_touch=touch)
    pg = ctx.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    # A function painted as source is refused LOUDLY by dom.js on the console, not thrown: counted as an error.
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and "dom.js" in m.text else None)
    # The catch-all FIRST: Playwright gives the LAST matching route priority.
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/daemon/status", _status_handler(api))
    pg.route("**/api/daemon/pair", _pair_handler(api))
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"strings": BUNDLES["en" if r.request.url.rstrip("/").endswith("/en") else "es"]})))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async ([css, lang]) => {
        for (const h of css) { const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h;
                               document.head.append(l); }
        await new Promise(r => setTimeout(r, 200));
        const store = await import('/frontend/app/core/store.js?v=2');
        if (store.setLang) store.setLang(lang);
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle(lang); if (i18n.applyLang) await i18n.applyLang(lang);
        window.__store = store;
        window.__daemon = await import('/frontend/app/services/daemon.js?v=3');
    }""", [_CSS, lang])
    pg._errors = errors
    pg._browser = browser
    return pg


def mount_screen(pg):
    """The real DaemonSetup, opened, after its first status has arrived."""
    pg.evaluate("""async () => {
        const m = await import('/frontend/app/components/DaemonSetup.js?v=1');
        document.body.append(m.DaemonSetup());
        window.__store.setDaemonSetupOpen(true);
        await window.__daemon.check();
    }""")


def recheck(pg):
    pg.evaluate("async () => { await window.__daemon.check(); }")


# What the screen paints, read from the DOM: the cards in order, and the text of the parts the tests name.
READ = """() => {
  const o = document.querySelector('.dsx-ovl');
  const q = (s) => { const e = o.querySelector(s); return e ? e.innerText.trim() : null; };
  const card = (id) => o.querySelector(`[data-card="${id}"]`);
  const sw = o.querySelector('.dsx-switch');
  return {
    open: o.classList.contains('on'),
    title: q('.dsx-title'),
    cards: [...o.querySelectorAll('[data-card]')].map(e => e.dataset.card),
    lead: q('.dsx-lead'),
    installed: q('.dsx-installed .dsx-v'), running: q('.dsx-running .dsx-v'),
    version: q('.dsx-version .dsx-v'), link: q('.dsx-link-state .dsx-v'),
    folders: [...o.querySelectorAll('.dsx-item .dsx-path')].map(e => e.innerText),
    defaultTag: q('.dsx-item.is-default .dsx-default'), suggested: q('.dsx-chip.is-default'),
    slow: q('.dsx-limit'), foldersNote: q('[data-card="folders"] .dsx-unknown'),
    browser: q('.dsx-browser-state'), onlyChrome: q('.dsx-only-chrome'), cap: q('.dsx-cap'),
    bar: (() => { const b = o.querySelector('.dsx-progress-bar'); return b ? b.getBoundingClientRect().width : null; })(),
    track: (() => { const b = o.querySelector('.dsx-progress'); return b ? b.getBoundingClientRect().width : null; })(),
    windowOpen: (() => { const b = o.querySelector('.dsx-window-open'); return b ? {disabled: b.disabled, tip: b.title} : null; })(),
    pairCard: !!card('pair'), pairLinked: q('.dsx-pair-linked'), pairCode: q('.dsx-pair-code'),
    pairLeft: q('.dsx-pair-left'), pairHow: q('.dsx-pair-how'), pairCli: q('.dsx-pair-cli'),
    getCard: !!card('get'), limit: q('[data-card="get"] .dsx-warn'),
    tunnel: q('.dsx-consent'), soon: q('.dsx-soon'),
    switchDisabled: sw ? sw.disabled : null, switchChecked: sw ? sw.checked : null,
    text: o.innerText,
  };
}"""


def read(pg) -> dict:
    return pg.evaluate(READ)

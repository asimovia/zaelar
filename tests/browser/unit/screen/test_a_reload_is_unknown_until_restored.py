"""A reloaded screen is UNKNOWN until its saved apps are back, never an empty screen (V2-907 A1, node 4.546).

RENDERED: the real `desktop.js` (windows) and `Deck.js` (deck) with apps saved in this browser's storage, their
`/api/canvas/layout` answer held back so the restore is still running when the first report goes out. Every body the
host POSTed to `/api/screen/report` is checked: none claims `open: []` while the restore runs — those say
`unknown: true` — the last one lists every saved app, and the engine's door (`widgets/screen_doc.write`) takes each in
order and ends with the saved apps open and nothing in `closed`. Disarm: the reporter ignores the host's restore.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from tests.browser.unit.mobile.phone_page import open_phone
from tests.browser.unit.mobile.test_the_deck_reports_what_it_shows import _LAYOUT, _widgets
from tests.browser.unit.screen.test_the_desktop_reports_what_it_shows import MANIFESTS, _free_port
from tests.waiting import port_listening

ENGINE = pathlib.Path(__file__).resolve().parents[4]
REPORTER = ENGINE / "frontend" / "app" / "widgets" / "screen-reporter.js"
_GUARD = "if (adapter.restoring && adapter.restoring()) return { layout: adapter.layout, unknown: true };"
SAVED = ["agenda", "musica"]
_STUB = "export function render(el){ el.textContent = 'mounted'; }\nexport default { render };\n"
HOLD_MS = 900


def _json(route, payload):
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


def _routes(page, reports, reporter_src):
    widgets = [{"id": i, "name": i} for i in MANIFESTS]
    page.route("**/api/**", lambda r: _json(r, {}))
    page.route("**/widgets", lambda r: _json(r, {"widgets": widgets}))
    page.route("**/widgets/registry", lambda r: _json(r, {"registry": []}))
    page.route("**/widgets/*/widget.js*", lambda r: r.fulfill(status=200, content_type="application/javascript", body=_STUB))
    page.route("**/widgets/*/data*", lambda r: _json(r, {}))
    page.route("**/widgets/*/aliases*", lambda r: _json(r, {"ok": True, "aliases": []}))
    page.route("**/api/canvas/layout*", lambda r: _json(r, {"items": [], "live": [], "elsewhere": [], "sheets": []}))
    page.route("**/api/screen/report", lambda r: (reports.append(json.loads(r.request.post_data or "{}")),
                                                  _json(r, {"ok": True})))
    if reporter_src is not None:
        page.route("**/frontend/app/widgets/screen-reporter.js*", lambda r: r.fulfill(
            status=200, content_type="application/javascript", body=reporter_src))


# The restore's fetch of the layout is slowed in the page itself (a held route would block Playwright's own loop).
_SLOW_LAYOUT = """(ms) => { const f = window.fetch.bind(window);
  window.fetch = (u, i) => String(u).includes('/api/canvas/layout') ? new Promise((r) => setTimeout(() => r(f(u, i)), ms)) : f(u, i); }"""


def _desktop(reporter_src=None) -> list[dict]:
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=ENGINE,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_listening(port)
    reports: list[dict] = []
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            page = b.new_page(viewport={"width": 1400, "height": 900})
            _routes(page, reports, reporter_src)
            page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            page.evaluate(_SLOW_LAYOUT, HOLD_MS)
            page.evaluate("""async (saved) => {
                localStorage.setItem('hb_desktop', JSON.stringify(saved.map((id) => ({id, q: ''}))));
                document.body.innerHTML = '<div id="stage"></div><div id="activity"></div>';
                const m = await import('/frontend/app/widgets/desktop.js?v=1');
                window.__desk = new m.Desktop(document.getElementById('stage'));
            }""", SAVED)
            page.wait_for_function("() => window.__desk && !window.__desk._screen.adapter.restoring()", timeout=15000)
            page.wait_for_timeout(600)
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)
    return reports


def _deck(reporter_src=None) -> list[dict]:
    routes = [(lambda u: "/widgets" in u and "/frontend/" not in u, _widgets), _LAYOUT]
    if reporter_src is not None:
        routes.append(("**/frontend/app/widgets/screen-reporter.js*", lambda r: r.fulfill(
            status=200, content_type="application/javascript", body=reporter_src)))
    with open_phone("", routes=routes) as pg:
        pg.evaluate(_SLOW_LAYOUT, HOLD_MS)
        pg.evaluate("""async (saved) => {
            localStorage.setItem('zaelar_mobile_deck', JSON.stringify(saved));
            localStorage.setItem('zaelar_mobile_wipe', '');
            const stage = document.createElement('div'); stage.id = 'zm-deck-wrap'; document.body.append(stage);
            const { Deck } = await import('/frontend/mobile/app/shell/Deck.js?v=a1');
            window.__deck = new Deck(stage); window.__deck.restore();
        }""", SAVED)
        pg.wait_for_function("() => window.__deck && !window.__deck._screen.adapter.restoring()", timeout=15000)
        pg.wait_for_timeout(600)
        reports = [p["body"] for p in pg._posts if p["url"] == "/api/screen/report"]
    return reports


def _check(reports: list[dict], layout: str) -> None:
    mine = [r for r in reports if r.get("doc", {}).get("layout") == layout]
    assert mine, f"{layout}: the host never reported"
    first_full = next((i for i, r in enumerate(mine) if not r["doc"].get("unknown")), None)
    assert first_full is not None, f"{layout}: never reported what it shows: {mine}"
    assert first_full > 0, f"{layout}: the first report was not unknown while the restore ran: {mine[0]['doc']}"
    for r in mine:
        assert r["doc"].get("unknown") or r["doc"]["open"], f"{layout}: a report claimed an empty screen: {r['doc']}"
    assert sorted(x["id"] for x in mine[-1]["doc"]["open"]) == SAVED, mine[-1]["doc"]
    from widgets import screen_doc
    from voice import screens
    screen_doc._reset_for_tests()
    real_open = screens.is_open
    screens.is_open = lambda dev: True
    try:
        dev = "desktop:a1test"
        for r in mine:
            stored, why = screen_doc.write(dev, r["mount"], r["n"], r["doc"], by=r.get("by") or "")
            assert stored or why == "n_back", (why, r)
        d = screen_doc.read(dev)
        assert d is not None and sorted(x["id"] for x in d.open) == SAVED and d.closed == (), d
    finally:
        screens.is_open = real_open
        screen_doc._reset_for_tests()


@pytest.mark.parametrize("layout", ["windows", "deck"])
def test_a_reload_is_unknown_until_restored(layout):
    _check(_desktop() if layout == "windows" else _deck(), layout)


def test_disarm_a_reporter_that_ignores_the_restore_turns_it_red(tmp_path):
    src = REPORTER.read_text(encoding="utf-8")
    assert src.count(_GUARD) == 1, "disarm did not land"
    mutated = src.replace(_GUARD, "")
    assert mutated != src
    for layout, run in (("windows", _desktop), ("deck", _deck)):
        with pytest.raises(AssertionError):
            _check(run(mutated), layout)
    shutil.rmtree(ENGINE / "tests" / "browser" / "unit" / "screen" / "__pycache__", ignore_errors=True)

"""The canvas report says a card is at full screen when the BROWSER's full screen holds it (node 4.561).

A typed order carries a user gesture, so `nativeFullscreen` really enters the browser's own full screen — with no
`_restore` and no `_persist`. The legacy canvas report (`/api/canvas/state`, the one `truth.canvas_state` and the
circuit read) only marked `max` from `_restore` and was not sent on `fullscreenchange`, so the circuit's «youtube is
maximized» never came true and, once its deadline passed, the mouth said «I couldn't make it full screen» over a card
that had been full screen (demo sandbox 2026-11-17, V3→V4).

RENDERED: the real `desktop.js` in Chromium. A card enters the browser's full screen the way `nativeFullscreen` does
(`requestFullscreen`), then leaves it the way Escape does. After each, the last report POSTed to `/api/canvas/state`
is handed to the REAL server route, and the canvas state the circuit reads must say `maximized`, then `visible`.
Disarms: no `fullscreenchange` report; `max` read from `_restore` only.
"""
from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.browser.unit.screen.test_the_desktop_reports_what_it_shows import ENGINE, _order, browser  # noqa: F401
from tests.browser.unit.screen.test_the_desktop_reports_what_it_shows import _page as _base_page

DESKTOP = ENGINE / "frontend" / "app" / "widgets" / "desktop.js"
_LISTEN = " this._reportOpen(true); });"
_MAX = "max:(r || document.fullscreenElement === c)?1:0"


@pytest.fixture
def server_state(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from server import livekit_api as lk
    monkeypatch.setitem(lk._active, "sid", None)            # no live session: every report counts
    from memory import api as memory
    memory.set_state({"open_widgets": [], "maximized_widget": "", "minimized_widgets": []})


def _page(browser, desktop_src: str | None = None):  # noqa: F811
    """The shared page, plus the legacy canvas reports it POSTs (and, for a disarm, a modified desktop.js)."""
    if desktop_src is None:
        page, _, errors = _base_page(browser)
    else:
        real = browser.new_page

        def _patched(**kw):
            pg = real(**kw)
            pg.route("**/frontend/app/widgets/desktop.js*", lambda r: r.fulfill(
                status=200, content_type="application/javascript", body=desktop_src))
            return pg
        browser.new_page = _patched
        try:
            page, _, errors = _base_page(browser)
        finally:
            browser.new_page = real
    states: list[dict] = []

    def _state(route):
        states.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json", body="{}")
    page.route("**/api/canvas/state", _state)
    return page, states, errors


def _served(states) -> str:
    """What the circuit reads for `agenda` once the last report reached the real server route."""
    from nucleo import truth
    from server import canvas_api
    with ThreadPoolExecutor(1) as pool:             # Playwright's sync API holds this thread's event loop
        pool.submit(asyncio.run, canvas_api.canvas_state(states[-1])).result()
    return truth.canvas_state("agenda")


def _scenario(page, states) -> None:
    _order(page, "show", "agenda", 1)
    page.evaluate("() => { window.__desk.fitAll = () => {}; }")   # the desk's own refit is not the signal
    page.wait_for_timeout(800)
    n = len(states)
    page.evaluate("() => window.__desk.wins.get('agenda').card.requestFullscreen()")
    page.wait_for_timeout(600)
    assert page.evaluate("() => document.fullscreenElement && document.fullscreenElement.dataset.wid") == "agenda"
    assert len(states) > n, "entering the browser's full screen was not reported"
    assert _served(states) == "maximized", states[-1].get("layout")
    n = len(states)
    page.evaluate("() => document.exitFullscreen()")
    page.wait_for_timeout(600)
    assert len(states) > n, "leaving the browser's full screen was not reported"
    assert _served(states) == "visible", states[-1].get("layout")


def test_the_browsers_full_screen_reaches_the_canvas_state(browser, server_state):  # noqa: F811
    page, states, errors = _page(browser)
    try:
        _scenario(page, states)
        assert not errors, errors
    finally:
        page.close()


@pytest.mark.parametrize("guard,plain,match", [
    (_LISTEN, " });", "was not reported"),
    (_MAX, "max:r?1:0", "maximized"),
])
def test_disarm_turns_it_red(browser, server_state, guard, plain, match):  # noqa: F811
    src = DESKTOP.read_text(encoding="utf-8")
    assert src.count(guard) == 1, "disarm did not land"
    page, states, _ = _page(browser, src.replace(guard, plain))
    try:
        with pytest.raises(AssertionError, match=match):
            _scenario(page, states)
    finally:
        page.close()

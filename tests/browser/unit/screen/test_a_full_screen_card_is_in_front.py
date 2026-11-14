"""The browser's full screen is in the desk's screen document (V2-907 A4, node 4.548).

RENDERED: the real `desktop.js` + `desktop-screen.js` in Chromium. Two cards; the LOWER one (not top of z) enters the
browser's own full screen (`requestFullscreen`, which the desk does not announce) and later leaves it the way Escape
does (`document.exitFullscreen`), in a window that does not resize for it (the desk's refit stubbed). After each,
with no other change of the desk to carry it, the last document must say it: the full-screen card is `front`, layer 0, `fs: true`, and the other is `behind`; once out, the top of z is front
again and no card has `fs`. Disarms: no `fullscreenchange` listener; the full-screen card not ranked first.
"""
from __future__ import annotations

import pytest

from tests.browser.unit.screen.test_the_desktop_reports_what_it_shows import ADAPTER, _order, _page, browser  # noqa: F401

_LISTEN = '  try { document.addEventListener("fullscreenchange", () => rep.changed()); } catch (_) {}\n'
_RANK = "(_fs(y) - _fs(x)) || "


def _rows(reports) -> dict:
    doc = reports[-1]["doc"]
    return {"front": doc["front"], **{r["id"]: (r["layer"], r["vis"], bool(r.get("fs"))) for r in doc["open"]}}


def _scenario(page, reports) -> None:
    _order(page, "show", "agenda", 1); _order(page, "show", "contactos", 2)
    assert _rows(reports)["front"] == "contactos", _rows(reports)
    # A window already the size of the screen (F11, a phone-sized kiosk) does not resize when a card goes full screen:
    # the desk's own refit, which reports as a side effect of the resize headless Chromium fires, is not the signal.
    page.evaluate("() => { window.__desk.fitAll = () => {}; }")
    page.wait_for_timeout(1500)                 # the shows' own late passes (arrange) report first, then the desk is still
    n = len(reports)
    page.evaluate("() => window.__desk.wins.get('agenda').card.requestFullscreen()")
    page.wait_for_timeout(500)
    assert page.evaluate("() => document.fullscreenElement && document.fullscreenElement.dataset.wid") == "agenda"
    assert len(reports) > n, "entering the browser's full screen was not reported"
    got = _rows(reports)
    assert got["front"] == "agenda" and got["agenda"] == (0, "front", True) and got["contactos"][1:] == ("behind", False), got
    n = len(reports)
    page.evaluate("() => document.exitFullscreen()")
    page.wait_for_timeout(500)
    assert len(reports) > n, "leaving the browser's full screen was not reported"
    got = _rows(reports)
    assert got["front"] == "contactos" and not got["agenda"][2] and not got["contactos"][2], got


def test_a_full_screen_card_is_in_front(browser):  # noqa: F811
    page, reports, errors = _page(browser)
    try:
        _scenario(page, reports)
        assert not errors, errors
    finally:
        page.close()


@pytest.mark.parametrize("guard,match", [(_LISTEN, "was not reported"), (_RANK, "front")])
def test_disarm_turns_it_red(browser, guard, match):  # noqa: F811
    src = ADAPTER.read_text(encoding="utf-8")
    assert src.count(guard) == 1, "disarm did not land"
    page, reports, _ = _page(browser, src.replace(guard, ""))
    try:
        with pytest.raises(AssertionError, match=match):
            _scenario(page, reports)
    finally:
        page.close()

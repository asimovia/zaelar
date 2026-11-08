"""The browser's end state is the page ARRIVING, never the URL it was sent to (operator, 2026-11-08).

`_goto` writes the URL BEFORE navigating, so the URL proves nothing. A capture bumps `rev` and writes `wall` — what
the page on screen IS (none · antibot · captcha · http, from `page_outcome.py`) — and `_search` writes the `query`;
all three are VALUES in every view, even of a store written before they existed. So open/search declare
`rev changed` + `wall is none`: a navigation that never landed, or landed on an anti-bot wall, reads unmet. And a
browser that is down is an offer with the page as a link, never a dead stop.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.circuit import spec, verify
from widgets.navegador import data as nav
from widgets.navegador import owner as O
from widgets.navegador import page_outcome as po


class _Page:
    def __init__(self):
        self.url = "about:blank"
        self.next_status = 200
        self.fail = False

    async def screenshot(self, **_k):
        return None

    async def title(self):
        return "page"

    async def goto(self, url, **_k):
        if self.fail:
            raise TimeoutError("navigation timed out")
        self.url = url
        po._note(self, {"status": self.next_status, "wall": po.classify(self.next_status, url)})


@pytest.fixture
def browser(monkeypatch, tmp_path):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    page = _Page()

    async def _ensure():
        return page

    async def _nothing(*_a, **_k):
        return None
    monkeypatch.setattr(O, "_ensure_page", _ensure)
    monkeypatch.setattr(O, "_dismiss_overlays", _nothing)
    monkeypatch.setattr(O, "_emit", lambda *a, **k: None)
    monkeypatch.setattr(O, "_page", page)
    monkeypatch.setattr(O, "_rev", 0)
    monkeypatch.setattr(O, "_hist", [])
    monkeypatch.setattr(O, "_idx", -1)
    return page


def _run(action, payload):
    dw = spec.render("navegador", action, payload)
    assert dw, f"navegador:{action} declares no renderable end state"
    asyncio.run(O.handle(action, payload))
    return verify.check(dw)


def test_a_search_that_lands_reads_met_and_says_what_it_searched(browser):
    assert _run("search", {"q": "zapatillas trail"}) is True
    view = nav.view_data()
    assert view["wall"] == "none" and view["query"] == "zapatillas trail" and "bing.com" in view["url"]


def test_a_page_behind_an_antibot_wall_reads_unmet(browser):
    browser.next_status = 403
    assert _run("open", {"url": "wallapop.com"}) is False
    assert nav.view_data()["wall"] == "antibot"


def test_a_navigation_that_never_landed_is_not_met(browser):
    assert _run("open", {"url": "example.com"}) is True
    browser.fail = True
    assert _run("open", {"url": "example.org"}) is not True, "the URL written before navigating is not arrival"


def test_an_older_store_still_answers_every_key():
    from widgets import store
    store.save(nav.WID, {"mode": "page", "url": "https://x.example", "rev": 4})
    view = nav.view_data()
    assert view["wall"] == "" and view["query"] == "" and view["error"] == ""


def test_the_browser_down_is_an_offer_with_the_page_as_a_link(monkeypatch, tmp_path):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.delenv("NAVEGADOR_SEARCH", raising=False)
    got = nav.apply_action("search", {"q": "pisos gràcia"})
    assert got["ok"] is False and got["offer"]
    assert got["link"] == "https://www.bing.com/search?q=pisos+gr%C3%A0cia"
    assert nav.apply_action("open", {"url": "wallapop.com"})["link"] == "https://wallapop.com"
    assert "link" not in nav.apply_action("back", {}) and nav.apply_action("back", {})["offer"]


def test_the_manifest_names_the_engine_the_browser_really_uses():
    import json
    from pathlib import Path
    acts = json.loads(Path("widgets/navegador/manifest.json").read_text(encoding="utf-8"))["actions"]
    assert "Bing" in acts["search"]["desc"] and "Google" not in acts["search"]["desc"]
    assert "bing.com" in O._SEARCH_URL or O.os.environ.get("NAVEGADOR_SEARCH")

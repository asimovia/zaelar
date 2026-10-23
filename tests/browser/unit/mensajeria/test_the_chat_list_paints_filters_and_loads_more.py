"""The chat list of a platform PAINTS: rows, the kind filter, the name search, «Cargar más» and opening a chat.

Verified by RENDERING the widget — the lens is chosen by a pushed view, and a list that the data carries but a
`return` above never draws is invisible to any source-level check (the V2-544 shape).
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def page():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            pg = browser.new_page()
            pg._hb_url = f"http://127.0.0.1:{port}/widgets/mensajeria/widget.js"
            pg.goto(f"http://127.0.0.1:{port}/widgets/mensajeria/")
            yield pg
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data):
    page.set_content("<div id='w'></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src + '?v=' + Math.random());
             window.__ctx = { action: (name, payload) => { window.__calls.push([name, payload || {}]); },
                              top: () => {}, openConnector: () => {}, running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_url, data])


def _data(rows, **v):
    now = time.time()
    return {"platforms": {"telegram": {"status": "connected"}}, "items": [], "chats": [],
            "view": {"platform": "telegram", "n": 1, "at": now},
            "chat_list": {"telegram": {"rows": rows, "recent_h": 72, "total": len(rows), "more": True,
                                       "complete": False, "loading": False, "asked": True, "error": "", **v}}}


_ROWS = [
    {"chatId": "1", "name": "Marta", "kind": "person", "unread": 2, "ts": time.time() - 60, "preview": "¿hoy?"},
    {"chatId": "2", "name": "Viaje Lisboa", "kind": "group", "ts": time.time() - 3600, "preview": "vuelos",
     "fromMe": True},
    {"chatId": "3", "name": "Noticias", "kind": "channel", "ts": time.time() - 7200, "preview": "titular"},
]


def _names(page):
    return page.locator(".cxlist .tfrom").all_inner_texts()


def test_the_list_paints_every_chat_newest_first(page):
    _mount(page, _data(_ROWS))
    assert _names(page) == ["Marta", "Viaje Lisboa", "Noticias"]
    assert "Tú: vuelos" in page.locator(".cxlist").inner_text()


def test_the_kind_filter_and_the_search_narrow_it_without_a_round_trip(page):
    _mount(page, _data(_ROWS))
    page.locator(".cxchip", has_text="Grupos").click()
    assert _names(page) == ["Viaje Lisboa"]
    page.locator(".cxchip", has_text="No leídos").click()
    assert _names(page) == ["Marta"]
    page.locator(".cxchip", has_text="Todos").click()
    page.locator(".cxsearch").fill("noti")
    assert _names(page) == ["Noticias"]
    assert page.evaluate("window.__calls") == [], "filtering is local: nothing is asked of the server"


def test_load_more_and_opening_a_chat_are_the_declared_actions(page):
    _mount(page, _data(_ROWS))
    page.locator(".cxmore").click()
    page.locator(".cxlist .chatrow").first.click()
    assert page.evaluate("window.__calls") == [["chats_more", {"platform": "telegram"}],
                                               ["open", {"platform": "telegram", "chatId": "1"}]]


def test_while_the_first_page_travels_the_list_says_so(page):
    _mount(page, _data([], loading=True, asked=True))
    assert "Cargando" in page.locator(".cxlist").inner_text()


def test_the_media_window_is_chosen_in_settings(page):
    _mount(page, {**_data(_ROWS), "media_days": 14})
    page.locator("button.gear").click()
    active = page.locator(".settings .segbtn.active").all_inner_texts()
    assert "14 días" in active
    page.locator(".settings .segbtn", has_text="30 días").click()
    assert page.evaluate("window.__calls")[-1] == ["set_media_days", {"days": 30}]

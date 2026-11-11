"""A card opened from the catalog shows ITS current state or an empty one — never a foreign search (V2-877 #12).

Search opened from the apps catalog showed a weather search for Soria, in Spanish, under a
«Searching…» that never stopped: `view_data("")` treated «no request» as «the weather», and «no place» as one
operator's home town (a module constant), and the card's header kept saying «Searching…» after every source had
answered. Three halves of one class — stale or foreign state shown as current:

  · no request → an EMPTY card: nothing fetched, the one line that says so and the request that fills it;
  · a weather question with no place in the words → the place from HIS state (`here`, then `location`), else an
    honest question — never a town of ours;
  · the header ends: «Done» once the sources resolved, and a deadline after which the card says the search did
    not finish instead of spinning for ever.

Disarm: make `run("")` fall through to the weather branch again → red (a network fetch is attempted).
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys

import pytest

from tests.waiting import until_sync

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


def _no_network(monkeypatch):
    from widgets.search import data as d
    calls = []
    monkeypatch.setattr(d, "_get", lambda url, timeout=6.0: calls.append(url) or (_ for _ in ()).throw(OSError("off")))
    return d, calls


def test_no_request_is_an_empty_card_and_fetches_nothing(monkeypatch):
    d, calls = _no_network(monkeypatch)
    out = d.view_data("")
    assert out["kind"] == "empty" and not out["sources"] and not out["conclusion"], out
    assert calls == [], f"a card opened with no request searched something: {calls}"


@pytest.mark.parametrize("state, place", [({}, ""), ({"location": "Porto"}, "Porto"),
                                          ({"location": "Porto", "here": {"place": "Lyon"}}, "Lyon")])
def test_a_weather_question_without_a_place_uses_his_place_or_asks(monkeypatch, state, place):
    d, calls = _no_network(monkeypatch)
    import memory.api as memory
    monkeypatch.setattr(memory, "state", lambda: dict(state))
    out = d.view_data("what's the weather like")
    if not place:
        assert out.get("needs") == "place" and calls == [], f"no place known: it asks, it never picks a town: {out}"
    else:
        assert out["location"] == place and calls and all("Soria" not in u for u in calls), (out, calls)


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def page():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(viewport={"width": 393, "height": 852})
            pg.goto(f"http://127.0.0.1:{port}/widgets/search/")
            pg.set_content("<div id='w'></div>")
            pg.evaluate("""async (src) => { const mod = await import(src);
                window.__render = (d) => mod.render(document.getElementById('w'), d, {close(){}, lang: 'en'}); }""",
                        f"http://127.0.0.1:{port}/widgets/search/widget.js")
            yield pg
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _state(pg):
    return pg.evaluate("""() => { const w = document.getElementById('w'); const scan = w.querySelector('.scan');
        return {cls: w.className, text: w.innerText,
                spinning: !!scan && getComputedStyle(scan).display !== 'none'}; }""")


def test_the_empty_card_has_no_spinner_and_names_the_request(page):
    page.evaluate("(d) => window.__render(d)", {"kind": "empty", "sources": [], "conclusion": ""})
    v = _state(page)
    assert not v["spinning"] and "Searching" not in v["text"], v
    assert "Search the web for" in v["text"], v


def test_the_header_ends_when_the_sources_have_answered(page):
    page.evaluate("(d) => window.__render(d)", {"kind": "web", "query": "coffee", "conclusion": "Found two.",
                  "sources": [{"title": "a.example", "status": "ok", "lines": ["x"]},
                              {"title": "b.example", "status": "fail", "lines": ["y"]}]})
    assert _state(page)["spinning"], "while the sources resolve, the card says it is working"
    page.wait_for_timeout(2400)
    v = _state(page)
    assert "done" in v["cls"] and not v["spinning"] and "Searching" not in v["text"], v
    assert "Found two." in v["text"], v

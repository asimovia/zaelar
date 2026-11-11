"""A user surface renders only user-facing fields — the results sheet on the phone, RENDERED (V2-877 #9, V2-876 P-40).

A finished coffee-shop search, opened on a phone, showed as if it were the answer: the
worker's own status line («delivered: 12 verified coffee shops…»), the sheet door's rule to the worker as the reason
three cafés were discarded («no url and no known source — a result says where it was found»), inline-code ticks
around a field name, and the brief's checklist of what the worker must verify. Each of those is a FIELD addressed to
the executor, so the class is fixed by field, never by its words:

  · `summary.state` is the process's status (V2-822 put the process in the processes panel) → not painted;
  · a rejected row the ENGINE filed (its `source` is a gate's filer id) is painted with `reason`, one line per filer in
    his language, derived by `data.view_data`; a row the worker filed keeps its own words;
  · `criteria.quality_bar` (what the worker must verify) and `min_candidates` (its breadth floor) → not painted;
  · inline-code ticks never reach the screen;
  · a tab with nothing he can read is not offered.

And the list fits the hand (P-40): one result per row inside the phone card, title 16px, source 14px, «See detail» a
44px target, and a missing photo is a neutral tile — no giant initial.

Disarm: paint `s.state` again in `panels.js::paintSummary` → red (the status line is on screen).
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys

import pytest

from tests.waiting import until_sync

pytest.importorskip("playwright.sync_api")

_ENGINE = pathlib.Path(__file__).resolve().parents[4]

_WHY = "no url and no known source — a result says where it was found"
_SHEET = {
    "title": "Best coffee shops in San Francisco", "subtitle": "12 verified picks", "tab": "summary",
    "summary": {"state": "delivered: 12 verified coffee shops across 9 neighbourhoods", "explored": 22,
                "steps": ["swept the `Eater` list", "kept 12 across 9 neighbourhoods"]},
    "rejected": [{"title": "Andytown Coffee Roasters", "why": _WHY, "source": "provenance"},
                 {"title": "Abanico Coffee Roasters", "why": "closed on weekdays until 2027"}],
    "criteria": {"goal": "Find the best coffee shops in San Francisco", "min_candidates": 25,
                 "hard": ["Coffee shop located in San Francisco"],
                 "quality_bar": ["verify the `address` on the official site"], "changes": ["only the Mission"]},
    "items": [{"title": "Sightglass Coffee", "subtitle": "SoMa · 270 7th St", "url": "https://sightglasscoffee.com",
               "image": "https://127.0.0.1:9/dead.jpg", "facts": [{"label": "Why", "value": "Roasts on site"}]},
              {"title": "Saint Frank", "subtitle": "Russian Hill", "url": "https://saintfrankcoffee.com"},
              {"title": "Ritual Coffee", "subtitle": "Mission", "image": "https://127.0.0.1:9/dead2.jpg",
               "facts": [{"label": "Why", "value": "Classic"}], "url": "https://ritualcoffee.com"}],
    "sources": [{"name": "Eater", "url": "https://eater.com", "status": "ok", "found": 6}],
}


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(viewport={"width": 393, "height": 852})
            pg.goto(f"http://127.0.0.1:{port}/widgets/results/")
            # The phone deck's card: the widget is mounted inside `.zm-scroll`, where its phone rules apply.
            pg.set_content("<link rel='stylesheet' href='/frontend/app/core/palette.css'>"
                           "<div class='zm-scroll' style='width:393px;height:780px;overflow:auto;box-sizing:border-box;"
                           "padding:0 12px'><div id='host' style='height:760px'></div></div>")
            pg.evaluate("""async (src) => {
                const mod = await import(src);
                const ctx = { action(){ return Promise.resolve({ok: true}); }, top(){}, lang: 'en' };
                window.__render = (d) => mod.render(document.getElementById('host'), JSON.parse(JSON.stringify(d)), ctx);
            }""", f"http://127.0.0.1:{port}/widgets/results/widget.js")
            yield pg
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _served(sheet: dict, monkeypatch, tmp_path) -> dict:
    """The sheet as `view_data` serves it — the derived `reason` is part of what is under test."""
    from widgets import store
    from widgets.results import data as d
    monkeypatch.setattr(store, "load", lambda *_a, **_k: dict(sheet))
    out = d.view_data("")
    return {k: v for k, v in out.items() if k not in ("identity",)}


def _text(pg, data, tab):
    pg.evaluate("(d) => window.__render(d)", {**data, "tab": tab})
    return pg.evaluate("""() => ({text: document.querySelector('.hr-panel').innerText,
        tabs: [...document.querySelectorAll('.hr-tab')].map(b => b.dataset.tab)})""")


def test_the_summary_paints_no_status_line_no_engine_reason_and_no_ticks(page, monkeypatch, tmp_path):
    data = _served(_SHEET, monkeypatch, tmp_path)
    v = _text(page, data, "summary")
    assert "delivered:" not in v["text"], "the worker's status line is the process's, not the deliverable's"
    assert _WHY not in v["text"], "the door's rule to the worker reached his screen"
    assert "No link or source to check it against" in v["text"], "an engine-filed row says why in HIS words"
    assert "closed on weekdays until 2027" in v["text"], "a row the worker filed keeps its own reason"
    assert "`" not in v["text"] and "swept the Eater list" in v["text"], "inline-code ticks are markup, not text"


def test_the_criteria_paint_what_he_can_check_and_not_the_workers_checklist(page, monkeypatch, tmp_path):
    v = _text(page, _served(_SHEET, monkeypatch, tmp_path), "criteria")
    assert "Coffee shop located in San Francisco" in v["text"] and "only the Mission" in v["text"]
    assert "verify the" not in v["text"], "`quality_bar` is the worker's checklist, never his screen"
    assert "25" not in v["text"], "the worker's breadth floor is a budget of the executor"


def test_a_tab_with_nothing_he_can_read_is_not_offered(page, monkeypatch, tmp_path):
    bare = {"title": "Monitors", "items": _SHEET["items"][:1], "criteria": {"quality_bar": ["check the panel"]}}
    v = _text(page, _served(bare, monkeypatch, tmp_path), "criteria")
    assert v["tabs"] == ["results"], v["tabs"]
    assert "Sightglass" in v["text"], "a persisted tab he cannot be shown falls back to the list"


_MEASURE = """() => {
    const cards = [...document.querySelectorAll('.hr-card')];
    const tops = cards.map(c => Math.round(c.getBoundingClientRect().top));
    const fs = (sel) => { const e = document.querySelector(sel); return e ? parseFloat(getComputedStyle(e).fontSize) : 0; };
    const more = document.querySelector('.hr-more');
    const monos = [...document.querySelectorAll('.hr-mono')];
    return {cards: cards.length, distinctRows: new Set(tops).size, title: fs('.hr-card .hr-t'),
            host: fs('.hr-card .hr-host'), moreH: more ? more.getBoundingClientRect().height : 0,
            monoText: monos.map(x => x.textContent).join(''), monos: monos.length,
            over: document.querySelector('.zm-scroll').scrollWidth - 393};
}"""


def _list(page, data, layout):
    page.evaluate("(d) => window.__render(d)", {**data, "tab": "results", "layout": layout})
    page.wait_for_timeout(600)
    return page.evaluate(_MEASURE)


def test_the_list_fits_the_hand(page, monkeypatch, tmp_path):
    data = _served(_SHEET, monkeypatch, tmp_path)
    rows = _list(page, {**data, "items": [{k: v for k, v in it.items() if k != "image"} for it in data["items"]]},
                 "rows")
    assert rows["cards"] == 3 and rows["distinctRows"] == 3, f"one result per row on the phone: {rows}"
    assert rows["title"] >= 16 and rows["host"] >= 14, rows
    assert rows["over"] <= 0, rows
    photos = _list(page, data, "gallery")
    assert photos["distinctRows"] == 3, f"one result per row, photo layout too: {photos}"
    assert photos["moreH"] >= 44, photos
    assert photos["monos"] >= 1 and photos["monoText"] == "", f"a missing photo is a neutral tile, no initial: {photos}"

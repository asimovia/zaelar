"""A native surface open over the canvas is in the screen's document (V2-907 T9, node 4.544).

RENDERED: the real desk and deck, their adapters and `widgets/screen-panel.js`, in one Chromium page (the phone's
harness). Every NAMED surface of `core/system-surfaces.js` (a `name`, not chrome) is opened through the store signal
its row names, and the desk's next document says `panel: <id>`, then `""` once it closes; every page of the phone
(`mobile/app/shell/pages.js`) does the same on the deck's document. A named surface the table does not know is red
here the day it is added. Disarm: the desk's adapter drops `panel`.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from tests.browser.unit.mobile.phone_page import open_phone

ENGINE = pathlib.Path(__file__).resolve().parents[4]
SURFACES = (ENGINE / "frontend/app/core/system-surfaces.js").read_text(encoding="utf-8")
ADAPTER = ENGINE / "frontend/app/widgets/desktop-screen.js"
_PANEL = "    panel: () => panelOf(DESKTOP_PANELS),\n"


def _named() -> list[tuple[str, str]]:
    """(id, how its row says it opens) of every named, non-chrome surface."""
    out = []
    for row in re.findall(r"\{ id: \"[^\"]+\".*?\n?.*?name: (?:null|\"[^\"]+\")", SURFACES, flags=re.S):
        sid = re.search(r'id: "([^"]+)"', row).group(1)
        if re.search(r'kind: "chrome"', row) or re.search(r"name: null", row):
            continue
        out.append((sid, re.search(r'toggle: "([^"]*)"', row).group(1)))
    return out


def _open_js(sid: str, toggle: str) -> str:
    """The store call that opens `sid`, read from its row (`store.<x>Open`, `store.chatTab = <tab>`)."""
    if m := re.search(r"store\.chatTab = (\w+)", toggle):
        return f"s.setChatTab('{m.group(1)}'); s.setChatOpen(true)"
    if sid == "chat":
        return "s.setChatTab('chat'); s.setChatOpen(true)"
    m = re.search(r"store\.(\w+Open)\b", toggle)
    sig = m.group(1) if m else re.sub(r"-(\w)", lambda g: g.group(1).upper(), sid) + "Open"
    return f"s.set{sig[0].upper()}{sig[1:]}(true)"


SETUP = """
  window.__sse = await import('/frontend/app/services/sse.js?v=6');
  const ds = document.createElement('div'); ds.id = 'stage'; document.body.append(ds);
  const { Desktop } = await import('/frontend/app/widgets/desktop.js?v=1');
  window.__desk = new Desktop(ds);
  const dk = document.createElement('div'); dk.id = 'zm-deck-wrap'; document.body.append(dk);
  const { Deck } = await import('/frontend/mobile/app/shell/Deck.js?v=5');
  window.__deck = new Deck(dk);
  window.__pages = (await import('/frontend/mobile/app/shell/pages.js?v=1')).PAGES;
  window.__closeAll = () => { const s = window.__store;
    for (const k of Object.keys(s)) if (/^set\\w+Open$/.test(k)) { try { s[k](false); } catch (_) {} }
    (window.__pages || []).forEach((p) => p[1](false)); s.setChatTab('chat'); };
"""


@pytest.fixture(scope="module")
def pg():
    with open_phone(SETUP) as page:
        page.wait_for_timeout(300)
        yield page


def _last_panel(pg, mount: str):
    reps = [p["body"] for p in pg._posts if p["url"] == "/api/screen/report" and p["body"].get("mount") == mount]
    return reps[-1]["doc"]["panel"] if reps else None


def _desk_failures(pg, mount: str) -> list[str]:
    bad = []
    for sid, toggle in _named():
        pg.evaluate(f"() => {{ const s = window.__store; window.__closeAll(); {_open_js(sid, toggle)}; }}")
        pg.wait_for_timeout(330)
        if (got := _last_panel(pg, mount)) != sid:
            bad.append(f"{sid} open: panel {got!r}")
        pg.evaluate("() => window.__closeAll()")
        pg.wait_for_timeout(330)
        if (got := _last_panel(pg, mount)) != "":
            bad.append(f"{sid} closed: panel {got!r}")
    return bad


def test_every_named_surface_has_a_row_in_the_table(pg):
    known = set(pg.evaluate("async () => (await import('/frontend/app/widgets/screen-panel.js?v=1')).DESKTOP_PANELS.map((r) => r[0])"))
    named = {sid for sid, _ in _named()}
    assert len(named) >= 10, named                   # the parse of system-surfaces.js still finds the surfaces
    assert named - {"apps", "conectores"} <= known, f"named surfaces the panel table does not know: {named - known}"


def test_an_open_panel_is_in_the_desktops_document(pg):
    mount = pg.evaluate("() => window.__desk._screen.rep.mount")
    assert _desk_failures(pg, mount) == []


def test_an_open_page_is_in_the_decks_document(pg):
    mount = pg.evaluate("() => window.__deck._screen.rep.mount")
    ids = pg.evaluate("() => window.__pages.map((p) => p[2])")
    assert ids and all(ids), ids
    for k, sid in enumerate(ids):
        pg.evaluate("(k) => { window.__closeAll(); window.__pages[k][1](true); }", k)
        pg.wait_for_timeout(330)
        assert _last_panel(pg, mount) == sid, (sid, _last_panel(pg, mount))
    pg.evaluate("() => window.__closeAll()")
    pg.wait_for_timeout(330)
    assert _last_panel(pg, mount) == ""
    assert not pg._errors, pg._errors


def test_disarm_an_adapter_that_drops_the_panel_turns_it_red(pg):
    src = ADAPTER.read_text(encoding="utf-8")
    assert src.count(_PANEL) == 1, "disarm did not land"
    pg.route("**/frontend/app/widgets/desktop-screen.js?v=disarm", lambda r: r.fulfill(
        status=200, content_type="text/javascript", body=src.replace(_PANEL, '    panel: () => "",\n')))
    mount = pg.evaluate("""async () => { const m = await import('/frontend/app/widgets/desktop-screen.js?v=disarm');
        window.__disarmed = m.desktopScreen(window.__desk); return window.__disarmed.rep.mount; }""")
    try:
        pg.wait_for_timeout(100)
        assert _desk_failures(pg, mount), "the disarmed adapter stayed green"
    finally:
        pg.evaluate("() => window.__disarmed.rep.dispose()")

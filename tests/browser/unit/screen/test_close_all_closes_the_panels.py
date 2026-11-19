"""«Close all» closes the native surfaces too, on the desk and on the deck (INI-042 #47).

RENDERED: the real desk and deck in one Chromium page (the phone's harness). Every surface of the desk's panel table
(`widgets/screen-panel.js`) is opened, `desk.closeAll({by: "engine"})` — what the engine's close-all reaches — runs,
and no surface is left but the conversation (a wall tab goes back to it). Every page of the phone but the chat is
closed by the deck's `closeAll`. A reset keeps its own lifecycle. Disarm: the desk without its `closePanels()` call.
"""
from __future__ import annotations

import pathlib

import pytest

from tests.browser.unit.mobile.phone_page import open_phone

ENGINE = pathlib.Path(__file__).resolve().parents[4]
DESK = ENGINE / "frontend/app/widgets/desktop.js"
_CALL = 'if(by!=="reset") closePanels();'

SETUP = """
  window.__sp = await import('/frontend/app/widgets/screen-panel.js?v=1');
  const ds = document.createElement('div'); ds.id = 'stage'; document.body.append(ds);
  const { Desktop } = await import('/frontend/app/widgets/desktop.js?v=1');
  window.__desk = new Desktop(ds);
  const dk = document.createElement('div'); dk.id = 'zm-deck-wrap'; document.body.append(dk);
  const { Deck } = await import('/frontend/mobile/app/shell/Deck.js?v=5');
  window.__deck = new Deck(dk);
  window.__pages = (await import('/frontend/mobile/app/shell/pages.js?v=1')).PAGES;
  window.__open = (id) => { const s = window.__store;
    ({ config: () => s.setConfigOpen(true), wizard: () => s.setWizardOpen(true), vault: () => s.setVaultOpen(true),
       'memory-map': () => s.setMemOpen(true), debug: () => s.setDebugOpen(true), status: () => s.setStatusOpen(true),
       feedback: () => s.setFeedbackOpen(true), chat: () => { s.setChatOpen(true); s.setChatTab('apps'); } })[id](); };
"""


@pytest.fixture(scope="module")
def pg():
    with open_phone(SETUP) as page:
        page.wait_for_timeout(300)
        yield page


def _desk_left(pg, desk="window.__desk", by="engine") -> list[str]:
    left = []
    for sid in pg.evaluate("() => window.__sp.DESKTOP_PANELS.map((r) => r[0])"):
        got = pg.evaluate(f"""(sid) => {{ window.__open(sid); {desk}.closeAll({{ by: '{by}' }});
            return window.__sp.panelOf(); }}""", sid)
        if got not in ("", "chat"):
            left.append(f"{sid}: {got}")
        pg.evaluate("() => { const s = window.__store; s.setConfigOpen(false); s.setWizardOpen(false); s.closeVault();"
                    " s.setMemOpen(false); s.setDebugOpen(false); s.setStatusOpen(false); s.setFeedbackOpen(false);"
                    " s.setChatTab('chat'); }")
    return left


def test_the_desks_close_all_leaves_no_surface_but_the_conversation(pg):
    assert len(pg.evaluate("() => window.__sp.DESKTOP_PANELS")) >= 8
    assert _desk_left(pg) == []
    assert not pg._errors, pg._errors


def test_a_reset_keeps_its_own_lifecycle(pg):
    assert pg.evaluate("() => { window.__open('config'); window.__desk.closeAll({ by: 'reset' }); "
                       "const p = window.__sp.panelOf(); window.__store.setConfigOpen(false); return p; }") == "config"


def test_the_decks_close_all_closes_every_page_but_the_chat(pg):
    for k, sid in enumerate(pg.evaluate("() => window.__pages.map((p) => p[2])")):
        if sid == "chat":
            continue
        pg.evaluate("(k) => { window.__pages[k][1](true); window.__deck.closeAll({ by: 'engine' }); }", k)
        pg.wait_for_timeout(60)
        assert pg.evaluate("(k) => window.__pages[k][0]()", k) is False, sid


def test_disarm_a_desk_without_close_panels_turns_it_red(pg):
    src = DESK.read_text(encoding="utf-8")
    assert src.count(_CALL) == 1, "disarm did not land"
    pg.route("**/frontend/app/widgets/desktop.js?v=disarm", lambda r: r.fulfill(
        status=200, content_type="text/javascript", body=src.replace(_CALL, "")))
    pg.evaluate("""async () => { const { Desktop } = await import('/frontend/app/widgets/desktop.js?v=disarm');
        const d = document.createElement('div'); document.body.append(d); window.__bare = new Desktop(d); }""")
    assert _desk_left(pg, "window.__bare"), "the disarmed desk stayed green"

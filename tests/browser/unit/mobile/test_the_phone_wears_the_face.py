"""The phone wears the agent's face too (V2-928 T11, node 4.569).

The operator, 2026-11-17: the face he chose on the computer, on the phone as well — behind the home, Porcelain for
everyone at first, a «Physical presence» switch on the ☰ page by the account rows, and Settings ▸ Presence laid out for
the hand (categories, a strip of faces, the face, «Customise» as a step). What is checked, RENDERED with the real
surfaces of `shell/mobile-surfaces.js` and the real stylesheets in Chromium at 393×852:

  - the face is drawn BEHIND the home: its layer sits between the backdrop and the stage, the home is see-through, and
    a card or a page in front of it stops it drawing;
  - the ☰ row turns it off (no canvas left) and on again, and names the face it wears;
  - Settings ▸ Presence opens as a page, fits the width, reads top to bottom as categories → faces → the face, and its
    back goes to Settings; picking a face wears it; «Customise» hides the categories and the strip; closing the page
    removes its preview;
  - «abre los ajustes de presencia» (the voice act) opens THIS page on the phone, not the desktop's Settings, and the
    phone's back returns from it to Settings.
"""
from __future__ import annotations

import pytest

from tests.browser.unit.mobile.phone_page import open_phone, shot

SETUP = """
  localStorage.removeItem('hb_presence');
  const wrap = document.createElement('div'); wrap.id = 'zm-deck-wrap'; document.body.append(wrap);
  const bg = document.createElement('div'); bg.className = 'zm-bg'; wrap.append(bg);
  const stage = document.createElement('div'); stage.id = 'zm-stage'; wrap.append(stage);
  const { MOBILE_SURFACES } = await import('/frontend/mobile/app/shell/mobile-surfaces.js?v=4');
  // main.js's own mounting rule: a "deck" scaffold goes under the stage
  for (const s of MOBILE_SURFACES.filter(s => s.phase === 'scaffold'))
    s.target === 'deck' ? wrap.insertBefore(s.comp(), stage) : document.body.append(s.comp());
  for (const id of ['menu', 'settings', 'presence-page']) document.body.append(MOBILE_SURFACES.find(s => s.id === id).comp());
  const { Deck } = await import('/frontend/mobile/app/shell/Deck.js?v=5');
  window.__deck = new Deck(stage);
  window.__pages = await import('/frontend/mobile/app/shell/pages.js?v=1'); window.__pages.onePageAtATime();
  window.__presence = await import('/frontend/app/presence/state.js?v=1');
  window.__sheet = await import('/frontend/mobile/app/shell/PresenceSheet.js?v=1');
  window.__controls = await import('/frontend/app/services/self-controls.js?v=1');
"""

_LAYER = """() => {
  const layer = document.getElementById('presence'), wrap = document.getElementById('zm-deck-wrap');
  const kids = [...wrap.children].map(e => e.id || e.className);
  const home = document.querySelector('.zm-home');
  return {
    canvas: !!(layer && layer.querySelector('canvas')),
    order: kids, between: kids.indexOf('presence') > kids.indexOf('zm-bg') && kids.indexOf('presence') < kids.indexOf('zm-stage'),
    homeBg: home ? getComputedStyle(home).backgroundColor : null,
  };
}"""

_PAGE = """() => {
  const page = document.querySelector('.zm-page[data-page="presence"]');
  const r = (s) => { const e = page.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect();
                     return { top: b.top, h: b.height, w: b.width, shown: b.height > 0 && getComputedStyle(e).display !== 'none' }; };
  return { open: page.classList.contains('open'), cats: r('.pz-cats'), list: r('.pz-list'), face: r('.pz-face'),
           edit: r('.pz-edit'), canvas: !!page.querySelector('.pz-face canvas'),
           overflow: document.documentElement.scrollWidth > innerWidth || page.scrollWidth > innerWidth,
           items: page.querySelectorAll('.pz-item').length, on: (page.querySelector('.pz-item.on') || {}).dataset?.id };
}"""


@pytest.fixture(scope="module")
def phone():
    with open_phone(SETUP) as pg:
        pg.wait_for_timeout(800)
        yield pg


def _drawn(pg) -> int:
    """How many frames the face drew in ~0.6 s (its canvas changes while it lives)."""
    return pg.evaluate("""async () => {
      const c = document.querySelector('#presence canvas'); if (!c) return 0;
      let n = 0, prev = c.toDataURL();
      for (let i = 0; i < 6; i++) { await new Promise(r => setTimeout(r, 100)); const d = c.toDataURL(); if (d !== prev) n++; prev = d; }
      return n;
    }""")


def test_the_face_lives_behind_the_home(phone):
    s = phone.evaluate(_LAYER)
    assert s["canvas"], f"no face on the phone's home: {s}"
    assert s["between"], f"the face must sit between the backdrop and the stage (under every card): {s['order']}"
    assert s["homeBg"] in ("rgba(0, 0, 0, 0)", "transparent"), f"the home hides the face behind an opaque background: {s}"
    assert _drawn(phone) > 0, "the face behind the home is a still"
    shot(phone, "presence-home")
    # a page in front covers it whole: it stops drawing, and draws again once the home shows
    phone.evaluate("() => window.__store.setMobileMenuOpen(true)")
    phone.wait_for_timeout(400)
    assert _drawn(phone) == 0, "the face keeps drawing behind an opaque page (battery for nothing)"
    phone.evaluate("() => window.__store.setMobileMenuOpen(false)")
    phone.wait_for_timeout(400)
    assert _drawn(phone) > 0, "the face did not come back to life when the home showed again"


def test_the_menu_switch_turns_the_face_off_and_on(phone):
    phone.evaluate("() => window.__store.setMobileMenuOpen(true)")
    phone.wait_for_timeout(300)
    row = '.zm-page[data-page="menu"] .zm-toggle:has-text("Presencia física")'
    assert phone.locator(row).count() == 1, "the ☰ page has no «Presencia física» switch"
    assert "Porcelana" in phone.locator(row).inner_text(), "the switch must name the face it wears (Porcelain by default)"
    phone.click(row)
    phone.wait_for_timeout(300)
    assert phone.evaluate("() => window.__presence.presenceOn()") is False
    assert not phone.evaluate(_LAYER)["canvas"], "off must mean off: the face's canvas is still there"
    phone.click(row)
    phone.wait_for_timeout(300)
    assert phone.evaluate(_LAYER)["canvas"], "on again, and no face"
    phone.evaluate("() => window.__store.setMobileMenuOpen(false)")


def test_settings_presence_is_a_page_for_the_hand(phone):
    phone.evaluate("() => window.__store.setMobileSettingsOpen(true)")
    phone.wait_for_timeout(300)
    phone.click('.zm-page[data-page="settings"] .zm-row:has-text("Presencia")')
    phone.wait_for_timeout(900)
    s = phone.evaluate(_PAGE)
    assert s["open"] and s["canvas"], f"Settings ▸ Presencia did not open its page with the face: {s}"
    assert not s["overflow"], f"the page is wider than the phone: {s}"
    assert s["cats"]["top"] < s["list"]["top"] < s["face"]["top"], f"phone order must be categories → faces → face: {s}"
    assert s["list"]["h"] < 140, f"on a phone the faces are a strip, not a column: {s['list']}"
    assert s["items"] > 5 and s["on"] == "c-porcelain", f"Porcelain is the face worn by default: {s}"
    shot(phone, "presence-page")

    phone.click('.zm-page[data-page="presence"] .pz-item >> nth=1')
    phone.wait_for_timeout(300)
    picked = phone.evaluate("() => window.__presence.presenceFace()")
    assert picked != "c-porcelain", "picking a face on the phone did not wear it"

    phone.click('.zm-page[data-page="presence"] .pz-custom')
    phone.wait_for_timeout(400)
    s = phone.evaluate(_PAGE)
    assert s["edit"]["shown"] and not s["cats"]["shown"] and not s["list"]["shown"], \
        f"«Customise» is a step on the phone: the knobs replace the categories and the strip: {s}"
    shot(phone, "presence-edit")
    phone.click('.zm-page[data-page="presence"] .pz-cancel')
    phone.evaluate("() => window.__presence.resetPresence()")

    phone.click('.zm-page[data-page="presence"] .zm-page-back')
    phone.wait_for_timeout(300)
    assert phone.evaluate("() => window.__store.mobileSettingsOpen()"), "back from Presence must return to Settings"
    assert not phone.evaluate("() => !!document.querySelector('.zm-page[data-page=\"presence\"] canvas')"), \
        "the closed page kept its live preview"
    phone.evaluate("() => window.__store.setMobileSettingsOpen(false)")


def test_the_voice_opens_the_phone_page(phone):
    phone.evaluate("() => window.__controls.applyControl({ act: 'presence_settings' })")
    phone.wait_for_timeout(500)
    assert phone.evaluate("() => window.__sheet.presenceOpen()"), "«abre los ajustes de presencia» did not open the phone's page"
    assert not phone.evaluate("() => window.__store.configOpen()"), "the voice opened the desktop's Settings on the phone"
    # the phone's own back (Android back, iOS swipe) leaves Presence for Settings, where it was opened from
    assert phone.evaluate("() => window.__pages.backFromPage()")
    assert phone.evaluate("() => !window.__sheet.presenceOpen() && window.__store.mobileSettingsOpen()"), \
        "the platform's back from Presence must land on Settings"
    phone.evaluate("() => window.__store.setMobileSettingsOpen(false)")
    assert not phone._errors, phone._errors

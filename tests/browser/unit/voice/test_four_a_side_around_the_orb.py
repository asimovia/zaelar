"""Four controls a side around the orb, phone and desktop, RENDERED (operator, 2026-11-18).

One side holds the device's tools (🎤 mic · 🔊 speaker · 📷 camera), the other the voice's activation (🤖 wake word ·
«Stick to my voice»). Mounted in Chromium from the real DockBar (375 px, the narrowest phone we fit) and the real Orb
docked into the real WidgetRail (1280 px), with the real store, i18n bundle, presence switch and voice-lock module:
  · each side carries four buttons, none overflows a 375 px screen, none overlaps its neighbour, all 44 px tall;
  · the camera button IS the presence camera switch (`hb_presence_look`), both ways, and says its state;
  · «Stick to my voice» toggles, persists (`hb_voice_lock`), and says «nothing is filtered» until a voice is enrolled;
  · the desktop's eye keeps ⏻ at the apex of nine slots.
Disarms: a camera button wired to nothing, and the bar dock moving three a side — each served in place of the real
module, each turns its check red.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.browser.unit.mobile.phone_page import PACK, open_phone

ROOT = Path(__file__).resolve().parents[4]
ES = PACK["es"]

PHONE = """
  localStorage.removeItem('hb_voice_lock'); localStorage.removeItem('zaelar_spk_profile');
  localStorage.removeItem('hb_presence_look');
  const { DockBar } = await import('/frontend/mobile/app/shell/DockBar.js?v=4');
  document.body.append(DockBar());
  window.__look = await import('/frontend/app/presence/look-state.js?v=1');
  window.__lock = await import('/frontend/app/services/voice-lock.js?v=1');
"""

DESK = """
  localStorage.setItem('hb_orb_dock', 'bar'); localStorage.removeItem('hb_voice_lock');
  localStorage.removeItem('zaelar_spk_profile'); localStorage.removeItem('hb_presence_look');
  const rail = await import('/frontend/app/components/WidgetRail.js?v=2');
  const el = rail.WidgetRail ? rail.WidgetRail() : null; if (el && !el.isConnected) document.body.append(el);
  const { Orb } = await import('/frontend/app/components/Orb.js?v=3');
  document.body.append(Orb());
  window.__store.setOrbDock('bar');   // the store had read `hb_orb_dock` before the setup wrote it
  window.__look = await import('/frontend/app/presence/look-state.js?v=1');
  window.__lock = await import('/frontend/app/services/voice-lock.js?v=1');
"""

_SIDES = """() => [...document.querySelectorAll('.zm-dock .zm-side')].map(s =>
  [...s.querySelectorAll(':scope > button')].map(b => { const r = b.getBoundingClientRect();
    return {ctl: b.dataset.ctl || '', l: r.left, r: r.right, h: r.height}; }))"""
_BTN = """(sel) => { const b = document.querySelector(sel);
  return b && {label: b.getAttribute('aria-label') || b.getAttribute('title'), cls: b.className,
               svg: b.querySelector('svg') ? b.querySelector('svg').outerHTML.length : 0}; }"""
_FLANKS = """() => ({l: [...document.querySelectorAll('#wrail .wr-orbl > button')].map(b => b.dataset.ctl || b.className),
                  r: [...document.querySelectorAll('#wrail .wr-orbr > button')].map(b => b.dataset.ctl
                     || (b.classList.contains('wr-swap') ? 'wr-swap' : b.className))})"""


def _served(rel: str, mutate) -> tuple:
    """A route that serves `rel` with `mutate(src)` instead of the file — the disarm, in the real page."""
    src = (ROOT / rel).read_text(encoding="utf-8")
    bad = mutate(src)
    assert bad != src, f"the mutation of {rel} did not land"
    return (lambda url: url.split("?")[0].endswith("/" + rel)), \
        (lambda r: r.fulfill(status=200, content_type="text/javascript", body=bad))


def _phone_checks(tab) -> dict:
    sides = tab.evaluate(_SIDES)
    width = tab.evaluate("() => document.documentElement.scrollWidth")
    cam0 = tab.evaluate("() => window.__look.lookCamera()")
    tab.click(".zm-dock [data-ctl='cam']")
    tab.wait_for_timeout(100)
    cam1 = tab.evaluate("() => ({on: window.__look.lookCamera(), kept: localStorage.getItem('hb_presence_look')})")
    return {"sides": sides, "width": width, "cam0": cam0, "cam1": cam1,
            "camBtn": tab.evaluate(_BTN, ".zm-dock [data-ctl='cam']")}


def test_the_phone_dock_is_four_a_side_and_fits_375():
    with open_phone(PHONE, width=375, height=812) as tab:
        tab.wait_for_timeout(300)
        g = _phone_checks(tab)
        left, right = g["sides"]
        assert [b["ctl"] for b in left][-2:] == ["lock", "bot"], f"the voice's activation beside the orb: {left}"
        assert [b["ctl"] for b in right] == ["mic", "", "cam", "apps"], f"the device's tools (🔊 carries no id): {right}"
        assert len(left) == 4 and len(right) == 4, g["sides"]
        assert g["width"] <= 375, f"the dock overflows a 375 px phone: {g['width']}"
        for side in g["sides"]:
            assert all(b["l"] >= 0 and b["r"] <= 375 and b["h"] >= 44 for b in side), side
            assert all(side[i + 1]["l"] >= side[i]["r"] for i in range(3)), f"neighbours overlap: {side}"
        # the camera button IS the presence switch, both ways
        assert g["cam0"] is True and g["cam1"]["on"] is False and '"camera":false' in (g["cam1"]["kept"] or ""), g
        assert g["camBtn"]["label"] == ES["orb.camera_off"] and g["camBtn"]["svg"], g["camBtn"]
        tab.evaluate("() => window.__look.setLookCamera(true, 'badge')")   # another door (Settings, the badge) moves it
        tab.wait_for_timeout(50)
        assert tab.evaluate(_BTN, ".zm-dock [data-ctl='cam']")["label"] == ES["orb.camera_on"]
        # «Stick to my voice»: off by default, on says «nothing filtered» until a voice is enrolled
        lock = lambda: tab.evaluate(_BTN, ".zm-dock [data-ctl='lock']")   # noqa: E731
        assert lock()["label"] == ES["orb.voice_lock_off"] and " off" in lock()["cls"], lock()
        tab.click(".zm-dock [data-ctl='lock']")
        tab.wait_for_timeout(50)
        assert tab.evaluate("() => [window.__lock.voiceLock(), localStorage.getItem('hb_voice_lock')]") == [True, "1"]
        assert lock()["label"] == ES["orb.voice_lock_unenrolled"] and "wait" in lock()["cls"], lock()
        tab.evaluate("() => window.__lock.saveProfile({pitch: {m: 120, s: 10}, centroid: {m: 900, s: 80}, rms: {m: .1}})")
        tab.wait_for_timeout(50)
        assert lock()["label"] == ES["orb.voice_lock_on"] and " on" in lock()["cls"], lock()
        assert not tab._errors, tab._errors


def test_the_disarm_a_camera_button_wired_to_nothing_is_red():
    route = _served("frontend/mobile/app/shell/DockBar.js",
                    lambda s: s.replace('onClick: () => setLookCamera(!lookCamera(), "dock")', "onClick: () => {}"))
    with open_phone(PHONE, width=375, height=812, routes=[route]) as tab:
        tab.wait_for_timeout(300)
        g = _phone_checks(tab)
        assert g["cam1"]["on"] is True, "with the button disarmed the switch does not move — the check above sees it"


def _desk(routes=()):
    return open_phone(DESK, width=1280, height=800, routes=routes)


def test_the_desktop_bar_is_four_a_side_and_both_toggles_move():
    with _desk() as tab:
        tab.wait_for_function("() => document.querySelectorAll('#wrail .wr-orbl > button').length > 0", timeout=5000)
        f = tab.evaluate(_FLANKS)
        assert f["l"] == ["mic", "spk", "cam", "cap"], f"the device side: {f}"
        assert f["r"] == ["bot", "lock", "chat", "wr-swap"], f"the voice side: {f}"
        tab.click("#wrail [data-ctl='lock']")
        tab.click("#wrail [data-ctl='cam']")
        tab.wait_for_timeout(100)
        st = tab.evaluate("() => [window.__lock.voiceLock(), window.__look.lookCamera()]")
        assert st == [True, False], st
        assert tab.evaluate(_BTN, "#wrail [data-ctl='lock']")["label"] == ES["orb.voice_lock_unenrolled"]
        assert tab.evaluate(_BTN, "#wrail [data-ctl='cam']")["label"] == ES["orb.camera_off"]
        # back to the eye: nine slots, ⏻ at the apex
        tab.evaluate("() => window.__store.setOrbDock('eye')")
        tab.wait_for_timeout(100)
        lid = tab.evaluate("() => [...document.querySelectorAll('#orbwrap .orbctl > button')].map(b => b.dataset.ctl)")
        assert lid == ["tobar", "mic", "spk", "cam", "pwr", "cap", "chat", "bot", "lock"], lid
        assert not tab._errors, tab._errors


def test_the_disarm_three_a_side_on_the_desktop_bar_is_red():
    route = _served("frontend/app/components/Orb.js",
                    lambda s: s.replace('ctls("mic", "spk", "cam", "cap")', 'ctls("mic", "spk", "cap")'))
    with _desk([route]) as tab:
        tab.wait_for_function("() => document.querySelectorAll('#wrail .wr-orbl > button').length > 0", timeout=5000)
        assert tab.evaluate(_FLANKS)["l"] == ["mic", "spk", "cap"], "the disarmed dock is three a side — the check sees it"


def test_every_new_label_is_in_both_bundles():
    keys = set()
    for rel in ("frontend/app/components/Orb.js", "frontend/mobile/app/shell/DockBar.js",
                "frontend/app/services/voice-lock.js"):
        keys |= set(re.findall(r'"(orb\.(?:camera|voice_lock)_[a-z]+)"', (ROOT / rel).read_text(encoding="utf-8")))
    assert len(keys) == 6, keys
    for lang in ("es", "en"):
        missing = sorted(k for k in keys if not PACK[lang].get(k))
        assert not missing, (lang, missing)
        assert not any(re.search(r"\bapps?\b", PACK[lang][k], re.I) for k in keys), "the word is «widget», never «app»"

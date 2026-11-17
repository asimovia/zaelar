"""His own controls by VOICE move the BUTTONS on the screen that heard him, phone and desktop (V2-930, node 4.571).

The `.mjs` beside this file drives the real `self-controls.js` + `volume.js` with recorded doors (target state, read
back, clamps, persistence, one-way after the line, order). Here the same `controls` event is applied to the RENDERED
shells in Chromium with their real modules: the phone's dock (🔊 / 🎤 / the level line) and Settings row, and the
desktop orb's lid (🔊 / 🎤) with its level popover — and the bot's <audio> element plays at the level. Plus the wiring
the `.mjs` cannot see: the doors it names exist, the level is the element's, and nothing on the path waits on the page
being visible (the phone's screen may be locked).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.browser.unit.mobile.phone_page import PACK, open_phone

SCRIPT = Path(__file__).with_name("test_his_controls_move_the_buttons.mjs")
ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "frontend" / "app"
ES = PACK["es"]


def _code(p: Path) -> str:
    return "\n".join(s for s in (l.strip() for l in p.read_text(encoding="utf-8").splitlines())
                     if s and not s.startswith("//"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_his_controls_move_the_buttons_by_target_state():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_nothing_on_the_path_waits_on_a_visible_page():
    """A locked phone keeps its event stream (iOS background audio): the controls path must not gate on visibility
    or ride an animation frame, or a voice order would wait for him to unlock the screen."""
    for rel in ("services/self-controls.js", "services/volume.js", "components/VolumeSlider.js"):
        src = _code(APP / rel)
        for gate in ("document.hidden", "visibilityState", "requestAnimationFrame"):
            assert gate not in src, f"{rel} gates on {gate}"
    sse = _code(APP / "services" / "sse.js")
    i = sse.index('d.kind === "controls"')
    assert "self-controls.js" in sse[i:i + 200]


def test_the_bot_audio_follows_the_level_through_one_door():
    for rel in ("services/session-lk.js", "services/session.js"):
        s = _code(APP / rel)
        assert "vol.enforce(el)" in s and "vol.bind(el)" in s and "vol.enforce(botAudioEl)" in s, rel
        assert not re.search(r"\.volume = store\.botMuted\(\)", s), f"{rel}: a second writer of the element's volume"


SETUP = """
  localStorage.removeItem('hb_bot_volume'); localStorage.setItem('hb_bot_muted', '0'); localStorage.setItem('hb_mic_muted', '0');
  const { MOBILE_SURFACES } = await import('/frontend/mobile/app/shell/mobile-surfaces.js?v=4');
  for (const id of ['dock', 'settings']) document.body.append(MOBILE_SURFACES.find(s => s.id === id).comp());
  window.__controls = await import('/frontend/app/services/self-controls.js?v=1');
  window.__volume = await import('/frontend/app/services/volume.js?v=1');
  const session = await import('/frontend/app/services/session.js?v=3');
  const a = document.createElement('audio'); a.id = 'botaudio'; document.body.append(a); session.attachBotAudio(a);
"""

DESK = """
  localStorage.removeItem('hb_bot_volume'); localStorage.setItem('hb_bot_muted', '0'); localStorage.setItem('hb_mic_muted', '0');
  const { Orb } = await import('/frontend/app/components/Orb.js?v=3');
  document.body.append(Orb());
  window.__controls = await import('/frontend/app/services/self-controls.js?v=1');
  window.__volume = await import('/frontend/app/services/volume.js?v=1');
  const session = await import('/frontend/app/services/session.js?v=3');
  const a = document.createElement('audio'); a.id = 'botaudio'; document.body.append(a); session.attachBotAudio(a);
"""

_STATE = """(sel) => {
  const q = (s) => document.querySelector(s);
  const spk = q(sel.spk), mic = q(sel.mic), pop = q(sel.pop), row = sel.row ? q(sel.row) : null;
  return { spk: spk && (spk.getAttribute('aria-label') || spk.getAttribute('title')),
           mic: mic && (mic.getAttribute('aria-label') || mic.getAttribute('title')),
           popShown: !!(pop && pop.classList.contains('show')), popValue: pop && pop.querySelector('input').value,
           rowValue: row && row.querySelector('input').value, audio: q('#botaudio').volume, audioMuted: q('#botaudio').muted,
           muted: window.__store.botMuted(), stored: localStorage.getItem('hb_bot_volume') };
}"""

def _either(root: str, *keys: str) -> str:
    """The dock button whose label is one of its two states (the dock's buttons carry no stable id of their own)."""
    return ", ".join(f"{root} button[aria-label='{ES[k]}']" for k in keys)


PHONE_SEL = {"spk": _either(".zm-dock", "orb.speaker_muted", "orb.speaker_unmuted"),
             "mic": _either(".zm-dock", "camera.mic_mute", "camera.mic_unmute"), "pop": ".zm-volnote", "row": ".zm-vol"}
DESK_SEL = {"spk": "[data-ctl='spk']", "mic": "[data-ctl='mic']", "pop": ".volpop", "row": None}


def _apply(pg, d):
    pg.evaluate("(d) => window.__controls.applyControl(d)", d)
    pg.wait_for_timeout(150)


@pytest.mark.parametrize("shell", ["phone", "desktop"])
def test_a_voice_control_moves_the_shells_buttons(shell):
    setup, sel, size = (SETUP, PHONE_SEL, {}) if shell == "phone" else (DESK, DESK_SEL, {"width": 1280, "height": 800})
    with open_phone(setup, **size) as pg:
        pg.wait_for_timeout(500)
        st = lambda: pg.evaluate(_STATE, sel)   # noqa: E731
        assert st()["spk"] == ES["orb.speaker_unmuted"], st()
        _apply(pg, {"act": "mute"}); _apply(pg, {"act": "mute"})
        s = st()
        assert s["muted"] and s["spk"] == ES["orb.speaker_muted"] and s["audioMuted"] and s["audio"] == 0, s
        _apply(pg, {"act": "unmute"})
        s = st()
        assert not s["muted"] and s["spk"] == ES["orb.speaker_unmuted"] and not s["audioMuted"], s
        _apply(pg, {"act": "volume_set", "value": 30})
        s = st()
        assert s["popShown"] and s["popValue"] == "30" and s["stored"] == "30", s
        assert abs(s["audio"] - 0.3) < 1e-6, f"the bot's audio must play at the level: {s}"
        if sel["row"]:
            assert s["rowValue"] == "30", f"the Settings row is the same door: {s}"
        _apply(pg, {"act": "volume_up"})
        assert st()["popValue"] == "50"
        _apply(pg, {"act": "mic_off"})
        assert pg.evaluate("() => window.__store.micMuted()") is True
        assert st()["mic"] == ES["camera.mic_unmute"], st()
        assert not pg._errors, pg._errors


def test_the_desktop_wheel_on_the_speaker_moves_the_level():
    with open_phone(DESK, width=1280, height=800) as pg:
        pg.wait_for_timeout(500)
        pg.hover("[data-ctl='spk']")
        pg.mouse.wheel(0, -100)
        pg.wait_for_timeout(150)
        assert pg.evaluate("() => window.__volume.level()") == 100, "louder past 100 stays at 100"
        pg.mouse.wheel(0, 100); pg.mouse.wheel(0, 100)
        pg.wait_for_timeout(150)
        s = pg.evaluate(_STATE, DESK_SEL)
        assert s["popShown"] and s["popValue"] == "90" and abs(s["audio"] - 0.9) < 1e-6, s

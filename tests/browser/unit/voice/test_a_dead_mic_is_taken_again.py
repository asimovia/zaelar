"""Exposes the DEAD-MIC contract to pytest: a capture track the system ends is taken again, and a mic nobody can use is
RED, SLASHED and a tap that recovers it, on both shells.

The behaviour is driven in the `.mjs` beside this file over the REAL modules. The cases here are the WIRING: a revive
nothing calls, a fault the phone's dock never paints, or a red icon whose tap still toggles the mute would keep the
`.mjs` green while the person still talks to a deaf session.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_dead_mic_is_taken_again.mjs")
ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "frontend" / "app"
MOBILE = ROOT / "frontend" / "mobile" / "app"


def _code(p: Path) -> str:
    return "\n".join(s for s in (l.strip() for l in p.read_text(encoding="utf-8").splitlines())
                     if s and not s.startswith("//"))


def _mic_button(src: str) -> str:
    i = src.index('"data-ctl": "mic"')
    start = src.rfind('h("button"', 0, i)
    end = src.index('h("button"', i)
    return src[start:end]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_a_dead_mic_is_taken_again_and_an_unusable_mic_is_red():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def session_wiring_problems(s: str) -> list[str]:
    """What is missing for the session engine to act on a lost track and on rooms without an agent (empty = wired)."""
    out = []
    if "health.onMicLost(" not in s:
        out.append("nobody listens for a lost capture track")
    if "_micDevice.revive(" not in s:
        out.append("a lost track is not taken again")
    body = s[s.index("function _noAgent("):]
    body = body[:body.index("\n}") if "\n}" in body else len(body)]
    if 'health.setCondition("mic", "no_agent", true' not in body:
        out.append("rooms without the agent never reach the mic's health")
    pc = s[s.index("RoomEvent.ParticipantConnected"):]
    pc = pc[:pc.index("});")]
    if 'health.setCondition("mic", "no_agent", false' not in pc:
        out.append("the agent joining does not clear no_agent")
    if "export const recoverMic = createMicRecover(" not in s:
        out.append("no recover door for the tap")
    return out


def test_the_session_takes_a_lost_track_again_and_says_when_no_agent_comes():
    assert session_wiring_problems(_code(APP / "services" / "session-lk.js")) == []


@pytest.mark.parametrize("path", [APP / "components" / "Orb.js", MOBILE / "shell" / "DockBar.js"],
                         ids=["desktop-orb", "mobile-dock"])
def test_an_unusable_mic_is_red_slashed_and_its_tap_recovers(path):
    btn = _mic_button(_code(path))
    assert re.search(r'store\.micHealth\(\)\.ok \? "" : " problem"', btn), "the class must read the mic's health"
    assert re.search(r"!store\.micHealth\(\)\.ok \|\| store\.micMuted\(\) \? MIC_OFF", btn), "a fault is SLASHED"
    click = btn[btn.index("onClick"):]
    rec = click.index("session.recoverMic")
    assert click.index("if (!store.micHealth().ok") < rec < click.index("mic.toggle("), \
        "a red mic's tap must recover it before anything toggles the mute"
    assert "return;" in click[rec:click.index("mic.toggle(")]


def test_the_phone_says_why_in_words():
    dock = _code(MOBILE / "shell" / "DockBar.js")
    assert "store.micBlocked().show" in dock and "store.micBlocked().msg" in dock
    css = (MOBILE / "styles.css").read_text(encoding="utf-8")
    assert re.search(r"\.zm-ic\.problem[^{]*\{[^}]*var\(--hb-risk\)", css)
    assert ".zm-micnote.show" in css


def test_every_new_sentence_is_translated():
    keys = ["orb.mic_problem_no_agent", "voice.mic_allow_app_ios", "voice.mic_allow_app_android",
            "voice.mic_allow_ios_safari", "voice.mic_allow_browser"]
    for lang in ("es", "en"):
        b = json.loads((ROOT / "i18n" / "genesis" / lang / "ui.json").read_text(encoding="utf-8"))
        assert not [k for k in keys if not b.get(k)], lang

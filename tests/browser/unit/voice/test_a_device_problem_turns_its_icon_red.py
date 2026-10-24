"""Exposes the DEVICE HEALTH contract to pytest (V2-788, node 3.119).

The behaviour — a problem turns the device's health red and reports a client event, clearing it restores, a
deliberate mute is not red — is driven in the `.mjs` beside this file over the REAL `device-health.js` and
`store.js`. The cases here are the WIRING: a correct detector that nothing calls, or a verdict the orb never
reads, would keep the `.mjs` green while the operator still sees a blue icon over a speaker he cannot hear.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_device_problem_turns_its_icon_red.mjs")
ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "frontend" / "app"


def _code(p: Path) -> str:
    return "\n".join(s for s in (l.strip() for l in p.read_text(encoding="utf-8").splitlines())
                     if s and not s.startswith("//"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_a_device_problem_turns_its_icon_red_and_clears_by_itself():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def orb_wiring_problems(orb: str) -> list[str]:
    """What is missing for the orb to paint the derived verdict (empty = wired)."""
    out = []
    for dev, health in (("mic", "store.micHealth()"), ("spk", "store.spkHealth()")):
        i = orb.find(f'"data-ctl": "{dev}"')
        if i < 0:
            out.append(f"no {dev} button"); continue
        btn = orb[i:i + 1600]
        if not re.search(re.escape(health) + r'\.ok \? "" : " problem"', btn):
            out.append(f"{dev}: class does not read {health}")
        if f'problemTitleKey("{dev}", {health}.reason)' not in btn:
            out.append(f"{dev}: title does not name the reason")
    return out


def test_the_orb_paints_the_verdict_on_both_icons():
    assert orb_wiring_problems(_code(APP / "components" / "Orb.js")) == []


def test_a_red_speaker_click_recovers_instead_of_muting():
    orb = _code(APP / "components" / "Orb.js")
    btn = orb[orb.index('"data-ctl": "spk"'):]
    btn = btn[:btn.index("session.toggleBotMute()")]
    assert "if (!store.spkHealth().ok)" in btn and "session.unlockAudio" in btn and "return;" in btn


def test_the_session_feeds_every_detector():
    s = _code(APP / "services" / "session-lk.js")
    for call in ("health.watchBotElement(el)", "health.watchMicTrack(captured.getAudioTracks()[0])",
                 "health.micCaptureResult(null)", "health.micCaptureResult(err)",
                 "health.watchRemoteTrack(track.mediaStreamTrack)", "health.watchAudioContext(audio.context())",
                 "_installHealth();", "health.clearSession()"):
        assert call in s, call
    stop = s[s.index("export async function stop()"):s.index("export async function reset()")]
    assert "health.clearSession()" in stop, "a stopped session must take its conditions with it"


def test_problem_is_red_and_beats_the_off_state():
    css = (APP / "styles.css").read_text(encoding="utf-8")
    m = re.search(r"\.orbic\.problem,\.orbic\.problem\.off,\.orbic\.problem\.on\{([^}]*)\}", css)
    assert m and "var(--hb-risk)" in m.group(1) and "opacity:1" in m.group(1)


def test_every_reason_has_a_translated_title():
    src = (APP / "services" / "device-health.js").read_text(encoding="utf-8")
    keys = set(re.findall(r'"(orb\.(?:mic|spk|device)_problem[a-z_]*)"', src))
    assert len(keys) >= 15
    for lang in ("es", "en"):
        b = json.loads((ROOT / "i18n" / "genesis" / lang / "ui.json").read_text(encoding="utf-8"))
        missing = sorted(k for k in keys if not b.get(k))
        assert not missing, (lang, missing)

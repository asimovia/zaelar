"""The device controls are a MIRROR of what the devices do — never OFF while ON (2026-11-18, session af04be1f).

The engine restarted, the screen reconnected, and the engine transcribed a sentence he was dictating elsewhere while he
believed the 🎤 was off. The `.mjs` beside this file drives the behaviour over the real `services/mic.js` and
`services/mic-wire.js`; the checks below hold every surface to it — a session engine that published before muting, a
button that painted the switch instead of the wire, or a meter that moved over a closed mic would keep the `.mjs` green
while the person is still being heard.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "frontend" / "app"
DOCK = ROOT / "frontend" / "mobile" / "app" / "shell" / "DockBar.js"
SCRIPT = Path(__file__).with_name("test_the_mic_icon_mirrors_the_wire.mjs")


def _code(p: Path) -> str:
    src = p.read_text(encoding="utf-8")
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", src)


def _mic_button(src: str) -> str:
    i = src.index('"data-ctl": "mic"')
    start = src.rfind('h("button"', 0, i)
    return src[start:src.index('h("button"', i)]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_mirror_and_the_closed_birth():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_the_session_publishes_already_closed_and_hands_over_its_probe():
    s = _code(APP / "services" / "session-lk.js")
    assert "publishTrack(new LocalAudioTrack" not in s, "a bare publish comes up OPEN and is muted only afterwards"
    pub = s.index("await publishMic({ track: micTrack, closed: mic.muted() || _tapParked")
    reg = s.index("mic.useTransport(_applyMicTransport, () => wireOpen(room));")
    assert pub < reg, "the track is born closed BEFORE the transport is registered, never muted after it went out"
    assert "if (mic.muted()) captured.getAudioTracks().forEach((tr) => { tr.enabled = false; });" in s, \
        "a capture taken while the switch is closed is silent from its first frame"


@pytest.mark.parametrize("path", [APP / "components" / "Orb.js", DOCK], ids=["desktop-orb", "mobile-dock"])
def test_every_mic_button_paints_the_wire(path):
    btn = _mic_button(_code(path))
    assert re.search(r"raw\(micOn\(\) \? MIC_(ICON|ON) : MIC_OFF\)", btn), "the glyph is the wire, not the switch"
    assert "store.micMuted() ? MIC_OFF" not in btn and "store.micMuted() ? t(" not in btn
    click = btn[btn.index("onClick"):]
    assert click.index("if (micOn())") < click.index("recoverMic"), "an open glyph closes first: off wins"
    assert "mic.toggle(" not in click, "a blind toggle flips the SWITCH, which a mismatch makes the opposite of the icon"
    code = _code(path)
    assert "mic.iconOpen(" in code


def test_nothing_reads_a_level_off_a_closed_mic():
    viz = _code(APP / "services" / "visualizer.js")
    assert "const micAn = live && micShownOpen() ? micAnalyser() : null;" in viz, \
        "the meter, the face's «hearing» and the spectrum all read this level: closed mic, no level"


def test_the_camera_button_shows_a_live_capture_whatever_the_switch():
    orb = _code(APP / "components" / "Orb.js")
    assert "const camOn = () => lookCamera() || cameraLive();" in orb
    i = orb.index('"data-ctl": "cam"')
    btn = orb[i:orb.index('h("button"', i)]
    assert "raw(camOn() ? CAMERA_ICON : CAMERA_OFF_ICON)" in btn and "setLookCamera(!camOn()" in btn


def test_the_local_ear_never_runs_over_a_closed_mic():
    s = _code(APP / "services" / "session-lk.js")
    body = s[s.index("function _applyEar()"):]
    body = body[:body.index("\n}")]
    assert "!store.micMuted()) wake.start(); else wake.stop();" in body


def test_the_lock_carries_the_switch():
    api = _code(APP / "services" / "api.js")
    assert re.search(r"sessionAcquire = \(sid, muted\)", api) and re.search(r"sessionSteal = \(sid, muted\)", api)
    s = _code(APP / "services" / "session-lk.js")
    assert "api.sessionSteal(SID, mic.muted())" in s and "api.sessionAcquire(SID, mic.muted())" in s

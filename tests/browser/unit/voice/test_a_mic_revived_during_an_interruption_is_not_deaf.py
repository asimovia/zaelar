"""An iOS audio interruption must not leave the microphone DEAF (2026-11-18, measured on b154).

The page revived the mic while the audio session was still interrupted; the fresh track was born muted, was swapped into
the sender and the log said «reopened»; when the interruption ended the orb moved (two captures stacked on the analyser)
while the server received pure silence until the session ended.

The behaviour is driven in the `.mjs` beside this file over the real modules. Each disarm below mutates ONE guard in a
COPY of `frontend/app` (the operator's engine serves the real tree) and must turn the `.mjs` red. The wiring check holds
the session engine to handing in what proves and escalates a revive.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_mic_revived_during_an_interruption_is_not_deaf.mjs")
ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "frontend" / "app"

NODE = shutil.which("node")

# (file under frontend/app, the guard, its disarmed form, what must break)
DISARMS = [
    ("services/device-health.js", "if (!_interrupted()) { _lost(why); return; }", "{ _lost(why); return; }",
     "a loss inside an interruption revives at once"),
    ("services/device-health.js", "if (track.muted) armMute();", "",
     "a track born muted is only painted"),
    ("services/device-health.js", "if (_ctx && _ctx.state !== \"running\" && _ctx.state !== \"closed\" && _ctx.resume) _ctx.resume()",
     "if (false) _ctx.resume()", "the context is not resumed when the interruption ends"),
    ("services/mic-device.js", "if (old && !old.__silent) {", "if (false) {",
     "the old capture is not stopped before the device is asked for"),
    ("services/mic-device.js", "if (born && !born.muted && await flows()) return true;",
     "if (born && await flows()) return true;", "a track born muted is not republished"),
    ("services/audio.js", "try { if (micSrc) micSrc.disconnect(); } catch (_) {}", "",
     "a rebind stacks analyser sources"),
]


def _run(script: Path) -> subprocess.CompletedProcess:
    return subprocess.run([NODE, str(script)], capture_output=True, text=True, timeout=60)


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_an_interruption_waits_and_a_revive_is_proved():
    r = _run(SCRIPT)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


@pytest.mark.skipif(NODE is None, reason="node not installed")
@pytest.mark.parametrize("rel,guard,disarmed,why", DISARMS, ids=[d[3] for d in DISARMS])
def test_disarm_each_guard_turns_red(tmp_path, rel, guard, disarmed, why):
    shutil.copytree(APP, tmp_path / "frontend" / "app")
    script = tmp_path / "tests" / "browser" / "unit" / "voice" / SCRIPT.name
    script.parent.mkdir(parents=True)
    shutil.copy(SCRIPT, script)
    assert _run(script).returncode == 0, "the copy must be green before it is disarmed"
    target = tmp_path / "frontend" / "app" / rel
    src = target.read_text(encoding="utf-8")
    assert src.count(guard) == 1, f"the guard moved: {guard}"
    target.write_text(src.replace(guard, disarmed), encoding="utf-8")
    assert guard not in target.read_text(encoding="utf-8"), "the disarm did not land"
    assert _run(script).returncode != 0, f"disarmed ({why}) and still green: the test does not guard it"


def test_the_session_hands_in_what_proves_a_revive():
    s = re.sub(r"(?m)^\s*//.*$", "", (APP / "services" / "session-lk.js").read_text(encoding="utf-8"))
    body = s[s.index("const _micDevice = createMicDevice({"):s.index("function _reviveMic(")]
    for key in ("current: () => stream", "probe: async", "sentLevel(room)", "republish: async", "republishMic({",
                "restart: async"):
        assert key in body, f"the session engine does not hand in `{key}`"
    restart = body[body.index("restart: async"):]
    assert restart.index("tr.stop()") < restart.index("await stop()"), \
        "a restart stops the dead capture first, or the warm park hands the same muted track back"

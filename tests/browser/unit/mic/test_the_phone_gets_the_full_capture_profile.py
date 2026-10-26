"""The phone opens its mic with the full capture profile (V2-812 T-08, node 4.299).

The old «is it a Mac» check matched iPhone/iPad, so the phone got echo cancellation only — no noise suppression, no
gain control. The behaviour is driven in the `.mjs` beside this file over the REAL `mic-profile.js`; the cases here
are the wiring (the session actually uses it) and the disarm (the old check turns the `.mjs` red).
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_phone_gets_the_full_capture_profile.mjs")
ROOT = Path(__file__).resolve().parents[4]
PROFILE = ROOT / "frontend" / "app" / "services" / "mic-profile.js"
SESSION = ROOT / "frontend" / "app" / "services" / "session-lk.js"
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _run(module: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, **({"MIC_PROFILE": str(module)} if module else {}))
    return subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60, env=env)


@needs_node
def test_each_platform_opens_the_mic_with_its_profile():
    r = _run()
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


@needs_node
@pytest.mark.parametrize("old, new, why", [
    # the original bug: iPhone/iPad counted as a Mac
    ('if (/iPhone|iPad|iPod|Android/i.test(plat) || /iPhone|iPad|iPod|Android/i.test(ua)) return "mobile";\n', "",
     "an iPhone read as a Mac"),
    # voiceIsolation asked blind
    ("if (sup.voiceIsolation === true) base.voiceIsolation = true;", "base.voiceIsolation = true;",
     "voiceIsolation asked where unsupported"),
])
def test_disarm_the_old_checks_turn_it_red(tmp_path, old, new, why):
    src = PROFILE.read_text(encoding="utf-8")
    assert src.count(old) == 1, f"disarm did not land: {why}"
    mutated = tmp_path / "mic-profile.js"
    mutated.write_text(src.replace(old, new), encoding="utf-8")
    assert _run(mutated).returncode != 0, f"the test stayed green with {why}"


def test_the_session_takes_its_profile_from_the_module():
    s = SESSION.read_text(encoding="utf-8")
    assert re.search(r'import \{[^}]*defaultMicMode[^}]*captureConstraints[^}]*\} from "\./mic-profile\.js', s)
    assert "return defaultMicMode(navigator);" in s
    assert "const ad = { ...captureConstraints(mode, navigator), channelCount: 1 };" in s
    assert not re.search(r"iP\(hone\|ad", s), "the Mac check that matched iPhone must not come back"

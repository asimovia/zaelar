"""One black veil over the whole screen when the engine sleeps or the voice moves (2026-11-10).

The engine's goodnight (`engine.sleep`) used to dim the orb and leave every panel and the chat wall looking usable
over an engine that was gone; the voice taken by another screen showed a different notice on each shell. Now ONE
shared component (`frontend/app/components/Veil.js`, V2-881: also the stopped agent's) covers the whole screen, on both shells, with the gesture
that fixes each case: Reactivate (the stream reopens with `wake=1`, and the veil waits until it answers) or «use it
here». The state machine is driven by the `.mjs` beside this file; the checks below hold the wiring around it.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_one_black_veil_when_the_engine_sleeps_or_the_voice_moves.mjs")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_veil_state_and_the_presence_beat():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_the_engine_hears_a_connected_screen():
    sse = Path("frontend/app/services/sse.js").read_text(encoding="utf-8")
    assert "beat: screensPresent, dormant: store.setDormant" in sse
    api = Path("frontend/app/services/api.js").read_text(encoding="utf-8")
    assert re.search(r'screensPresent = \(\) => \{[^}]*present: true', api)
    srv = Path("server/screens_api.py").read_text(encoding="utf-8")
    assert 'get("present") and visible is True' in srv and "screens.present(dev)" in srv

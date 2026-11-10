"""A refused microphone waits for a gesture: `session.start()` never loops on a capture the browser refuses.

main.js re-enters `session.start()` from a reactive effect whenever `starting` drops; a refusal (denied, no device,
a policy) fails instantly, so without a gate the tab asked the browser again and again, endlessly. The `.mjs` beside
this file drives the gate (`services/mic-denial.js`); the check below holds both transports to it.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_refused_mic_waits_for_a_gesture.mjs")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_gate_holds_until_a_gesture():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


@pytest.mark.parametrize("path", ["frontend/app/services/session-lk.js", "frontend/app/services/session.js"])
def test_both_transports_stop_at_the_gate_and_feed_it(path):
    src = Path(path).read_text(encoding="utf-8")
    start = src[src.index("export async function start()"):]
    head = start[:start.index("getUserMedia")]
    assert "micDenial.waitingForGesture()) return" in head, f"{path}: start() must return before asking again"
    assert re.search(r"catch \(err\) \{[^}]*?micDenial\.noteCaptureError\(err\)", start, re.S), f"{path}: the refusal is recorded"

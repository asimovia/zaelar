"""A closed microphone releases the device, and opening it reacquires it (2026-11-11).

Closing the 🎤 only disabled the capture track, so the browser kept the device captured and its red recording dot lit.
The `.mjs` beside this file drives `frontend/app/services/mic-device.js`; the checks below hold the session engine to
it: the operator's switch releases, the wake-word park never does, and a new capture owns the device again.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_closed_mic_releases_the_device.mjs")
SRC = Path("frontend/app/services/session-lk.js")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_release_and_reacquire():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_the_switch_releases_and_the_park_does_not():
    src = SRC.read_text(encoding="utf-8")
    body = src[src.index("function _applyMicTransport(want)"):]
    body = body[:body.index("\n}\n")]
    assert "if (want) _micDevice.release(stream);" in body, "the operator's closed mic must release the device"
    assert "_micDevice.reacquire(" in body, "…and opening it must reacquire it"
    assert not re.search(r"if \(off\) _micDevice\.release", body), "the wake-word park must never release the device"


def test_a_new_capture_owns_the_device_again():
    src = SRC.read_text(encoding="utf-8")
    assert "stream = captured; streamKey = key; _micDevice.reset();" in src

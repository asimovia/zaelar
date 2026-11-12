"""A voice start that fails is retried by its bounded retry, never by the ⏻ effect (node 3.199).

`main.js` brings the voice back when ⏻ comes ON from outside the tab with an effect that called `ensureVoice()`,
which READS `started()`/`starting()` — so the effect subscribed to the very state a start writes. A start refused
with 503 `voice_starting` (the worker not registered) drops both flags, the effect re-ran, and started again: a desktop
opened and closed a voice session every ~150 ms for hours, past `voice-arrival.js`'s 40 × 3 s bound, and every
ask also restarted the engine's dead-voice clock (node 3.198). The effect now runs `ensureVoice` untracked.

The `.mjs` beside this file runs main.js's OWN `ensureVoice` and effect over the engine's reactive core.
"""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_a_failed_start_is_not_restarted_by_the_power_effect():
    r = subprocess.run(["node", str(Path(__file__).with_suffix(".mjs"))], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")

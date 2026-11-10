"""A refused microphone gives a chat-only session, and never a loop (node 4.437).

main.js re-enters `session.start()` from a reactive effect whenever `starting` drops; a refusal (denied, no device,
a policy) fails instantly, so without a gate the tab asked the browser again and again, endlessly. And with no
session at all, `/api/chat` answers `no_session` and a typed line is retried forever: a refusal now brings the session
up CHAT-ONLY on a silent stream. The `.mjs` beside this file drives `services/mic-denial.js` (the gate, `isRefusal`,
`silentStream`); the checks below hold both transports to it.
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


@pytest.mark.parametrize("path", ["frontend/app/services/session-lk.js", "frontend/app/services/session.js"])
def test_a_refused_capture_falls_back_to_a_silent_stream_instead_of_throwing(path):
    src = Path(path).read_text(encoding="utf-8")
    start = src[src.index("export async function start()"):]
    m = re.search(r"try \{[^\n]*getUserMedia\(\{ audio: ad \}\);[^\n]*\}[^\n]*\s*catch \(err\) \{([\s\S]*?)\n    \}", start)
    assert m, f"{path}: the capture is not caught where it is asked"
    fallback = m.group(1)
    assert "if (!micDenial.isRefusal(err)) throw err;" in fallback, f"{path}: only a refusal falls back"
    assert re.search(r"try \{ (captured|stream) = micDenial\.silentStream\(\); \} catch \(_\) \{ throw err; \}", fallback), (
        f"{path}: a refusal must come up on the silent stream (and stand, gated, when there is none)")
    assert "setMicBlocked" in fallback and "chat-only session" in fallback, f"{path}: the mic says why it is off"


def test_a_silent_stream_is_never_taken_back_as_the_mic():
    src = Path("frontend/app/services/session-lk.js").read_text(encoding="utf-8")
    park = src[src.index("function _parkMic("):src.index("function _takeWarm(")]
    assert re.search(r"if \(s && s\.__silent\) \{[^\n]*tr\.stop\(\)[^\n]*return; \}", park), (
        "a parked silent stream would be reused by the next start, which would never ask for the mic again")
    assert "if (!captured.__silent) health.micCaptureResult(null);" in src, "a silent stream is not a healthy mic"

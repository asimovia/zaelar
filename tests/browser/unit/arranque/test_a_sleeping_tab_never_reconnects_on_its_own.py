"""A sleeping tab never reconnects on its own (V2-872).

A hosted engine stops when nobody uses it, and any request starts it again. An open tab whose `EventSource`
reconnected by itself after every stop booted one engine 35 times in 26 h with nobody there. The client's rule
lives in ONE pure function (`frontend/app/services/presence.js::reconnectDecision`), driven by the `.mjs` beside
this file; the checks below hold the wiring that makes it the only way back: the stream's error closes it, and
every poller and voice retry asks `asleep()` before it reaches the server.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_sleeping_tab_never_reconnects_on_its_own.mjs")
FRONT = Path("frontend/app")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_reconnect_decision_and_the_dormant_state():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_the_stream_error_closes_it_and_hands_the_decision_over():
    src = (FRONT / "services/sse.js").read_text(encoding="utf-8")
    assert "es.onerror = () => { closeSSE(); onStreamError(); };" in src, (
        "without an onerror that closes it, the browser reconnects the EventSource on its own")
    assert "presenceEvent(d);" in src[src.index("export function routeEvent"):], "engine.sleep must reach the tab"


@pytest.mark.parametrize("rel, guard", [
    ("services/status.js", "if (!asleep()) refreshStatus();"),
    ("services/daemon.js", "!asleep()"),
    ("update/watch.js", "!asleep()"),
    ("services/session-lk.js", "if (started && !asleep()) start();"),
    ("services/session-lk.js", "_hb = setInterval(() => { if (asleep()) return;"),
    ("services/debugbus.js", "if (asleep()) setTimeout(retry, 5000); else startDebugBus();"),
])
def test_a_sleeping_tab_sends_nothing(rel, guard):
    """A poll is a request, and a request starts a stopped engine just like a stream does."""
    assert guard in (FRONT / rel).read_text(encoding="utf-8"), f"{rel} reaches the server while the tab sleeps"


def test_the_only_event_streams_are_the_app_one_and_the_debug_panel():
    """A new `EventSource` is a new door back into a stopped engine: it goes through presence.js or is named here."""
    hits = sorted(str(p.relative_to(FRONT)) for p in FRONT.rglob("*.js")
                  if re.search(r"new EventSource\(", p.read_text(encoding="utf-8", errors="ignore")))
    assert hits == ["services/debugbus.js", "services/sse.js"], hits

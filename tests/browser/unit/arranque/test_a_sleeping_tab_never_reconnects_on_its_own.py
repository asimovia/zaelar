"""A sleeping tab never reconnects on its own (V2-872).

An engine with an idle stop ends when nobody uses it, and any request can start it again. An open tab whose
`EventSource` reconnects by itself after every stop starts the engine again and again with nobody there. The client's rule
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


def test_an_open_the_tab_decided_says_it_is_a_person():
    """The edge of a hosted deployment starts a stopped engine for a navigation or for `wake=1`, never for a stream the
    browser retries on its own. The mark is set only on the opens presence.js decides; the boot open has none."""
    src = (FRONT / "services/sse.js").read_text(encoding="utf-8")
    assert '(wake ? "&wake=1" : "")' in src, "a presence-driven open must carry wake=1"
    assert "open: (o) => openSSE(desktop, o)" in src, "presence.js's open options must reach the stream"
    api = Path("server/voice_api.py").read_text(encoding="utf-8")
    assert 'wake: str = ""' in api and 'if wake == "1":' in api and "_screens.touched(dev)" in api, (
        "a gesture that reopened the stream is input: the idle stop's unattended-wake grace ends with it")


def test_the_only_event_streams_are_the_app_one_and_the_debug_panel():
    """A new `EventSource` is a new door back into a stopped engine: it goes through presence.js or is named here."""
    hits = sorted(str(p.relative_to(FRONT)) for p in FRONT.rglob("*.js")
                  if re.search(r"new EventSource\(", p.read_text(encoding="utf-8", errors="ignore")))
    assert hits == ["services/debugbus.js", "services/sse.js"], hits

"""An `error` event with no exception is a browser notice, never reported as a «JS error» (V2-873).

A demo pass (2026-11-10) reported `ResizeObserver loop completed with undelivered notifications` as a JS error: the
browser raises it itself when a layout settles over two frames, and nothing is lost. The label is read off the event's
shape — an exception a script threw carries its Error object — never off its words. The `.mjs` beside this file drives
`services/api.js` (`errorLabel`); the check below holds the page's reporter to it.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_browser_notice_is_not_a_js_error.mjs")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_label_is_read_off_the_events_shape():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_the_pages_reporter_uses_it():
    src = Path("frontend/app/main.js").read_text(encoding="utf-8")
    handler = src[src.index('window.addEventListener("error"'):]
    assert handler.index("api.clientLog(api.errorLabel(e)") < handler.index("unhandledrejection")

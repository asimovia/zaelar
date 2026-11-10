"""A failed diagnostic report never reports itself (the page's error reporter used to loop on its own failure).

`api.clientLog` is called by the page's global `error` / `unhandledrejection` handlers. Its POST returned a rejected
promise nobody caught, so one failed report raised another `unhandledrejection` → another report → … an endless loop
that took every connection of the tab. The `.mjs` beside this file drives `api.js` with a failing `fetch`.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_failed_client_log_never_reports_itself.mjs")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_a_failed_report_is_swallowed_and_a_storm_is_capped():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")

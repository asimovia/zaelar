"""V2-875 — pytest face of the .mjs next to it: services/where.js + services/privacy.js."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_screen_tells_where_it_is.mjs")


def test_a_screen_tells_where_it_is_only_when_allowed() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required")
    r = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr

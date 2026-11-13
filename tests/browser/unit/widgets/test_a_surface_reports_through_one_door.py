"""Exposes the card-side state reporter's test to pytest (V2-884 1a; the why is in the .mjs).

Same wrapper pattern as tests/browser/unit/mobile/test_mobile_host_contract.py.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_surface_reports_through_one_door.mjs")


def test_a_surface_reports_through_one_door() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the state reporter test")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr

"""Exposes the commit-order rule of the chat wall to pytest/Test Observatory (see the .mjs for the measurement)."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_wall_is_in_the_order_things_were_committed.mjs")


def test_the_wall_is_in_the_order_things_were_committed() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the chat wall order contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr

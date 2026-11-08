"""Exposes the V2-862 rule that an errand's chat reference is one box that updates to pytest (see the .mjs)."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_an_errand_reference_is_one_box_that_updates.mjs")


def test_an_errand_reference_is_one_box_that_updates() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the chat wall reference contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr

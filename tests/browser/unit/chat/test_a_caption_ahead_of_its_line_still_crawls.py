"""Exposes «a caption ahead of its line still crawls» to pytest/Test Observatory.

The measurement and the reason each assertion exists are in the `.mjs`
beside this file — it drives the REAL store, so this is a runner, not a copy.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_caption_ahead_of_its_line_still_crawls.mjs")


def test_a_caption_ahead_of_its_line_still_crawls() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the early-caption contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr

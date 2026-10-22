"""Exposes the two-lines-one-turn contract to pytest (demo 2026-10-22). The reason is in the .mjs, which MOUNTS the
real store and replays the order of events that drew one reply in two bubbles."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_two_lines_of_one_turn_are_two_bubbles.mjs")


def test_two_lines_of_one_turn_are_two_bubbles() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to mount the store")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr

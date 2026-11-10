"""V2-870 P2 — pytest face of the .mjs next to it: services/device.js, the screen's location/motion/compass door."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_screen_is_a_sensor.mjs")


def test_the_screen_is_a_sensor_through_one_door_and_a_refusal_is_a_value() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required")
    r = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr

"""Node 4.271 (V2-796) — pytest face of the .mjs next to it: the install → notifications banner and the service
worker's push half. Same wrapper pattern as test_mobile_host_contract.py."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_phone_is_offered_install_then_notifications.mjs")


def test_the_phone_is_offered_the_app_then_notifications_and_never_nagged() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required")
    r = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr

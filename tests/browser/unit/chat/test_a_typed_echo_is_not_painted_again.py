"""INI-042 #36 — the engine's echo of a typed line is not painted again when it lands after the next line."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_typed_echo_is_not_painted_again.mjs")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_a_typed_echo_is_not_painted_again():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")

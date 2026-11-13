"""V2-901 — the cycling card's half, run in Node (the .mjs next to this file): the phone app claims a voice-started
ride and reads only the sensors it has, a desktop only reflects it unless he tapped Start there, a saved ride stops
the sensors, a view the brain pushes opens that ride's page, the card reports what it shows, and the ghost's
arithmetic puts each earlier attempt ahead or behind him.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_the_card_records_on_one_screen_and_follows_a_pushed_view():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required")
    script = Path(__file__).with_name("test_the_card_records_on_one_screen.mjs")
    r = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr

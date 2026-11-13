"""V2-899 — the nutrition card's own half, run in Node against a DOM stub (the .mjs next to this file).

After every paint the card reports `screen`, `day` (empty for the logical today), `meal` and `pending` with the
revision it applied; a voice `show` moves it once and the same order pushed again never undoes his tap; a photo is
uploaded as a FILE through `ctx.upload` and `log_meal` names it (no bytes travel in an action); every screen paints;
a model's answer is built as text, never as markup.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_the_card_says_what_it_shows_and_uploads_a_photo_as_a_file():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required")
    script = Path(__file__).with_suffix(".mjs")
    r = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip().endswith("ok")

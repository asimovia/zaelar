"""The boot loader grows continuously on its own clock and finishes fast on ready (node 4.492).

The operator (2026-11-12): the mesh around the turning ring must compose itself little by little — one neuron at the
top, another at the bottom, one on the left, two at the top… — at a steady cadence, never in two or three batches
tied to the boot phases; on ready the rest develops very fast and the loader hands over. The schedule lives in two
pure functions of `frontend/app/components/boot-anim.js` (`growStep`, `growthOrder`), driven frame by frame by the
`.mjs` beside this file.

Disarm (`test_a_growth_tied_to_the_phases_alone_is_caught`): boot-anim.js copied with the clock term of `growStep`
cut — the growth then moves only on a phase, as it did — and the same script must fail.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_loader_grows_continuously_and_finishes_fast.mjs")
ANIM = Path(__file__).resolve().parents[4] / "frontend/app/components/boot-anim.js"
CLOCK_TERM = "ramp * (GROW.CAP - p) / GROW.TAU"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["node", str(SCRIPT), *args], capture_output=True, text=True, timeout=60)


def test_the_growth_is_continuous_alternates_fronts_and_finishes_fast():
    r = _run()
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_a_growth_tied_to_the_phases_alone_is_caught(tmp_path):
    src = ANIM.read_text(encoding="utf-8")
    assert CLOCK_TERM in src, "the clock term this disarm cuts is gone — update the disarm"
    disarmed = src.replace(CLOCK_TERM, "0")
    assert CLOCK_TERM not in disarmed
    copy = tmp_path / "boot-anim.mjs"
    copy.write_text(disarmed, encoding="utf-8")
    r = _run(str(copy))
    assert r.returncode != 0, "with the clock cut the schedule still passed: the test proves nothing"
    assert "still grows every second" in (r.stderr or "") or "froze" in (r.stderr or ""), r.stderr

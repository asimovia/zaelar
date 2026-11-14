"""A screen's host says what it shows as ONE document (V2-907 T6, node 4.541).

The behaviour is driven in the `.mjs` beside this file over the REAL `frontend/app/widgets/screen-reporter.js`; the
cases here are the run, the engine's door taking every body it sent (`widgets/screen_doc.write`), and the disarm: an
order's answer that waits for the coalescing window turns the `.mjs` red.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_reporter_sends_one_document.mjs")
ROOT = Path(__file__).resolve().parents[4]
REPORTER = ROOT / "frontend" / "app" / "widgets" / "screen-reporter.js"
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _run(module: Path | None = None, bodies: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if module:
        env["SCREEN_REPORTER"] = str(module)
    if bodies:
        env["SCREEN_BODIES"] = str(bodies)
    return subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60, env=env)


@needs_node
def test_the_reporter_sends_one_document(tmp_path):
    out = tmp_path / "bodies.json"
    r = _run(bodies=out)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    from widgets import screen_doc
    screen_doc._reset_for_tests()
    try:
        for b in json.loads(out.read_text()):
            stored, why = screen_doc.write(b["dev"], b["mount"], b["n"], b["doc"], by=b["by"])
            assert stored or why in ("n_back", "replaced"), (why, b)   # the test's own crossed POSTs, never a shape
    finally:
        screen_doc._reset_for_tests()


@needs_node
def test_disarm_an_answer_that_waits_for_the_window_turns_it_red(tmp_path):
    src = REPORTER.read_text(encoding="utf-8")
    old = "acks.push({ seq, ok: WHY[w], why: w });\n      send(false);"
    assert src.count(old) == 1, "disarm did not land"
    mutated = tmp_path / "screen-reporter.js"
    mutated.write_text(src.replace(old, "acks.push({ seq, ok: WHY[w], why: w });\n      schedule();"), encoding="utf-8")
    r = _run(mutated)
    assert r.returncode != 0 and "FAIL an order's answer is flushed at once" in r.stdout, r.stdout

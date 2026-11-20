"""The old path writes the chat wall as one writer among others (node 4.613, INI-042 #49 — the wall plan's commit 3/5;
the review's F3-2, F3-3 and minors).

  · the behaviour, on the real old-path writer and the real model (`.mjs`): a typed line and its acknowledgement are
    one line by its `cid`; his line in course is one line; a notice is one line per notice id; the engine's 4000 cut;
    the reset; the old wall's history moved over once at the old cap;
  · F3-3 — the old path's hands are `legacy:<source>` and nothing else, but for the ONE acknowledgement of a typed line
    by the keyboard that wrote it: it never writes as the manager (`ear:`, `mouth`) nor as a keyboard otherwise;
  · F3-1 — the router leaves every event a session of the manager marks (`conv`) before the old path could paint it.

Disarms seen red: the acknowledgement by `legacy:you` (two lines); a notice by a fresh id (painted twice); the old
writer naming `mouth`; the router's `conv` branch removed.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
SCRIPT = Path(__file__).with_name("test_the_old_path_is_one_writer_among_others.mjs")
LEGACY = ENGINE / "frontend/app/services/wall-legacy.js"
SSE = ENGINE / "frontend/app/services/sse.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_old_path_writes_one_line_where_one_was_said():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def _writers(src: str) -> list[str]:
    """Every writer name the old path's source writes with: the first argument of each `add(`/`act(` call."""
    out = []
    for door in ("add(", "act("):
        at = 0
        while (at := src.find(door, at)) >= 0:
            at += len(door)
            arg = src[at:at + 60].lstrip()
            if arg[:1] in "\"'`":
                out.append(arg[1:].split(arg[0], 1)[0])
    return out


def test_the_old_path_writes_by_its_own_names_only():
    src = LEGACY.read_text(encoding="utf-8")
    names = _writers(src)
    assert names and all(n.startswith("legacy:") for n in names if not n.startswith("keyboard:")), names
    keyboard = [n for n in names if n.startswith("keyboard:")]
    assert keyboard == ["keyboard:${clean(dev || me)}"], f"one acknowledgement by the keyboard, no other: {keyboard}"
    assert not [n for n in names if n == "mouth" or n.startswith("ear:")], "the old path never writes as the manager"


def test_the_router_leaves_what_the_manager_writes():
    src = SSE.read_text(encoding="utf-8")
    conv = src.index('field(d, "conv") && (d.kind === "interim"')
    for later in ('d.kind === "interim" && d.text && d.role === "user"', 'd.kind === "transcript" && d.text',
                  'd.kind === "notify"', 'd.kind === "brain" && /reply/'):
        assert src.index(later) > conv, f"the old path reaches {later!r} before the manager's mark is read"
    for kind in ("interim", "transcript", "notify"):
        assert f'd.kind === "{kind}"' in src[conv:conv + 220]

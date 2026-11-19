"""A phone back from the background runs the new screen (node 4.600).

Measured 2026-11-19 on the operator's phone: a release changed the phone's home, and his app — alive in the background
since the build before — came back to the foreground with the old home, because the update channel only showed
«new version — tap to update». The rule lives in `frontend/app/update/watch.js` (`reloadOnReturn`), driven by the
`.mjs` beside this file; the phone shell turns it on, the desktop keeps the bar. Disarm: the return no longer reloads.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
SCRIPT = Path(__file__).with_name("test_a_phone_back_from_the_background_runs_the_new_screen.mjs")
WATCH = ENGINE / "frontend" / "app" / "update" / "watch.js"
_RETURN = "if (_reloadOnReturn && stale()) applyUpdate();"


def _run(watch: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["node", str(SCRIPT), watch.as_uri()], capture_output=True, text=True, timeout=60, cwd=ENGINE)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_phone_reloads_onto_a_newer_frontend_and_the_desktop_keeps_the_bar():
    r = _run(WATCH)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_the_phone_shell_turns_it_on_and_the_desktop_does_not():
    phone = (ENGINE / "frontend/mobile/app/shell/mobile-surfaces.js").read_text(encoding="utf-8")
    desk = (ENGINE / "frontend/app/core/system-surfaces.js").read_text(encoding="utf-8")
    assert "UpdateSurface({ badge: false, reloadOnReturn: true })" in phone
    assert "reloadOnReturn" not in desk


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_disarm_a_return_that_does_not_reload_turns_it_red(tmp_path):
    src = WATCH.read_text(encoding="utf-8")
    assert src.count(_RETURN) == 1, "disarm did not land"
    copy = tmp_path / "frontend" / "app" / "update" / "watch.js"
    copy.parent.mkdir(parents=True)
    copy.write_text(src.replace(_RETURN, "void 0;"), encoding="utf-8")
    for dep in ("frontend/app/core/reactive.js", "frontend/app/services/presence.js"):
        d = tmp_path / dep
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_text((ENGINE / dep).read_text(encoding="utf-8"), encoding="utf-8")
    r = _run(copy)
    assert r.returncode != 0 and "THE BUG" in (r.stdout + r.stderr), r.stdout + r.stderr

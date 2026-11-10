"""One black veil over the whole screen when the engine sleeps or the voice moves (2026-11-10).

The engine's goodnight (`engine.sleep`) used to dim the orb and leave every panel and the chat wall looking usable
over an engine that was gone; the voice taken by another screen showed a different notice on each shell. Now ONE
shared component (`frontend/app/components/DormantVeil.js`) covers the whole screen, on both shells, with the gesture
that fixes each case: Reactivate (the stream reopens with `wake=1`, and the veil waits until it answers) or «use it
here». The state machine is driven by the `.mjs` beside this file; the checks below hold the wiring around it.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_one_black_veil_when_the_engine_sleeps_or_the_voice_moves.mjs")
VEIL = Path("frontend/app/components/DormantVeil.js")
SHARED_CSS = Path("frontend/app/core/shared-surfaces.css")
#: `.fw-wrap` (styles.css): the one layer above the veil — test_the_feedback_button_is_never_hidden holds it on top.
FEEDBACK_LAUNCHER = 101000


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_veil_state_and_the_presence_beat():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def _z(src: str, selector: str) -> int:
    m = re.search(re.escape(selector) + r"\{[^}]*?z-index:(\d+)", src)
    assert m, f"no z-index for {selector}"
    return int(m.group(1))


def test_the_veil_is_the_top_layer_on_every_screen():
    """«Covers the whole screen, the chat wall and any open panel»: nothing on either shell sits above it but the
    feedback button, which is never hidden."""
    veil = _z(SHARED_CSS.read_text(encoding="utf-8"), ".dz-veil")
    for p in [*Path("frontend/app").rglob("*.css"), *Path("frontend/app").rglob("*.js"),
              *Path("frontend/mobile").rglob("*.css"), *Path("frontend/mobile").rglob("*.js")]:
        for z in re.findall(r"z-index:\s*(\d+)", p.read_text(encoding="utf-8", errors="ignore")):
            if int(z) == FEEDBACK_LAUNCHER:      # the feedback button is never hidden, by anything
                continue
            if p != SHARED_CSS or int(z) != veil:
                assert int(z) < veil, f"{p} has a layer at z-index {z}, above the veil ({veil})"


def test_both_shells_mount_the_one_veil_and_the_old_notice_is_gone():
    desk = Path("frontend/app/core/system-surfaces.js").read_text(encoding="utf-8")
    phone = Path("frontend/mobile/app/shell/mobile-surfaces.js").read_text(encoding="utf-8")
    assert re.search(r'id: "dormant",\s*comp: DormantVeil,\s*target: "body"', desk)
    assert re.search(r'id: "dormant",\s*comp: DormantVeil,\s*target: "body".*shared: true', phone)
    assert not Path("frontend/mobile/app/shell/VoiceHeldNotice.js").exists(), "a second notice for the same state"


def test_reactivate_is_a_gesture_and_the_moved_face_brings_the_voice_here():
    src = VEIL.read_text(encoding="utf-8")
    assert 'import { reactivate } from "../services/presence.js?v=1"' in src
    assert 'session.claimVoice("veil")' in src
    assert "setPower" not in src and "power.js" not in src, "the veil never touches the agent's ⏻"


def test_the_engine_hears_a_connected_screen():
    sse = Path("frontend/app/services/sse.js").read_text(encoding="utf-8")
    assert "beat: screensPresent, dormant: store.setDormant" in sse
    api = Path("frontend/app/services/api.js").read_text(encoding="utf-8")
    assert re.search(r'screensPresent = \(\) => \{[^}]*present: true', api)
    srv = Path("server/screens_api.py").read_text(encoding="utf-8")
    assert 'get("present") and visible is True' in srv and "screens.present(dev)" in srv


@pytest.mark.parametrize("lang", ["en", "es"])
def test_every_line_of_the_veil_is_in_the_ui_pack(lang):
    pack = json.loads(Path(f"i18n/genesis/{lang}/ui.json").read_text(encoding="utf-8"))
    used = set(re.findall(r't\("(dormant\.[a-z_]+)"\)', VEIL.read_text(encoding="utf-8")))
    assert len(used) >= 8, used
    missing = sorted(k for k in used if not pack.get(k))
    assert not missing, f"{lang}: {missing}"

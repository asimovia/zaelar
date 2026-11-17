"""The agent's face (V2-928): every face in the catalogue draws, Porcelain is the default, and the face is never a statue.

The catalogue is one shared rig + a parametric head with layers + 17 fixed classics, driven in node by `faces.mjs`
with a canvas stub. Pinned here:

  1. every face — classics and every generated variation — draws at rest, speaking and thinking, with no error;
  2. Porcelain is the first classic and the default face everyone starts with (`presence/state.js`);
  3. every face, category and knob label the Settings section shows has its string in BOTH preset bundles;
  4. the rig is ALIVE: a minute at rest moves the head and brows well beyond the slow drift, and speech with bursts
     of energy fires accents (`presence/life.js`).

Disarm: `test_disarm_without_life_the_face_is_a_statue` switches `life.apply` off in a copy of the folder and the
liveliness numbers fall to the drift alone — the red this file exists to show.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
PRESENCE = ENGINE / "frontend/app/presence"
SCRIPT = Path(__file__).with_name("faces.mjs")
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _run(folder: Path) -> dict:
    r = subprocess.run(["node", str(SCRIPT), str(folder)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def run():
    return _run(PRESENCE)


def _alive(d: dict) -> bool:
    s = d["spread"]
    return s["roll"] > 0.15 and s["brow"] > 0.35 and d["browPeaks"] >= 10


def test_every_face_draws_at_rest_speaking_and_thinking(run):
    assert run["nErrors"] == 0, run["errors"]
    assert run["nFaces"] >= 900 and len(run["styles"]) == 17
    assert run["drawn"] == 3 * (run["nFaces"] + len(run["styles"]))


def test_porcelain_is_the_first_classic_and_the_default(run):
    assert run["styles"][0] == "porcelain"
    state = (PRESENCE / "state.js").read_text(encoding="utf-8")
    assert 'export const DEFAULT_FACE = "c-porcelain";' in state


def test_every_label_the_section_shows_is_in_both_bundles(run):
    keys = {f"presence.face.{b}" for b in run["bases"] + run["styles"]} | {f"presence.cat.{c}" for c in run["cats"]}
    controls = (PRESENCE / "controls.js").read_text(encoding="utf-8")
    keys |= {f"presence.ctl.{p}" for p in re.findall(r'(?:S|Rg|Cl|Ck)\("([a-z]+\.[A-Za-z0-9]+)"', controls)}
    keys |= {f"presence.grp.{g}" for g in re.findall(r'^\s*\["([a-z]+)", \[', controls, re.M)}
    section = (PRESENCE / "PresenceSection.js").read_text(encoding="utf-8")
    keys |= set(re.findall(r't\("(presence\.[a-z_]+)"', section))
    for lang in ("en", "es"):
        ui = json.loads((ENGINE / f"i18n/genesis/{lang}/ui.json").read_text(encoding="utf-8"))
        missing = sorted(k for k in keys if k not in ui)
        assert not missing, (lang, missing[:10])


def test_the_face_is_alive_at_rest_and_accents_its_speech(run):
    assert _alive(run), (run["spread"], run["browPeaks"])


def test_disarm_without_life_the_face_is_a_statue(tmp_path):
    copy = tmp_path / "presence"
    shutil.copytree(PRESENCE, copy)
    rig = copy / "rig.js"
    src = rig.read_text(encoding="utf-8")
    assert src.count("    life.apply(r, {") == 1, "the rig's call to life.js moved — follow it"
    rig.write_text(src.replace("    life.apply(r, {", "    if (0) life.apply(r, {"), encoding="utf-8")
    d = _run(copy)
    assert not _alive(d), ("with life.js disarmed the rig still read as alive — the test proves nothing", d["spread"])

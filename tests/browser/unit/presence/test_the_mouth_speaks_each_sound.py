"""The face speaks each sound with its own mouth (V2-928, node 4.575) — ES and EN alike.

The operator, 2026-11-18: «that the lips have more resolution, that it looks like a person really speaking». The voice
model already tells 15 sounds apart (Oculus visemes, language-free); the rig folded them into four numbers, so every sound
was a slightly different slit. `presence/mouth.js` gives each sound a recipe over nine channels and the human-like looks
(Porcelain, the parametric «filled» / «lips» / «o» mouths) show teeth and a tongue inside the opening.

What is pinned (mouth.mjs, node, a held viseme through the real rig and geometry):
  1. «p b m» seal the lips (no opening); «f v» leave a thin slit with the lower lip under the upper teeth; «t d n l» lift
     the tongue tip and «th» puts it between the teeth; «o u» round and narrow the lips; «i e s» stretch them wider than
     rest; «a» opens the most;
  2. resolution: every pair of the 14 sounds draws a measurably different mouth;
  3. the human-like look shows teeth for every open sound and none when sealed or at rest; an abstract look (LED) never;
  4. at rest the mouth is exactly the one it always was (the old formula, to the last digit).

Disarms: «f» without its bite has no teeth over the lip; the inside switched off shows no teeth anywhere.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
PRESENCE = ENGINE / "frontend/app/presence"
SCRIPT = Path(__file__).with_name("mouth.mjs")
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _run(folder: Path) -> dict:
    r = subprocess.run(["node", str(SCRIPT), str(folder)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    return json.loads(r.stdout.strip().splitlines()[-1])


def _disarmed(tmp_path: Path, old: str, new: str) -> dict:
    copy = tmp_path / "presence"
    shutil.copytree(PRESENCE, copy)
    src = (copy / "mouth.js").read_text(encoding="utf-8")
    assert old in src, f"the disarm did not find its target: {old!r}"
    (copy / "mouth.js").write_text(src.replace(old, new), encoding="utf-8")
    return _run(copy)


@pytest.fixture(scope="module")
def run():
    return _run(PRESENCE)


def test_each_sound_has_its_own_mouth(run):
    o = run["out"]
    assert o["PP"]["h"] < 0.003 and o["PP"]["press"] > 0.9, f"p b m seal the lips: {o['PP']}"
    assert 0.02 < o["FF"]["h"] < 0.05 and o["FF"]["bite"] > 0.9 and o["FF"]["teeth"], f"f v: a slit under the teeth: {o['FF']}"
    assert o["TH"]["tip"] > 0.9 and o["DD"]["tip"] > 0.5 and o["nn"]["tip"] > 0.5, "t d n l lift the tongue tip, th pushes it out"
    for v in ("O", "U"):
        assert o[v]["round"] > 0.7 and o[v]["mw"] < 0.7 * o["rest"]["mw"], f"{v} rounds and narrows the lips: {o[v]}"
    for v in ("I", "E", "SS"):
        assert o[v]["mw"] > 1.15 * o["rest"]["mw"], f"{v} stretches the lips: {o[v]}"
    assert o["aa"]["h"] == max(x["h"] for x in o.values()), "a opens the most"


def test_every_pair_of_sounds_is_told_apart(run):
    assert run["minGap"] > 0.08, f"two sounds draw (almost) the same mouth: {run['closest']} at {run['minGap']}"


def test_the_human_look_shows_teeth_while_it_speaks_and_the_abstract_ones_never(run):
    o = run["out"]
    assert all(o[v]["teeth"] for v in o if v not in ("rest", "PP")), {v: o[v]["teeth"] for v in o}
    assert not o["rest"]["teeth"] and not o["PP"]["teeth"], "teeth through closed lips"
    assert not any(o[v]["ledTeeth"] for v in o), "an abstract look grew teeth"


def test_at_rest_the_mouth_is_the_one_it_always_was(run):
    assert run["restSame"], "the resting mouth moved: every face's still look would change"


def test_disarm_f_without_its_bite_has_no_teeth_over_the_lip(tmp_path):
    d = _disarmed(tmp_path, "FF: { open: 0.22, bite: 1,", "FF: { open: 0.22, bite: 0,")
    assert not (d["out"]["FF"]["bite"] > 0.9 and 0.02 < d["out"]["FF"]["h"] < 0.05)


def test_disarm_without_the_inside_no_look_shows_teeth(tmp_path):
    d = _disarmed(tmp_path, 'new Set(["porcelain"])', "new Set([])")
    assert not any(v["teeth"] for v in d["out"].values())

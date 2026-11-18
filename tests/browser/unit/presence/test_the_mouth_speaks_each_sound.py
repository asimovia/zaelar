"""A richer speaking mouth, PARKED (V2-928, node 4.575) — built and kept, not wired.

The operator, 2026-11-18, asked for lips with «more resolution»; the same day, after seeing it, he preferred the simpler
mouth (and its lag behind the voice is less visible). `presence/mouth.js` keeps the richer one — a recipe per sound over
nine channels, teeth and a tongue inside the human-like looks — unimported, with its wiring steps in its header.

What is pinned: nothing in the live face imports it (his choice holds), and, driven directly (mouth.mjs, node):
  1. «p b m» seal the lips (no opening); «f v» leave a thin slit with the lower lip under the upper teeth; «t d n l» lift
     the tongue tip and «th» puts it between the teeth; «o u» round and narrow the lips; «i e s» stretch them wider than
     rest; «a» opens the most;
  2. resolution: every pair of the 14 sounds draws a measurably different mouth;
  3. the inside shows teeth for every open sound and none when sealed or at rest;
  4. at rest the mouth is exactly the one the live face draws (the old formula, to the last digit).

Disarm: «f» without its bite has no teeth over the lip.
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


def test_the_inside_shows_teeth_only_while_open(run):
    o = run["out"]
    assert all(o[v]["teeth"] for v in o if v not in ("rest", "PP")), {v: o[v]["teeth"] for v in o}
    assert not o["rest"]["teeth"] and not o["PP"]["teeth"], "teeth through closed lips"


def test_the_live_face_does_not_wire_it():
    for f in ("rig.js", "face.js", "classics.js", "parts-face.js", "creator.js"):
        assert "mouth.js" not in (PRESENCE / f).read_text(encoding="utf-8").replace("PARKED in mouth.js", ""), \
            f"{f} wires the parked mouth — the operator chose the simpler one (2026-11-18)"


def test_at_rest_it_is_the_live_mouth(run):
    assert run["restSame"], "at rest the parked mouth must be the live one exactly"


def test_disarm_f_without_its_bite_has_no_teeth_over_the_lip(tmp_path):
    d = _disarmed(tmp_path, "FF: { open: 0.22, bite: 1,", "FF: { open: 0.22, bite: 0,")
    assert not (d["out"]["FF"]["bite"] > 0.9 and 0.02 < d["out"]["FF"]["h"] < 0.05)

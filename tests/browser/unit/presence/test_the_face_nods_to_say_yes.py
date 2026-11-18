"""The face nods to say YES, not all the time (V2-928, node 4.576).

The operator, 2026-11-18: «the face moves up and down a lot, as if it were saying yes, but very exaggerated… it could
move the face while it says yes or no, but only when we ask a question that needs that answer».

What is pinned (nod.mjs, node):
  1. the head's vertical travel is calm — under 0.08 rad/s while the agent speaks (it was 0.17: a bob on every syllable,
     accents that nodded, a whole nod on one accent in four) and under 0.015 rad/s while he talks (it was 0.029: more
     than half the backchannel moves were nods);
  2. a reply that OPENS with a bare yes or no (the word, then a pause) is a yes or a no — ES and EN, with the bundles'
     own words (`presence.says_yes` / `presence.says_no`, language data, not code); «no te preocupes», «si quieres»,
     «noviembre», «nobody», «surely» are neither;
  3. the layer plays a nod for a yes and a shake for a no from the SPOKEN caption segments (audio-synced), once each.

Disarm: the speech bob back at its old depth → the travel while speaking goes over the line.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
PRESENCE = ENGINE / "frontend/app/presence"
SCRIPT = Path(__file__).with_name("nod.mjs")
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _words() -> str:
    out = {}
    for lang in ("es", "en"):
        ui = json.loads((ENGINE / f"i18n/genesis/{lang}/ui.json").read_text(encoding="utf-8"))
        out[lang] = {"yes": ui["presence.says_yes"], "no": ui["presence.says_no"]}
    return json.dumps(out, ensure_ascii=False)


def _run(folder: Path) -> dict:
    r = subprocess.run(["node", str(SCRIPT), str(folder), _words()], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def run():
    return _run(PRESENCE)


def test_the_head_is_calm_while_it_speaks_and_while_he_talks(run):
    assert run["speakTravel"] < 0.08, f"the head bobs while the agent speaks: {run['speakTravel']:.3f} rad/s"
    assert run["hearTravel"] < 0.015, f"the head keeps nodding while he talks: {run['hearTravel']:.3f} rad/s"


def test_a_reply_that_opens_with_yes_or_no_is_one_and_nothing_else_is(run):
    es, en = run["said"]["es"], run["said"]["en"]
    assert [es[s] for s in ("Sí, claro que puedo.", "Sí.", "¡Claro! Ahora mismo.", "Por supuesto, dime.")] == ["yes"] * 4, es
    assert [es[s] for s in ("No, todavía no ha llegado.", "Qué va, no hay nada.")] == ["no"] * 2, es
    assert not any(es[s] for s in ("No te preocupes, ya está.", "Si quieres lo miro.", "Noviembre empieza el lunes.",
                                   "Claramente es tarde.")), es
    assert [en[s] for s in ("Yes, I can.", "Sure! Right away.", "Of course, tell me.")] == ["yes"] * 3, en
    assert [en[s] for s in ("No, it has not arrived.", "Nope.")] == ["no"] * 2, en
    assert not any(en[s] for s in ("Not now, later today.", "Yesterday it rained.", "Nobody called.", "Surely it will.")), en


def test_the_layer_nods_and_shakes_from_the_spoken_caption():
    src = (PRESENCE / "PresenceLayer.js").read_text(encoding="utf-8")
    assert "store.captionSeg()" in src and 'face.gesture(p === "yes" ? "nod" : "shake")' in src and "seg.id === judged" in src, \
        "the yes / no gesture must come from the audio-synced caption, once per segment"


def test_disarm_the_old_speech_bob_makes_the_head_bob_again(tmp_path):
    copy = tmp_path / "presence"
    shutil.copytree(PRESENCE, copy)
    src = (copy / "rig.js").read_text(encoding="utf-8")
    assert "s.energy * 0.012 * Math.sin(t * 7.3)" in src
    (copy / "rig.js").write_text(src.replace("s.energy * 0.012 * Math.sin(t * 7.3)", "s.energy * 0.04 * Math.sin(t * 7.3)"), encoding="utf-8")
    assert _run(copy)["speakTravel"] >= 0.08

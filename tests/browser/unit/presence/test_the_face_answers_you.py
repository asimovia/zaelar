"""«The face answers you» (V2-928 T12, node 4.574): the agent's body language, on the device.

The operator, 2026-11-17: the face gestures back at what he does in front of the camera — a wink gets a wink, a tongue a
tongue, a laugh a laugh — but it is NOT a mirror: another being, which sometimes lets a gesture go, tires of the same one,
and gives a yawn nothing at all. Zero model, API or token; no image leaves the device. `frontend/app/presence/humanity/`
is perception → temperament → expression, fed by the vendored MediaPipe Face Landmarker (52 expression scores) once it
has loaded behind the camera, with picojs keeping the gaze until then or when the device is too slow.

What is pinned:
  1. PERCEPTION (humanity.mjs, node, fake blendshape frames): a held smile, a laugh, a one-eyed wink (and its side), a
     tongue, a yawn, a nod, a shake, an arrival and a departure are events; a blink with both eyes, an eye held shut and
     a short flicker are not, and a smile hovering at the line for seconds is one smile; while he TALKS — heard by his mic or seen as the jaw's flutter, mic muted — no mouth event
     (smile, tongue, yawn) fires, and a laugh still does;
  2. TEMPERAMENT (seeded): the same seed gives the same answers; across seeds a wink is usually answered and sometimes
     let go, a yawn mostly gets nothing; two events inside the gap get one answer; the same answer never twice in a row
     within its cooldown; the same gesture over and over tires (a sigh, a glance, nothing); while the agent speaks no
     answer uses the mouth (laugh, giggle, tongue, yawn); an answer waits a human beat (250–750 ms);
  3. EXPRESSION: a wink back mirrors his eye three times in four; a hello is a brow flash then a smile; the rig plays the
     new gestures (tongue, yawn, the left wink), and the tongue is drawn on top of EVERY look, classics and parametric;
  4. the whole chain on a fake face: a tongue held in silence is answered after its beat; the same tongue while he
     talks is not even perceived;
  5. the SEAM to the conversation is OFF: one summary per 20–60 s stretch of play, offered to nothing unless its
     switch is on;
  6. LOADING: with the camera switch off neither humanity/ nor the vendored MediaPipe is requested; on, they load
     behind the camera, the runtime is inflated and hash-checked, and the landmarker runs (headless: on the CPU when
     the GPU is refused); a landmarker that cannot load leaves the camera on the light detector, still following;
  7. the vendored files match their pins, and none of them carries a telemetry endpoint.

Disarms: perception without the talking gate fires a smile and a tongue while he talks; a temperament without «let it
go» answers every yawn; without the gap two laughs half a second apart both get answers.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.browser.unit.mobile.phone_page import open_phone
from tests.browser.unit.presence.test_the_face_looks_at_you import DESK, DESK_OFF, STATE

ENGINE = Path(__file__).resolve().parents[4]
PRESENCE = ENGINE / "frontend/app/presence"
VENDOR = ENGINE / "frontend/vendor/mediapipe"
SCRIPT = Path(__file__).with_name("humanity.mjs")
node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _run(folder: Path) -> dict:
    r = subprocess.run(["node", str(SCRIPT), str(folder)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    return json.loads(r.stdout.strip().splitlines()[-1])


def _disarmed(tmp_path: Path, file: str, old: str, new: str) -> dict:
    copy = tmp_path / "presence"
    shutil.copytree(PRESENCE, copy)
    src = (copy / file).read_text(encoding="utf-8")
    assert old in src, f"the disarm did not find its target in {file}: {old!r}"
    (copy / file).write_text(src.replace(old, new), encoding="utf-8")
    return _run(copy)


@pytest.fixture(scope="module")
def run():
    return _run(PRESENCE)


def _talk_gate_holds(p: dict) -> bool:
    return not p["smileHearing"] and not p["smileTalkingMuted"] and not p["tongueHearing"] and not p["talkingNoYawn"]


@node
def test_what_he_does_is_perceived_and_talking_is_not_a_face(run):
    p = run["perceive"]
    assert p["smile"] == ["smile"] and p["laughHearing"] == ["laugh"], f"a held smile / a laugh: {p}"
    assert p["smileHover"] == ["smile"], f"a smile held at the line for 6 s is ONE smile, not one every few seconds: {p}"
    assert p["winkLeft"] == ["wink:left"], f"a one-eyed wink, with its side: {p}"
    assert p["blinkBoth"] == [] and p["eyeShutLong"] == [], f"a blink or an eye held shut is not a wink: {p}"
    assert p["tongue"] == ["tongue"] and p["yawn"] == ["yawn"], f"a tongue out / a yawn: {p}"
    assert p["nod"] and set(p["nod"]) == {"nod"} and p["shake"] and set(p["shake"]) == {"shake"}, f"head nod / shake: {p}"
    assert p["presence"] == ["arrive", "leave"], f"someone arrives, then leaves: {p}"
    assert _talk_gate_holds(p), f"his talking mouth fired a face (heard, or seen with the mic muted): {p}"


@node
def test_it_is_another_being_not_a_mirror(run):
    t = run["temper"]
    assert t["sameSeedSame"], "the same seed must give the same answers (deterministic in a test)"
    w = t["winkAcross"]
    assert w.get("wink", 0) > 0.4 * 300 and 0.08 * 300 < w.get("nothing", 0) < 0.4 * 300 and len(w) >= 3, \
        f"a wink is mostly winked back, sometimes let go, sometimes answered otherwise: {w}"
    y = t["yawnAcross"]
    assert y.get("nothing", 0) > 0.6 * 300, f"a yawn mostly gets nothing: {y}"
    assert t["cooldown"] == 0, f"two laughs half a second apart both got an answer (no gap): {t}"
    assert t["sameTwice"] == 0, f"the same answer twice in a row inside its cooldown: {t}"
    assert "smile" not in t["tired"] and set(t["tired"]) <= {"sigh", "look", "nothing"}, f"the same gesture over and over must tire: {t}"
    assert not set(t["speakingMouth"]) & {"laugh", "giggle", "tongue", "yawn"}, f"while it speaks its mouth is the voice's: {t}"
    assert 250 <= t["delays"][0] and t["delays"][1] <= 750, f"an answer waits a human beat: {t}"
    assert "hand" in t["everyEvent"], "the declared hand event has its answers ready for a future detector"


@node
def test_the_face_plays_its_answers_and_any_look_sticks_its_tongue_out(run):
    assert 0.65 * 200 < run["mirror"] < 0.85 * 200, f"a wink back mirrors his eye three times in four: {run['mirror']}"
    assert run["hello"] == ["brows", "smile"], run["hello"]
    r = run["rig"]
    assert r["tongue"] > 0.9 and r["yawnOpen"] > 0.7 and r["winkL"]["L"] > 0.9 and r["winkL"]["R"] < 0.1, r
    td = run["tongueDrawn"]
    assert td["out"] == td["outOf"] and td["outOf"] > 20 and not td["errors"], f"the tongue must be drawn on every look: {td}"
    assert td["atRest"] == 0, f"a tongue drawn while it is in: {td}"


@node
def test_the_whole_chain_answers_a_tongue_in_silence_and_not_a_talking_mouth(run):
    s, h = run["whole"]["silent"], run["whole"]["hearing"]
    assert "tongue>tongue" in s["log"] and "tongue" in s["gestures"], f"a tongue in silence is answered: {s}"
    assert not [x for x in h["log"] if x.startswith("tongue")], f"his mouth while he talks is not a face: {h}"


@node
def test_the_seam_to_the_conversation_offers_one_summary_per_stretch(run):
    s = run["seam"]
    assert s["offers"] == 1 and 20 <= s["seconds"] <= 60 and "smiling" in s["line"], f"one summary per 20–60 s stretch: {s}"
    src = (PRESENCE / "humanity" / "index.js").read_text(encoding="utf-8")
    assert "if (offer && talkOn()) offer(s)" in src and "d.talk === true" in src, \
        "the seam must be off unless its switch is set by hand"
    look = (PRESENCE / "LookAtMe.js").read_text(encoding="utf-8")
    assert "createHumanity(face, { speech })" in look, "the live face wires no far end to the seam (no tokens)"


@node
def test_disarm_perception_without_the_talking_gate_reads_his_talking_as_faces(tmp_path):
    d = _disarmed(tmp_path, "humanity/perceive.js", "const mouthFree = t >= quietUntil;", "const mouthFree = true;")
    assert not _talk_gate_holds(d["perceive"])


@node
def test_disarm_a_temperament_that_never_lets_go_answers_every_yawn(tmp_path):
    d = _disarmed(tmp_path, "humanity/temperament.js", "if (w.null) w.null *= 1.6 - engagement;", "w.null = 0;")
    assert d["temper"]["yawnAcross"].get("nothing", 0) == 0


@node
def test_disarm_without_the_gap_two_laughs_both_get_answers(tmp_path):
    d = _disarmed(tmp_path, "humanity/temperament.js", "if (t - lastAnswerAt < k.gapMs) return null;", "")
    assert d["temper"]["cooldown"] > 0


# ── loading: nothing with the switch off; the real landmarker with it on ─────────────────────────────────────────────
def _heavy(urls: list[str]) -> list[str]:
    return [u for u in urls if "/presence/humanity/" in u or "/vendor/mediapipe/" in u]


def test_with_the_camera_off_nothing_of_it_loads():
    with open_phone(DESK_OFF, width=1280, height=800) as pg:
        urls: list[str] = []
        pg.on("request", lambda r: urls.append(r.url))
        pg.wait_for_timeout(1500)
        assert pg.evaluate("() => window.__presence.presenceOn()"), "the face should be on for this check"
        assert pg.evaluate(STATE)["gum"] == 0
        assert not _heavy(urls), f"the camera is off, yet its humanity loaded: {_heavy(urls)}"


def test_with_the_camera_on_the_landmarker_loads_verified_and_runs():
    with open_phone(DESK, width=1280, height=800) as pg:
        urls: list[str] = []
        pg.on("request", lambda r: urls.append(r.url))
        pg.wait_for_function("() => window.__zaelarLook && window.__zaelarLook.stats() && window.__zaelarLook.stats().mode === 'mesh'",
                             timeout=45000)
        pg.wait_for_timeout(1200)
        stats = pg.evaluate("() => window.__zaelarLook.stats()")
        assert stats["delegate"] in ("GPU", "CPU") and stats["meshFps"] >= 5 and stats["fps"] > 0, stats
        loaded = pg.evaluate("() => performance.getEntriesByType('resource').map(e => e.name)") + urls
        names = {u.rsplit("/", 1)[-1].split("?")[0] for u in _heavy(loaded)}
        assert {"vision_bundle.mjs", "vision_wasm_internal.wasm.gz", "face_landmarker.task"} <= names, names
        host = pg.url.split("/")[2]
        assert not [u for u in loaded if not u.startswith(("blob:", "data:")) and u.split("/")[2] != host], "a request left the device"
        assert pg.evaluate(STATE)["live"], "the camera stopped once the landmarker ran"
        assert pg.evaluate("() => window.__zaelarLook.humanity() !== null"), "the face has no humanity while the camera runs"


def test_a_landmarker_that_cannot_load_leaves_the_light_detector_following():
    with open_phone(DESK, width=1280, height=800, routes=[("**/vendor/mediapipe/**", lambda route: route.abort())]) as pg:
        pg.wait_for_timeout(2500)
        stats = pg.evaluate("() => window.__zaelarLook.stats()")
        assert stats["mode"] == "light" and stats["fps"] >= 8 and pg.evaluate(STATE)["live"], \
            f"without the landmarker the camera must keep following with picojs: {stats}"


# ── the vendored files: pinned, and silent ───────────────────────────────────────────────────────────────────────────
def test_the_vendored_landmarker_matches_its_pins_and_has_no_telemetry():
    src = (PRESENCE / "humanity" / "landmarker.js").read_text(encoding="utf-8")
    pins = dict(re.findall(r'(\w+): "([0-9a-f]{64})"', src))
    wasm = gzip.decompress((VENDOR / "vision_wasm_internal.wasm.gz").read_bytes())
    assert hashlib.sha256(wasm).hexdigest() == pins["wasm"], "the inflated runtime does not match its pin"
    assert hashlib.sha256((VENDOR / "face_landmarker.task").read_bytes()).hexdigest() == pins["model"], "the model moved"
    note = (VENDOR / "VENDORED_FROM.md").read_text(encoding="utf-8")
    for f in ("vision_bundle.mjs", "vision_wasm_internal.js", "vision_wasm_internal.wasm.gz", "face_landmarker.task"):
        assert hashlib.sha256((VENDOR / f).read_bytes()).hexdigest() in note, f"{f} is not the file VENDORED_FROM.md pins"
    for f in ("vision_bundle.mjs", "vision_wasm_internal.js"):
        body = (VENDOR / f).read_text(encoding="utf-8", errors="replace")
        assert not re.search(r"odml\.pa\.googleapis|/v1/log|sendBeacon|x-goog-api-key", body), f"{f} carries a telemetry endpoint"
    assert all((VENDOR / f).stat().st_size < 5 * 1024 * 1024 for f in (p.name for p in VENDOR.iterdir())), \
        "a vendored file is over the public repository's 5 MB limit"

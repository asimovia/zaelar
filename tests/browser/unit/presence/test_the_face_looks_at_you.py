"""«Look at me» (V2-928 T10, node 4.570): the agent's face turns toward the person in front of the camera — on the device.

The operator, 2026-11-17: the face follows the person as they move (left → it looks left, right → right), from the
camera on the computer and the phone, and from the AirPods' head motion inside the iPhone app; one switch each, OFF by
default, and NO model, API or token: an on-device detector (vendored picojs) and nothing ever leaves the page.

What is pinned:
  1. fake detections drive the head and the eyes: a person on their left turns the face to the left, on their right to
     the right; detector jitter inside the dead band does not move the target; a lost person hands the head back to the
     idle life; a second, farther face does not steal the gaze; the AirPods' turn maps the same way (look.mjs, node);
  2. the camera NEVER starts while its switch is off — with the face on and Settings ▸ Presence open;
  3. on, it starts once (video only, the front camera), a badge says so, and every off stops the tracks: the switch,
     the face hidden, the tab hidden, the badge; a refusal turns the switch back off and says why;
  4. while it runs nothing is sent anywhere: no request leaves the page's own host and none carries an image;
  5. the phone's Settings carries the camera switch at the bottom, and the AirPods switch ONLY when the native app's
     bridge (`window.ZaelarNative.headMotion`) says the device can read headphone motion — which then starts and stops
     it; Core Motion's yaw (> 0 = to the head's left) is flipped once, so a turn to his right turns the face right.

Disarms: the camera gate forced open (LookAtMe.js served with the switch read as `true`) starts the camera with the
switch off; the rig without `lookAt` keeps its head still; the camera frame read unmirrored turns the face the wrong way.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.browser.unit.mobile.phone_page import open_phone

ENGINE = Path(__file__).resolve().parents[4]
PRESENCE = ENGINE / "frontend/app/presence"
SCRIPT = Path(__file__).with_name("look.mjs")

# A fake front camera: a canvas stream, its gets and its track stops counted.
FAKE_CAMERA = """
  localStorage.removeItem('hb_presence'); localStorage.removeItem('hb_presence_look');
  window.__gum = []; window.__stopped = 0;
  navigator.mediaDevices.getUserMedia = async (c) => {
    window.__gum.push(JSON.parse(JSON.stringify(c)));
    if (window.__refuse) throw new DOMException('refused', 'NotAllowedError');
    const cv = document.createElement('canvas'); cv.width = 320; cv.height = 240;
    const g = cv.getContext('2d'); g.fillStyle = '#556'; g.fillRect(0, 0, 320, 240);
    const s = cv.captureStream(15);
    for (const tr of s.getTracks()) { const st = tr.stop.bind(tr); tr.stop = () => { window.__stopped++; st(); }; }
    return s;
  };
  window.__hidden = false;
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => window.__hidden });
  window.__look = await import('/frontend/app/presence/look-state.js?v=1');
  window.__presence = await import('/frontend/app/presence/state.js?v=1');
"""

DESK = FAKE_CAMERA + """
  const { PresenceLayer } = await import('/frontend/app/presence/PresenceLayer.js?v=1');
  document.body.append(PresenceLayer());
  const host = document.createElement('div'); host.id = 'pz-host'; document.body.append(host);
  const { mountPresence } = await import('/frontend/app/presence/PresenceSection.js?v=1');
  mountPresence(host);
"""

STATE = """() => ({ gum: window.__gum.length, stopped: window.__stopped, live: window.__look.cameraLive(),
  on: window.__look.lookCamera(), badge: !!document.querySelector('.hb-cam'),
  checked: document.querySelector('.pz-cam').checked, hint: document.querySelector('.pz-cam-hint').textContent })"""


def _run(folder: Path) -> dict:
    r = subprocess.run(["node", str(SCRIPT), str(folder)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    return json.loads(r.stdout.strip().splitlines()[-1])


def _follows(d: dict) -> bool:
    return (d["left"]["yaw"] < -0.15 and d["left"]["gazeX"] < -0.2 and d["right"]["yaw"] > 0.15
            and d["right"]["gazeX"] > 0.2 and d["left"]["w"] > 0.95)


node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


@node
def test_a_fake_detection_turns_the_head_toward_the_person():
    d = _run(PRESENCE)
    assert _follows(d), f"the face must look left at a person on their left and right on their right: {d}"
    assert d["jitterTarget"] == 0, f"a ±2 % detector jitter moved the target (the dead band is gone): {d}"
    assert d["gone"]["w"] < 0.01 and abs(d["gone"]["yaw"]) < 0.15, f"a lost person must hand the head back to idle: {d}"
    assert d["stay"]["yaw"] < -0.15, f"a farther face crossing behind stole the gaze: {d}"
    assert d["headRight"]["x"] > 0.3 and d["headRight"]["y"] > 0.1, f"AirPods: a turn to his right must turn the face right: {d}"
    assert 0 < d["seamX"] < 0.2, f"AirPods: a small turn across the sensor's ±π seam read as a whole turn: {d}"
    assert d["bridgeYaw"] == -0.3 and d["bridgePitch"] == 0.1, f"Core Motion's yaw (> 0 = left) must be flipped once: {d}"


def _disarmed(tmp_path: Path, file: str, old: str, new: str) -> dict:
    copy = tmp_path / "presence"
    shutil.copytree(PRESENCE, copy)
    src = (copy / file).read_text(encoding="utf-8")
    assert old in src, f"the disarm did not find its target in {file}: {old!r}"
    (copy / file).write_text(src.replace(old, new), encoding="utf-8")
    try:
        return _run(copy)
    finally:
        shutil.rmtree(copy, ignore_errors=True)


@node
def test_disarm_a_rig_without_look_at_keeps_its_head_still(tmp_path):
    assert not _follows(_disarmed(tmp_path, "rig.js", "    lookAt(r, dt);\n", "\n"))


@node
def test_disarm_an_unmirrored_frame_turns_the_face_the_wrong_way(tmp_path):
    assert not _follows(_disarmed(tmp_path, "look.js", "const rx = clamp((0.5 - d.x) * 2)", "const rx = clamp((d.x - 0.5) * 2)"))


@pytest.fixture
def desk():  # one page per test: a second Playwright cannot start while a module-wide one is open
    with open_phone(DESK, width=1280, height=800) as pg:
        pg.wait_for_timeout(600)
        yield pg


def test_the_camera_never_starts_with_the_switch_off(desk):
    desk.wait_for_timeout(1500)
    s = desk.evaluate(STATE)
    assert desk.evaluate("() => window.__presence.presenceOn()"), "the face should be on for this check"
    assert s["gum"] == 0 and not s["live"] and not s["badge"], f"the camera started with its switch off: {s}"
    assert not s["checked"] and "ninguna imagen sale" in s["hint"], f"the switch is off by default and says it stays here: {s}"


def test_on_it_starts_once_and_every_off_stops_it(desk):
    requests: list[tuple[str, str, str]] = []
    desk.on("request", lambda r: requests.append((r.url, r.method, r.post_data or "")))
    desk.click(".pz-cam")
    desk.wait_for_timeout(1200)
    s = desk.evaluate(STATE)
    assert s["gum"] == 1 and s["live"] and s["badge"], f"the switch did not start the camera with its badge: {s}"
    c = desk.evaluate("() => window.__gum[0]")
    assert c["audio"] is False and c["video"]["facingMode"] == "user", f"the camera asks for the front camera only: {c}"
    stats = desk.evaluate("() => window.__zaelarLook.stats()")
    assert stats["fps"] >= 8, f"the detector loop runs well under its rate: {stats}"

    # 4. nothing leaves: every request stays on the page's own host and none carries an image
    host = desk.url.split("/")[2]
    away = [u for u, _, _ in requests if u.split("/")[2] != host]
    assert not away, f"a request left the device while the camera ran: {away}"
    assert not [u for u, _, b in requests if "data:image" in b or len(b) > 4000], "a request carried an image"

    # the tab hidden → stopped; visible → started again
    desk.evaluate("() => { window.__hidden = true; document.dispatchEvent(new Event('visibilitychange')); }")
    desk.wait_for_timeout(300)
    s = desk.evaluate(STATE)
    assert s["stopped"] >= 1 and not s["live"] and not s["badge"], f"a hidden tab kept the camera: {s}"
    desk.evaluate("() => { window.__hidden = false; document.dispatchEvent(new Event('visibilitychange')); }")
    desk.wait_for_timeout(1000)
    assert desk.evaluate(STATE)["gum"] == 2, "the camera did not come back with the tab"

    # the face off → stopped (off means off); on → back
    n = desk.evaluate(STATE)["stopped"]
    desk.evaluate("() => window.__presence.setPresenceOn(false)")
    desk.wait_for_timeout(300)
    s = desk.evaluate(STATE)
    assert s["stopped"] > n and not s["live"], f"hiding the face kept the camera: {s}"
    desk.evaluate("() => window.__presence.setPresenceOn(true)")
    desk.wait_for_timeout(1000)
    assert desk.evaluate(STATE)["live"], "the face came back without its camera"

    # the badge is the way out: a tap turns the switch off, for this device
    n = desk.evaluate(STATE)["stopped"]
    desk.click(".hb-cam")
    desk.wait_for_timeout(300)
    s = desk.evaluate(STATE)
    assert not s["on"] and not s["checked"] and s["stopped"] > n and not s["badge"], f"the badge did not turn it off: {s}"
    assert json.loads(desk.evaluate("() => localStorage.getItem('hb_presence_look')")) == {"camera": False, "airpods": False}


def test_a_refused_camera_turns_the_switch_off_and_says_why(desk):
    desk.evaluate("() => { window.__refuse = true; }")
    desk.click(".pz-cam")
    desk.wait_for_timeout(600)
    s = desk.evaluate(STATE)
    desk.evaluate("() => { window.__refuse = false; }")
    assert not s["on"] and not s["checked"] and not s["live"], f"a refused camera left the switch on: {s}"
    assert "bloqueada" in s["hint"], f"the switch must say the camera is blocked: {s}"
    assert not desk._errors, desk._errors


def test_disarm_a_gate_forced_open_starts_the_camera_with_the_switch_off():
    served: list[str] = []

    def mutated(route):
        src = (PRESENCE / "LookAtMe.js").read_text(encoding="utf-8")
        assert "wants(lookCamera())" in src
        body = src.replace("const want = wants(lookCamera());", "const want = wants(true);")
        served.append(body)
        route.fulfill(status=200, content_type="text/javascript", body=body)

    with open_phone(DESK, width=1280, height=800, routes=[("**/presence/LookAtMe.js*", mutated)]) as pg:
        pg.wait_for_timeout(1500)
        assert served and "wants(true)" in served[0], "the disarm did not land"
        assert pg.evaluate("() => window.__gum.length") >= 1, "the gate forced open did not start the camera — the check is blind"


# ── the phone: the rows at the bottom of Settings, the AirPods only where the native app can read them ─────────────
PHONE = """
  const { MOBILE_SURFACES } = await import('/frontend/mobile/app/shell/mobile-surfaces.js?v=4');
  document.body.append(MOBILE_SURFACES.find(s => s.id === 'settings').comp());
  window.__store.setMobileSettingsOpen(true);
"""
# the iOS app's page glue (`mobile-app/www/in-app.js`): `window.ZaelarNative.headMotion`
NATIVE = """
  window.__hm = { started: 0, stopped: 0, emit: null };
  window.ZaelarNative = { headMotion: {
    available: async () => true,
    start: async (cb) => { window.__hm.started++; window.__hm.emit = cb; return true; },
    stop: async () => { window.__hm.stopped++; } } };
"""
ROWS = """() => { const rows = [...document.querySelectorAll('.zm-page[data-page="settings"] .zm-toggle')];
  const i = (s) => rows.findIndex(r => r.matches(s));
  return { n: rows.length, cam: i('.zm-look-cam'), air: i('.zm-look-airpods'),
           camText: (rows[i('.zm-look-cam')] || {}).innerText || '' }; }"""


def test_the_phone_has_the_camera_switch_at_the_bottom_and_no_airpods_on_the_web():
    with open_phone(FAKE_CAMERA + PHONE) as pg:
        pg.wait_for_timeout(800)
        r = pg.evaluate(ROWS)
        assert r["cam"] == r["n"] - 1, f"the camera switch is the last row of the phone's Settings: {r}"
        assert "Cámara: el agente te mira" in r["camText"], r
        assert r["air"] == -1, f"the AirPods switch shows on the plain web, where nothing can read them: {r}"
        assert pg.evaluate("() => window.__gum.length") == 0, "the phone's Settings started the camera"


def test_inside_the_native_app_the_airpods_switch_drives_the_plugin():
    with open_phone(FAKE_CAMERA + NATIVE + PHONE + """
      const { PresenceLayer } = await import('/frontend/app/presence/PresenceLayer.js?v=1');
      document.body.append(PresenceLayer());""") as pg:
        pg.wait_for_timeout(800)
        r = pg.evaluate(ROWS)
        assert r["air"] == r["n"] - 1 and r["cam"] == r["n"] - 2, f"the AirPods switch, under the camera's: {r}"
        pg.click(".zm-look-airpods")
        pg.wait_for_timeout(500)
        hm = pg.evaluate("() => ({ started: window.__hm.started, listening: !!window.__hm.emit })")
        assert hm == {"started": 1, "listening": True}, f"the switch did not start the headphone bridge: {hm}"
        pg.click(".zm-look-airpods")
        pg.wait_for_timeout(300)
        assert pg.evaluate("() => window.__hm.stopped") == 1, "turning the switch off did not stop the plugin"
        assert pg.evaluate("() => window.__gum.length") == 0, "the AirPods switch started the camera"
        assert not pg._errors, pg._errors

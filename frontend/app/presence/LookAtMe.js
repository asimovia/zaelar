// LookAtMe.js — «look at me» (V2-928 T10) wired to the live face: it starts and stops the sources and hands the face one
// target a few dozen times a second. The camera runs ONLY while all of these hold, and stops the moment one does not:
//   the switch is on · the face is on (this exists only while PresenceLayer has a face) · the tab is visible ·
//   the face is not covered (the phone's card or page in front of it) for more than a moment ·
//   no black face is up (the engine asleep, the voice held by another screen: Veil.js covers everything, the badge too).
// While the camera runs a small «● Camera» badge stays on screen above everything; tapping it turns the switch off.
// The AirPods source (iPhone app only) follows the same rules, without a badge: it reads no image.
// While the camera runs the face also ANSWERS him (T12, humanity/): imported only when the camera starts, it reads his
// expression on the device and plays the face's gestures back — no image or number is sent anywhere; only the NAMES of
// the last gestures (his and the face's answers) reach the agent, for half a minute (recent.js), so it can talk about them.
import { h } from "../core/dom.js?v=2";
import { createEffect, createSignal, untrack } from "../core/reactive.js?v=2";
import { t } from "../core/i18n.js?v=1";
import * as store from "../core/store.js?v=2";
import { createTracker, createHeadTracker, blend } from "./look.js?v=1";
import { startCamera, cameraError } from "./look-camera.js?v=1";
import { start as startHead } from "./head-motion.js?v=1";
import { clear as forgetRecent } from "./recent.js?v=1";
import { lookCamera, lookAirpods, setLookCamera, setLookAirpods, cameraLive, setCameraLive, setCameraProblem,
  setAirpodsProblem, airpodsAvailable, probeAirpods } from "./look-state.js?v=1";

const COVER_GRACE_MS = 2000, PUSH_MS = 40;
// A refusal or a missing device will not change by itself: the switch goes back off and says why.
const FINAL = new Set(["denied", "nocamera", "unsupported"]);

/** Start following for `face` (face.js). `covered` (optional) = the shell's «something opaque is in front»; `speech`
 *  (optional) → `{hearing, speaking}` (his mic hears him · the agent speaks), so talking is not read as a face. Returns dispose. */
export function LookAtMe(face, { covered = null, speech = () => ({}) } = {}) {
  return untrack(() => {
    probeAirpods();
    let disposed = false, cam = null, camStarting = false, headStop = null, headStarting = false, push = 0, coverTimer = 0;
    let humanity = null;
    const cams = createTracker(), heads = createHeadTracker();
    const [visible, setVisible] = createSignal(!document.hidden);
    const [hiddenLong, setHiddenLong] = createSignal(false);
    const onVis = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", onVis);
    const disposers = [];

    // a card over the face for a moment (a glance at a widget) does not flick the camera off and on
    if (covered) disposers.push(createEffect(() => {
      const c = !!covered();
      clearTimeout(coverTimer);
      if (!c) setHiddenLong(false); else coverTimer = setTimeout(() => setHiddenLong(true), COVER_GRACE_MS);
    }));
    const black = () => { const d = store.dormant(); return !!(d && d.face === "sleep") || !!store.remoteHeld(); };
    const wants = (on) => !disposed && on && visible() && !hiddenLong() && !black();

    function pump() {
      if (push) return;
      push = setInterval(() => {
        const now = performance.now();
        const target = blend(cams.sample(now), heads.sample(now));
        face.setLook(target);
        if (!cam && !headStop && !target) { clearInterval(push); push = 0; face.setLook(null); }
      }, PUSH_MS);
    }

    disposers.push(createEffect(() => {
      const want = wants(lookCamera());
      if (want && !cam && !camStarting) {
        camStarting = true;
        // the face answers you (T12): its module only now, with the camera; its landmarker loads behind the stream
        const hum = import("./humanity/index.js?v=1").then((m) => {
          if (disposed || !camStarting && !cam) return null;
          if (!humanity) humanity = m.createHumanity(face, { speech });
          return m;
        }).catch(() => null);
        startCamera({
          onFaces: (dets, at, faces) => {
            cams.feed(dets, at);
            if (humanity) humanity.frame(faces || dets.map((d) => ({ size: d.size })), at);
          },
          rich: () => hum.then((m) => (m ? m.meshDetector() : null)),
        }).then((handle) => {
          camStarting = false;
          if (!untrack(() => wants(lookCamera()))) { handle.stop(); return; }
          cam = handle; setCameraLive(true); setCameraProblem(""); pump();
          if (typeof window !== "undefined") window.__zaelarLook = { stats: () => (cam ? cam.stats() : null),
            humanity: () => (humanity ? { engagement: humanity.engagement, log: humanity.log } : null) };
        }).catch((e) => {
          camStarting = false;
          const why = cameraError(e);
          setCameraProblem(why);
          if (FINAL.has(why)) setLookCamera(false, "camera");
        });
      } else if (!want && cam) {
        cam.stop(); cam = null; setCameraLive(false); if (humanity) humanity.dispose(); humanity = null;
        forgetRecent("saw");                        // what the camera saw goes with it (the engine is told)
      }
    }));

    disposers.push(createEffect(() => {
      const want = wants(lookAirpods()) && airpodsAvailable();
      if (want && !headStop && !headStarting) {
        headStarting = true; heads.recenter();
        startHead((m) => heads.feed(m, performance.now())).then((stop) => {
          headStarting = false;
          if (!untrack(() => wants(lookAirpods()))) { stop(); return; }
          headStop = stop; setAirpodsProblem(""); pump();
        }).catch(() => {
          headStarting = false;
          setAirpodsProblem("unavailable"); setLookAirpods(false, "airpods");
        });
      } else if (!want && headStop) { headStop(); headStop = null; }
    }));

    // the badge: on screen exactly while the camera is
    const badge = h("button", { type: "button", class: "hb-cam", title: () => t("presence.camera_off_title"),
      "aria-label": () => t("presence.camera_off_title"), onClick: () => setLookCamera(false, "badge") },
      h("i", { "aria-hidden": "true" }), h("span", null, () => t("presence.camera_badge")));
    disposers.push(createEffect(() => {
      if (cameraLive()) { if (!badge.isConnected) document.body.append(badge); } else badge.remove();
    }));

    return () => {
      disposed = true;
      document.removeEventListener("visibilitychange", onVis);
      clearTimeout(coverTimer); clearInterval(push); push = 0;
      for (const d of disposers) d();
      if (cam) { cam.stop(); cam = null; }
      if (humanity) { humanity.dispose(); humanity = null; }
      forgetRecent("saw");
      if (headStop) { headStop(); headStop = null; }
      setCameraLive(false); badge.remove();
      face.setLook(null);
    };
  });
}

// look-state.js — the «look at me» switches (V2-928 T10): the camera, and the AirPods on an iPhone.
// The CAMERA is ON until he says otherwise (the operator, 2026-11-17): with no stored choice the first face that shows
// asks the browser for it; a refusal (or no camera, or no https) turns the switch off and is stored like a choice by
// hand, so it is never asked again in a loop. A choice by hand is kept, both ways. The AirPods stay OFF by default.
// Kept per DEVICE (localStorage only), never in the account: a camera and its permission belong to one browser on one
// machine, so turning it on at the phone must not make the computer ask for its camera. Runtime facts (is the camera
// live, why it could not start, can this device read headphone motion) are signals here too, so the desktop's Settings,
// the phone's Settings and the indicator all read ONE copy.
import { createSignal } from "../core/reactive.js?v=2";
import * as api from "../services/api.js?v=2";
import { available as headAvailable } from "./head-motion.js?v=1";

const KEY = "hb_presence_look";
function read() {
  try { const d = JSON.parse(localStorage.getItem(KEY) || "{}"); return d && typeof d === "object" ? d : {}; } catch (_) { return {}; }
}
const boot = read();
const [camera, setCameraRaw] = createSignal(boot.camera !== false);   // no record = never touched = on
const [airpods, setAirpodsRaw] = createSignal(boot.airpods === true);
export { camera as lookCamera, airpods as lookAirpods };

/** Live facts: the camera is running · why a source could not start ("" | denied | nocamera | unsupported | unavailable). */
export const [cameraLive, setCameraLive] = createSignal(false);
export const [cameraProblem, setCameraProblem] = createSignal("");
export const [airpodsProblem, setAirpodsProblem] = createSignal("");
/** Why a source could not start → the i18n key of the line under its switch (both shells say the same). */
export const CAMERA_PROBLEM = { denied: "presence.camera_denied", nocamera: "presence.camera_nocamera",
  unsupported: "presence.camera_unsupported", unavailable: "presence.camera_unavailable" };
export const AIRPODS_PROBLEM = { unavailable: "presence.airpods_unavailable" };
/** True only in the native iPhone app with the headphone-motion plugin (head-motion.js); the switch shows only then. */
export const [airpodsAvailable, setAirpodsAvailable] = createSignal(false);
let _asked = false;
export function probeAirpods() { if (_asked) return; _asked = true; headAvailable().then((ok) => setAirpodsAvailable(!!ok)).catch(() => {}); }

function persist() { try { localStorage.setItem(KEY, JSON.stringify({ camera: camera(), airpods: airpods() })); } catch (_) {} }

export function setLookCamera(v, by = "ui") {
  const next = !!v;
  if (next) setCameraProblem("");
  if (next === camera()) return;
  setCameraRaw(next); persist();
  try { api.uiEvent("presence:camera:" + (next ? "on" : "off"), { by }); } catch (_) {}
}
export function setLookAirpods(v, by = "ui") {
  const next = !!v;
  if (next) setAirpodsProblem("");
  if (next === airpods()) return;
  setAirpodsRaw(next); persist();
  try { api.uiEvent("presence:airpods:" + (next ? "on" : "off"), { by }); } catch (_) {}
}

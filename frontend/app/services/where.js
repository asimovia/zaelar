// where.js — this screen tells the agent where it is (V2-875; the engine side is `nucleo/where.py` → state `here`).
//
// Only while the person's `privacy.location` switch is on, and only with a platform permission ALREADY granted: a
// page never raises a location prompt on load. The prompt is asked by a gesture — flipping the switch on
// (`report({ask: true})`). Then on load, when the screen comes back to the front, and every quarter of an hour while
// it is visible; coarse (the engine rounds to ~1 km anyway). Failures are silent: no fix, no report.
import { DEVICE } from "./api.js?v=2";

const EVERY_MS = 15 * 60 * 1000;
let on = false, timer = null, last = 0;

async function granted() {
  const cap = globalThis.Capacitor;
  const geo = cap && cap.isNativePlatform && cap.isNativePlatform() && cap.Plugins ? cap.Plugins.Geolocation : null;
  try {
    if (geo) { const p = await geo.checkPermissions(); return p.location === "granted" || p.coarseLocation === "granted"; }
    return (await navigator.permissions.query({ name: "geolocation" })).state === "granted";
  } catch (_) { return false; }
}

/** Send one fix. `ask: true` (a gesture) lets the platform ask for the permission; otherwise only if granted. */
export async function report({ ask = false } = {}) {
  if (!on || !(ask || (await granted()))) return null;
  const fix = await (await import("./device.js?v=1")).location({ precise: false });
  if (!fix || fix.error) return fix;
  last = Date.now();
  return fetch("/api/device/location", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lat: fix.lat, lon: fix.lon, accuracy: fix.accuracy, dev: DEVICE }),
  }).then((r) => r.json()).catch(() => null);
}

/** Follow the switch (and, in the app, the AI-services yes): on → report now and every quarter of an hour. */
export function setEnabled(v) {
  on = !!v;
  clearInterval(timer);
  timer = null;
  if (!on) return;
  report();
  timer = setInterval(() => { if (document.visibilityState === "visible") report(); }, EVERY_MS);
}

if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    if (on && document.visibilityState === "visible" && Date.now() - last > EVERY_MS) report();
  });
}

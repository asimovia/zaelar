// head-motion.js — «follow me with AirPods» (V2-928 T10): the person's HEAD orientation from motion-sensing headphones,
// which only the native iPhone app can read (Core Motion's headphone motion manager). A web page cannot: in a browser,
// on Android, or in an app build without the bridge, `available()` is false and the switch is not shown at all.
//
// THE NATIVE CONTRACT — the app's page glue (`mobile-app/www/in-app.js`, over its device plugin) puts on the page:
//   window.ZaelarNative.headMotion = {
//     available() → Promise<boolean>   the device can read headphone motion (iOS); false on Android
//     start(cb)   → Promise<boolean>   begin updates; false when it could not start (no headphones, Motion refused)
//     stop()      → Promise            end updates (idempotent)
//   }  with cb({yaw, pitch, t}): Core Motion's attitude AS IT COMES — radians, yaw > 0 when the head turns to ITS
//   LEFT (counter-clockwise seen from above), pitch > 0 looking up — and t in ms (epoch).
// This module flips the yaw ONCE, here, into the engine's convention (look.js: yaw > 0 = the person turns to THEIR
// right). Nothing is recorded or sent anywhere: the numbers go to look.js and are dropped.

const bridge = () => {
  const n = globalThis.window && window.ZaelarNative;
  const hm = n && n.headMotion;
  return hm && typeof hm.available === "function" && typeof hm.start === "function" ? hm : null;
};

/** True only where the app's bridge says the device can read headphone motion. */
export async function available() {
  const hm = bridge();
  if (!hm) return false;
  try { return !!(await hm.available()); } catch (_) { return false; }
}

/** Start following: `cb({yaw, pitch, t})` per sample (yaw > 0 = to their right). Resolves to a `stop()`. */
export async function start(cb) {
  const hm = bridge();
  if (!hm) throw Object.assign(new Error("no headphone motion here"), { code: "unsupported" });
  let ok = false;
  try {
    ok = await hm.start((m) => { if (m && Number.isFinite(+m.yaw)) cb({ yaw: -m.yaw, pitch: +m.pitch, t: +m.t || Date.now() }); });
  } catch (_) { ok = false; }
  if (!ok) throw Object.assign(new Error("headphone motion did not start"), { code: "unavailable" });
  let stopped = false;
  return () => { if (stopped) return; stopped = true; try { hm.stop(); } catch (_) {} };
}

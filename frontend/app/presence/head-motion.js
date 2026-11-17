// head-motion.js — «follow me with AirPods» (V2-928 T10): the person's HEAD orientation from motion-sensing headphones,
// which only the native iPhone app can read (Core Motion's headphone motion manager). A web page cannot: in a browser,
// on Android, or in an app without the plugin, `available()` is false and the switch is not shown at all.
//
// THE NATIVE CONTRACT — a Capacitor plugin registered as `ZaelarHeadMotion` (reached through the bridge like every
// native plugin here, `Capacitor.Plugins[name]`, never an npm import: the shell is served by the engine):
//   isAvailable() → Promise<{ available: boolean }>   the device can read headphone motion (iOS 14+), even if no
//                                                     headphones are connected right now
//   start()       → Promise<void>                     begin updates; rejects with code "denied" when the person refuses
//                                                     Motion & Fitness, "unavailable" otherwise
//   stop()        → Promise<void>                     end updates (idempotent)
//   event "motion" { yaw, pitch, t }                  radians, yaw > 0 when the person turns their head to THEIR
//                                                     right, pitch > 0 when they look up; t = ms (epoch); ~25 Hz
//   event "status" { connected }                      optional: headphones with motion came or went
// Nothing is recorded or sent anywhere: the numbers go to look.js and are dropped.

const plugin = () => {
  const c = globalThis.Capacitor;
  return c && c.isNativePlatform && c.isNativePlatform() && c.Plugins ? c.Plugins.ZaelarHeadMotion || null : null;
};

/** True only inside the native app whose plugin says the device can read headphone motion. */
export async function available() {
  const p = plugin();
  if (!p || typeof p.isAvailable !== "function") return false;
  try { const r = await p.isAvailable(); return !!(r && r.available); } catch (_) { return false; }
}

/** Start following: `cb({yaw, pitch, t})` per sample. Resolves to a `stop()`; rejects with code denied|unavailable. */
export async function start(cb) {
  const p = plugin();
  if (!p) throw Object.assign(new Error("no headphone motion here"), { code: "unsupported" });
  const subs = [];
  const on = async (ev, fn) => { try { const h = await p.addListener(ev, fn); if (h) subs.push(h); } catch (_) {} };
  await on("motion", (m) => { if (m) cb({ yaw: +m.yaw, pitch: +m.pitch, t: +m.t || Date.now() }); });
  try { await p.start(); }
  catch (e) { for (const s of subs) { try { s.remove(); } catch (_) {} } throw Object.assign(new Error("headphone motion refused"), { code: e && e.code === "denied" ? "denied" : "unavailable" }); }
  let stopped = false;
  return () => {
    if (stopped) return; stopped = true;
    for (const s of subs) { try { s.remove(); } catch (_) {} }
    try { p.stop(); } catch (_) {}
  };
}

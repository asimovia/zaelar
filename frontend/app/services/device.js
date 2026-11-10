// device.js — the screen as a SENSOR (V2-870 §10 P2): location, motion and compass behind one door, the same
// signatures in a browser (Web APIs) and in the native app (Capacitor plugins through the bridge, never an npm
// import: the shell is served by the engine, not bundled into the app). Apps reach it as `ctx.device`.
//
// Rules: nothing is stored here — an app that wants a track keeps it in its own data. Every failure is a VALUE
// ({error: "denied" | "unavailable" | "unsupported" | "timeout"}), never a throw, so a declined permission breaks
// nothing and the app can say what it cannot do. The system asks for the permission the first time it is used.

const native = (name) => {
  const c = globalThis.Capacitor;
  return c && c.isNativePlatform && c.isNativePlatform() && c.Plugins ? c.Plugins[name] || null : null;
};
const fix = (p) => (p && p.coords ? {
  lat: p.coords.latitude, lon: p.coords.longitude, accuracy: p.coords.accuracy,
  altitude: p.coords.altitude ?? null, heading: p.coords.heading ?? null, speed: p.coords.speed ?? null,
  at: p.timestamp || Date.now(),
} : null);
const why = (e) => {
  const s = String((e && (e.message || e.code)) || e || "").toLowerCase();
  return { error: e && e.code === 1 || /denied|permission/.test(s) ? "denied" : e && e.code === 3 || /timeout/.test(s) ? "timeout" : "unavailable" };
};
const opts = (precise, timeout) => ({ enableHighAccuracy: precise !== false, timeout: timeout || 15000, maximumAge: 10000 });

/** What this screen can sense right now (the platform answers; the permission is asked on first use). */
export function capabilities() {
  const out = [];
  if (native("Geolocation") || (typeof navigator !== "undefined" && navigator.geolocation)) out.push("location");
  if (typeof DeviceMotionEvent !== "undefined") out.push("motion");
  if (typeof DeviceOrientationEvent !== "undefined") out.push("heading");
  return out;
}

/** One position: {lat, lon, accuracy, altitude, heading, speed, at} or {error}. */
export async function location({ precise = true, timeout } = {}) {
  const geo = native("Geolocation");
  if (geo) { try { return fix(await geo.getCurrentPosition(opts(precise, timeout))); } catch (e) { return why(e); } }
  if (typeof navigator === "undefined" || !navigator.geolocation) return { error: "unsupported" };
  return new Promise((done) => navigator.geolocation.getCurrentPosition(
    (p) => done(fix(p)), (e) => done(why(e)), opts(precise, timeout)));
}

/** Follow the position: `onFix` gets each fix (or {error}); returns stop(). Tracking only while the screen is on. */
export function watchLocation(onFix, { precise = true } = {}) {
  const geo = native("Geolocation");
  if (geo) {
    const id = geo.watchPosition(opts(precise), (p, e) => onFix(e ? why(e) : fix(p)));
    return () => { Promise.resolve(id).then((cid) => geo.clearWatch({ id: cid })).catch(() => {}); };
  }
  if (typeof navigator === "undefined" || !navigator.geolocation) { onFix({ error: "unsupported" }); return () => {}; }
  const id = navigator.geolocation.watchPosition((p) => onFix(fix(p)), (e) => onFix(why(e)), opts(precise));
  return () => navigator.geolocation.clearWatch(id);
}

// iOS Safari gates motion and orientation behind a permission that must come from a tap; the native app grants it.
async function _allowed(Ev) {
  if (!Ev || typeof Ev.requestPermission !== "function") return true;
  try { return (await Ev.requestPermission()) === "granted"; } catch (_) { return false; }
}

/** Acceleration (m/s², gravity included) and rotation rate: `onReading({x, y, z, alpha, beta, gamma, at})`. */
export async function motion(onReading) {
  if (typeof DeviceMotionEvent === "undefined") return { error: "unsupported", stop: () => {} };
  if (!(await _allowed(DeviceMotionEvent))) return { error: "denied", stop: () => {} };
  const h = (e) => { const a = e.accelerationIncludingGravity || {}, r = e.rotationRate || {};
    onReading({ x: a.x, y: a.y, z: a.z, alpha: r.alpha, beta: r.beta, gamma: r.gamma, at: Date.now() }); };
  addEventListener("devicemotion", h);
  return { stop: () => removeEventListener("devicemotion", h) };
}

/** Compass heading in degrees from north (0-360), when the device has one: `onHeading(deg)`. */
export async function heading(onHeading) {
  if (typeof DeviceOrientationEvent === "undefined") return { error: "unsupported", stop: () => {} };
  if (!(await _allowed(DeviceOrientationEvent))) return { error: "denied", stop: () => {} };
  const h = (e) => { const d = e.webkitCompassHeading ?? (e.absolute && e.alpha != null ? 360 - e.alpha : null);
    if (d != null) onHeading(d); };
  addEventListener("deviceorientation", h);
  return { stop: () => removeEventListener("deviceorientation", h) };
}

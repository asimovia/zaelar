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

// ── The native device bridge (V2-890): the app's own `ZaelarDevice` plugin. Only in the native app; elsewhere every
// call answers `unsupported`, so an app written once runs everywhere and says what this screen cannot do.
const bridge = () => native("ZaelarDevice");

/** What this screen is and has, in full: {platform, form, sensors: {name: {available, permission, …}}, background}.
 *  In a browser: the Web APIs above, foreground only. Apps read it to adapt (no strap → no heart-rate panel). */
export async function details() {
  const b = bridge();
  if (b) { try { return await b.capabilities(); } catch (_) { /* an older app build: fall through */ } }
  const has = capabilities();
  const s = (k) => ({ available: has.includes(k), permission: "ask_on_use" });
  return { platform: "web", form: typeof matchMedia !== "undefined" && matchMedia("(pointer: coarse)").matches ? "phone" : "desktop",
    background_sessions: false, sensors: { location: s("location"), motion: s("motion"), heading: s("heading") } };
}

/** An ACTIVITY the person started (a ride, a run, a walk, a drive): `sensors` ⊂ location · heart_rate ·
 *  motion_activity · altitude. Samples `{kind, t, …}` reach `onSample` while the screen is on; with the screen locked
 *  the native app keeps reading and hands the missed samples over when it comes back. Returns {stop} or {error}.
 *  In a browser only `location` runs, and only while the screen is on. */
export async function activity({ sensors = ["location"], label = "", kind = "fitness" } = {}, onSample = () => {}) {
  const b = bridge();
  if (!b) {
    if (!sensors.includes("location")) return { error: "unsupported" };
    const stop = watchLocation((f) => { if (!f.error) onSample({ kind: "location", t: f.at, lat: f.lat, lon: f.lon, accuracy_m: f.accuracy, speed_mps: f.speed }); });
    return { stop, background: false };
  }
  let last = -1, live = true;
  const take = (x) => { if (x && x.seq > last) { last = x.seq; onSample(x); } };
  const drain = async () => {
    for (let more = true; more && live;) {
      const r = await b.drain({ after: last }).catch(() => ({ samples: [] }));
      (r.samples || []).forEach(take); more = !!r.more && (r.samples || []).length > 0;
    }
  };
  try { await b.startSession({ sensors, label, activity: kind, background: true }); } catch (e) { return why(e); }
  const subs = [await b.addListener("sample", take)];
  const back = () => { if (document.visibilityState === "visible") drain(); };
  document.addEventListener("visibilitychange", back);
  return { background: true, stop: async () => {
    await drain(); live = false;
    document.removeEventListener("visibilitychange", back);
    subs.forEach((s) => s && s.remove && s.remove());
    await b.stopSession().catch(() => {});
  } };
}

/** Heart-rate straps and watches in range (Bluetooth Heart Rate Service): [{id, name}]; `pick(id)` remembers one. */
export async function heartRateStraps(seconds = 6) {
  const b = bridge();
  if (!b) return { error: "unsupported", straps: [] };
  try { return { straps: (await b.scanHeartRate({ seconds })).straps || [], pick: (id) => b.scanHeartRate({ pick: id }) }; }
  catch (e) { return { ...why(e), straps: [] }; }
}

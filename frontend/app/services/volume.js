// volume.js — the agent's OWN voice volume on THIS screen (0–100): one door for the 🔊's slider and for his voice.
//
// It is the level of the agent's voice coming out of this page — the <audio> element the LiveKit track plays in —
// never the device's system volume, which a web page (and an iOS app through public API) cannot set. Kept per device
// (`hb_bot_volume`): the phone and the desktop each keep their own. Mute stays its own switch (`store.botMuted`, the
// 🔊): the element plays at 0 while muted and at this level otherwise, so un-muting brings back the level he chose.
// iOS WebKit (Safari and the app's WKWebView) ignores `HTMLMediaElement.volume`: there the voice leaves through a
// Web Audio gain instead (services/audio.js — same track, source → gain → speakers) and the element only stays silent.
// Everywhere else the element's own volume is the level, as before: on Chrome a remote voice played through Web Audio
// is not the reference its echo canceller listens to, so the mic would hear the agent. Only with neither (no Web
// Audio either) is `settable()` false, and the screen says so instead of claiming a level it could not set. Nothing
// here waits on a frame or on the page being visible: a locked phone's voice order lands the same way.
import * as store from "../core/store.js?v=2";
import { createEffect, createSignal } from "../core/reactive.js?v=2";
import * as audio from "./audio.js?v=2";

const KEY = "hb_bot_volume";
/** One spoken «louder» / «quieter». */
export const STEP = 20;

/** A level as an integer 0–100; `fallback` when it is not a number. */
export function clamp(n, fallback = 100) {
  const v = Math.round(Number(n));
  return Number.isFinite(v) && String(n).trim() !== "" ? Math.max(0, Math.min(100, v)) : fallback;
}
const _read = () => { try { const v = localStorage.getItem(KEY); return v === null ? 100 : clamp(v); } catch (_) { return 100; } };
const [_level, _setLevel] = createSignal(_read());
const [_shown, _setShown] = createSignal(false);
/** The level (reactive). */
export const level = _level;
/** Whether the transient slider over the 🔊 shows (reactive). */
export const shown = _shown;

/** Show the slider for a few seconds (a wheel notch, a voice order, a drag re-arms it). */
export function reveal(ms = 4000) {
  _setShown(true);
  clearTimeout(reveal._t); reveal._t = setTimeout(() => _setShown(false), ms);
}

/** THE ONE WRITE: set the level, persist it on this device, show it. Returns the level it landed on. */
export function setLevel(n) {
  const v = clamp(n, _level());
  _setLevel(v);
  try { localStorage.setItem(KEY, String(v)); } catch (_) { /* private window: this session only */ }
  reveal();
  return v;
}
/** One step louder (+1) or quieter (−1). */
export const step = (dir) => setLevel(_level() + (dir < 0 ? -STEP : STEP));

/** What the bot's <audio> plays at: 0 while the 🔊 is muted, else the level. */
export const out = () => (store.botMuted() ? 0 : _level() / 100);

/** Hold the element to the 🔊 and the level. The vendor rewrites `muted` on every attach, so the session calls this on
 *  attach and on every `volumechange` (writes only on a difference, so it cannot loop). With the voice routed through
 *  the gain the element is held SILENT — it is still the track's sink, but the voice must come out once — and the
 *  gain carries the level and the 🔊. */
export function enforce(el) {
  audio.setBotGain(out());
  if (!el) return;
  const routed = audio.botOutRouted();
  const muted = routed || store.botMuted(), v = routed ? 0 : out();
  if (el.muted !== muted) el.muted = muted;
  if (routed) return;   // a volume the platform ignores is not written (it would only fire a `volumechange` loop)
  if (Math.abs((typeof el.volume === "number" ? el.volume : 1) - v) > 0.004) { try { el.volume = v; } catch (_) {} }
}
/** Keep `el` following the level and the 🔊 for the life of the page — and the gain route appearing or going. */
export function bind(el) {
  audio.onBotOutChange(() => enforce(el));
  createEffect(() => { _level(); store.botMuted(); enforce(el); });
}

let _honours = null;
// iOS WebKit KEEPS the value written to an element's `volume` and reads it back, yet plays at full (measured on an
// iPhone, iOS 18.7, in the app's WKWebView, 2026-11-17): a read-back probe cannot see it, so iOS is told by its
// platform (every browser there is WebKit; an iPad asks for the desktop site as a touch «MacIntel»).
const _iosWebKit = () => {
  try { const n = navigator; return /iPad|iPhone|iPod/.test(n.userAgent || "") || (n.platform === "MacIntel" && n.maxTouchPoints > 1); }
  catch (_) { return false; }
};
/** Does this platform play an element at the volume the page sets? False on iOS WebKit. */
export function elementHonoursVolume() {
  if (_honours !== null) return _honours;
  if (_iosWebKit()) return (_honours = false);
  try { const a = document.createElement("audio"); a.volume = 0.5; _honours = Math.abs(a.volume - 0.5) < 0.01; }
  catch (_) { _honours = true; }
  return _honours;
}
const _webAudio = () => typeof window !== "undefined" && !!(window.AudioContext || window.webkitAudioContext);
/** Should the agent's voice leave through the gain on this screen? Only where the element's volume is ignored. */
export function routesOut() { return !elementHonoursVolume() && _webAudio(); }
/** False only where neither the element nor a gain can carry the level: the screen says so instead. */
export function settable() { return elementHonoursVolume() || _webAudio(); }

// state.js — the agent's presence choice, ONE copy for every surface (V2-928): on/off, which face, and his own
// customised face. Same two-layer persistence as the theme (services/theme.js): localStorage paints at boot without
// a flash, and /api/settings (`presence`) makes it durable per ACCOUNT — the server wins when they disagree.
import { createSignal } from "../core/reactive.js?v=2";
import * as api from "../services/api.js?v=2";

/** The face everyone starts with: the Porcelain classic. */
export const DEFAULT_FACE = "c-porcelain";
const KEY = "hb_presence";

function read() {
  try { const d = JSON.parse(localStorage.getItem(KEY) || "{}"); return d && typeof d === "object" ? d : {}; } catch (_) { return {}; }
}
const boot = read();
const [on, setOnRaw] = createSignal(boot.on !== false);
const [face, setFaceRaw] = createSignal(typeof boot.face === "string" && boot.face ? boot.face : DEFAULT_FACE);
const [custom, setCustomRaw] = createSignal(boot.custom && typeof boot.custom === "object" ? boot.custom : null);
export { on as presenceOn, face as presenceFace, custom as presenceCustom };

const snapshot = () => ({ on: on(), face: face(), custom: custom() });
function persist(server = true) {
  try { localStorage.setItem(KEY, JSON.stringify(snapshot())); } catch (_) {}
  // Best-effort: the account copy. A failed save costs durability, never the current paint.
  if (server) api.saveSettings({ presence: snapshot() }).catch(() => {});
}

export function setPresenceOn(v, by = "ui") {
  const next = !!v;
  if (next === on()) return;
  setOnRaw(next); persist();
  try { api.uiEvent("presence:" + (next ? "on" : "off"), { by }); } catch (_) {}
}
export const togglePresence = (by) => setPresenceOn(!on(), by);

/** Choose a catalogue face (its id), keeping his customised one stored. */
export function setPresenceFace(id) { if (typeof id !== "string" || !id) return; setFaceRaw(id); persist(); }

/** Save his customised face and wear it at once. */
export function saveCustomFace(spec) { setCustomRaw(JSON.parse(JSON.stringify(spec))); setFaceRaw("mine"); persist(); }

/** Back to the default for everyone: Porcelain, on. His customised face is forgotten. */
export function resetPresence() { setCustomRaw(null); setFaceRaw(DEFAULT_FACE); setOnRaw(true); persist(); }

/** Adopt the account's copy (boot reconcile, or a change pushed from another screen). */
export function adopt(p) {
  if (!p || typeof p !== "object") return;
  if (typeof p.on === "boolean") setOnRaw(p.on);
  if (typeof p.face === "string" && p.face) setFaceRaw(p.face);
  setCustomRaw(p.custom && typeof p.custom === "object" ? p.custom : null);
  persist(false);
}

let _synced = false;
/** One reconcile fetch per page: the server is the copy that survives a new browser. */
export function syncPresence() {
  if (_synced) return; _synced = true;
  api.getSettings().then((d) => { if (d && d.presence && typeof d.presence === "object" && Object.keys(d.presence).length) adopt(d.presence); }).catch(() => {});
}

// «Open the presence settings» (the voice act, a row): each shell names ITS page. The phone registers its Presence page
// here; with none registered the caller opens the desktop's Settings ▸ Presence. One door, two screens.
let _page = null;
export function setPresencePage(open) { _page = typeof open === "function" ? open : null; }
/** True when a shell's own page took the order. */
export function openPresencePage() { if (!_page) return false; _page(); return true; }

// privacy.js — the person's permission switches (V2-875), one source for both shells' Permissions section.
//
// They are the ENGINE's (`config/v2` section `privacy`: location, files, observability, obfuscate), so one flip
// covers every device of this agent: read from `/api/config`, written with `POST /api/config/v2`. The screen
// changes only once the engine has the value. Location also drives this screen's reporter (`where.js`).
import { createSignal } from "../core/reactive.js?v=2";

export const KEYS = ["location", "files", "observability", "obfuscate"];
const DEFAULTS = { location: true, files: true, observability: true, obfuscate: true };
const [values, setValues] = createSignal({ ...DEFAULTS });
export { values };
let gate = () => true;          // the phone app's AI-services yes (no location reaches the agent before it)

async function _where(on) { (await import("./where.js?v=1")).setEnabled(on && gate()); }

/** Read the switches from a `/api/config` payload. `allow` = an extra condition for reporting the location. */
export function loadFrom(cfg, allow) {
  if (allow) gate = allow;
  setValues({ ...DEFAULTS, ...((cfg && cfg.v2 && cfg.v2.privacy) || {}) });
  _where(values().location);
}

/** Re-apply after the extra condition changed (the AI-services yes arrived). */
export const refresh = () => _where(values().location);

/** Flip one switch on the engine. Turning location on is a gesture: it asks for the permission and reports once. */
export async function set(key, on) {
  if (!KEYS.includes(key)) return false;
  const r = await fetch("/api/config/v2", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ section: "privacy", patch: { [key]: !!on } }),
  }).then((x) => x.json()).catch(() => null);
  if (!(r && r.ok)) return false;
  setValues({ ...values(), [key]: !!on });
  if (key === "location") {
    await _where(!!on);
    if (on && gate()) (await import("./where.js?v=1")).report({ ask: true });
  }
  return true;
}

// ai-consent.js — inside the native app, nothing reaches the AI services before the person says yes (V2-870, App
// Review 5.1.2(i)): the voice does not start, the orb and the chat's send button ask first. A browser is unaffected.
//
// The answer is the ENGINE's, not this phone's: it is stored in the engine's config (`config/v2` section `consent`,
// key `ai_providers`, through the same `POST /api/config/v2` every setting uses) and read back from `/api/config`, so
// one yes covers every device of this agent and survives a reinstall. Until the config has been read the answer is
// unknown, and unknown counts as «not yet»: no voice before we know.
import { createSignal } from "../../../app/core/reactive.js?v=2";
import { inNativeApp } from "../../../app/core/native.js?v=1";

const [accepted, setAccepted] = createSignal(false);
export const [sheetOpen, setSheetOpen] = createSignal(false);
export { accepted };

/** Read the engine's answer from a `/api/config` payload; ask at once if the answer is still no. */
export function loadFrom(cfg) {
  setAccepted(!!(cfg && cfg.v2 && cfg.v2.consent && cfg.v2.consent.ai_providers));
  if (pending()) setSheetOpen(true);
}

/** Is a yes still missing on this screen? Only ever true inside the native app. */
export const pending = () => inNativeApp() && !accepted();

/** Run `fn` (start the voice, send a line) — or open the question instead while the yes is missing. */
export function gate(fn) {
  if (pending()) { setSheetOpen(true); return undefined; }
  return fn();
}

const _post = (yes) => fetch("/api/config/v2", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ section: "consent", patch: { ai_providers: !!yes } }),
}).then((r) => r.json()).catch(() => null);

/** Record the answer on the engine; the screen changes only once the engine has it. */
export async function decide(yes, post = _post) {
  const r = await post(!!yes);
  if (!(r && r.ok)) return false;
  setAccepted(!!yes);
  if (yes) setSheetOpen(false);
  import("../../../app/services/privacy.js?v=1").then((p) => p.refresh()).catch(() => {});   // location may report now
  return true;
}

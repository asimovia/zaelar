// native-audio.js — what the phone app says about the voice's audio (`window.ZaelarNative.audio`, the app's own glue in
// mobile-app/www/in-app.js; absent in a browser). An interruption that ends (a call, Siri, the media services reset)
// resumes the context the iOS voice gain plays in, so the agent is heard again without a tap; every route change and
// interruption is recorded for the session's trace. The level is never the app's: it stays services/volume.js's.
import * as audio from "./audio.js?v=2";
import * as api from "./api.js?v=2";

let _watching = false;

/** Start listening once, if this page runs inside the app. Returns whether it did. */
export function watch() {
  const bridge = typeof window !== "undefined" && window.ZaelarNative && window.ZaelarNative.audio;
  if (!bridge || _watching) return false;
  _watching = true;
  bridge.onInterruption((e) => {
    try { api.clientLog("🔈 audio interrupted", { text: `${e.phase} ${e.reason || ""}`.trim(), state: e.phase }); } catch (_) {}
    if (e.phase === "ended" || e.phase === "reset") audio.resumeContext();
  });
  bridge.onRouteChange((r) => {
    try { api.clientLog("🔈 audio route", { text: `${r.output} ${r.name || ""} (${r.reason || ""})`, state: r.output }); } catch (_) {}
  });
  return true;
}

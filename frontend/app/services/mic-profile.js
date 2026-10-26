// ============================================================================
// mic-profile.js — which capture profile the microphone opens with, per platform (V2-812 T-08).
//
// THE BUG. The old «is it a Mac» check was `/Mac|iP(hone|ad|od)/` over `navigator.platform`, so an iPhone or iPad
// got the Mac's «isolate» profile: echo cancellation ONLY, no noise suppression, no gain control. That profile
// exists on purpose for a Mac — it turns on macOS's voice-processing unit, where the system's Voice Isolation hooks
// in, without Chrome's weaker noise suppression fighting it. A phone has no such switch the page can rely on, and
// in a car it is the device that most needs suppression and gain.
//
// THE RULE.
//   • A phone or tablet (iOS, iPadOS, Android) → «full»: echoCancellation + noiseSuppression + autoGainControl.
//   • A desktop Mac → «isolate» (unchanged).
//   • Anything else → «full» (unchanged).
//   • `voiceIsolation` is asked ONLY where the browser reports it in `getSupportedConstraints()` — never blind: a
//     browser that ignores it would only create a false sense of isolation.
//
// Detection prefers capabilities over the user-agent string: `userAgentData.mobile` where the browser has it, and
// touch points to tell iPadOS (which reports «MacIntel») from a real Mac. The UA string is the last resort.
// Pure: everything it reads comes in as `nav`, so it runs under node with a fake navigator.
// ============================================================================

export const MIC_MODES = {
  isolate: { echoCancellation: true,  noiseSuppression: false, autoGainControl: false },
  full:    { echoCancellation: true,  noiseSuppression: true,  autoGainControl: true  },
  raw:     { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
};

/** "mobile" (phone/tablet), "mac" (desktop macOS) or "other". */
export function platformKind(nav) {
  const n = nav || {};
  const plat = String((n.userAgentData && n.userAgentData.platform) || n.platform || "");
  const ua = String(n.userAgent || "");
  const touch = Number(n.maxTouchPoints || 0);
  if (n.userAgentData && n.userAgentData.mobile === true) return "mobile";
  if (/iPhone|iPad|iPod|Android/i.test(plat) || /iPhone|iPad|iPod|Android/i.test(ua)) return "mobile";
  if (/Mac/i.test(plat)) return touch > 1 ? "mobile" : "mac";   // iPadOS desktop-mode reports MacIntel + touch
  return "other";
}

/** The default mode when nothing (URL flag, saved choice) overrides it. */
export function defaultMicMode(nav) {
  return platformKind(nav) === "mac" ? "isolate" : "full";
}

/** The getUserMedia audio constraints for `mode`, plus `voiceIsolation` where the browser supports it. */
export function captureConstraints(mode, nav) {
  const base = { ...(MIC_MODES[mode] || MIC_MODES.full) };
  if (mode === "raw") return base;
  let sup = {};
  try { sup = (nav && nav.mediaDevices && nav.mediaDevices.getSupportedConstraints && nav.mediaDevices.getSupportedConstraints()) || {}; }
  catch (e) { console.warn("getSupportedConstraints failed:", e); }
  if (sup.voiceIsolation === true) base.voiceIsolation = true;
  return base;
}

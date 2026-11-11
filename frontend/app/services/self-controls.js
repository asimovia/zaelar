// self-controls.js — his own 🔊 / ⏻ ordered by VOICE (nucleo/acts/self_controls.py): this screen presses its button.
//
// The brain emits one `controls` event, scoped to the screen that heard him (`event-scope.js`: `controls` is
// origin-scoped), and this module runs THE BUTTON'S DOOR, never a copy of it: the 🔊 does what the bar's speaker does
// (bring the speaker here when it is muted, else the toggle — Orb.js / DockBar.js) and «off» runs `power.setPower`, the
// ⏻'s own body (server first, then the session). Both are imported lazily: session.js imports sse.js, which imports
// this, so a static import would close the cycle.
import * as store from "../core/store.js?v=2";

/** Apply one `controls` act (`mute` · `unmute` · `off`). Idempotent: a state already reached is left alone. */
export function applyControl(d) {
  const act = String((d && (d.act || d.label)) || "");
  if (act === "off") {
    import("./power.js?v=1").then(p => { if (!store.powerOff()) p.setPower(true, "voice"); }).catch(() => {});
  } else if (act === "mute" || act === "unmute") {
    import("./session.js?v=3").then(session => {
      const muted = store.botMuted();
      if (act === "mute" && !muted) session.toggleBotMute();
      else if (act === "unmute" && muted) {
        if (session.openSpeakerHere) session.openSpeakerHere("voice"); else session.toggleBotMute();
      }
    }).catch(() => {});
  }
}

// ============================================================================
// OrbMini.js — zaelar's face, shrunk into the CENTRE of the dock.  The desktop's Orb.js is 24 KB because it is also
// the «eye»: an arc of seven controls, an ECG lower lid, a caption teleprompter, a drag handle. None of that survives
// a 76px-tall bar, so this is a fresh component — but it reuses the ENGINE of the desktop orb rather than a copy of it:
//
//   session.startVisuals({ orbCanvas, vizCanvas })
//
// That function takes two <canvas> elements and nothing else (services/visualizer.js reads only the theme and the
// --canvas token; it never queries the DOM for layout). So the animation — zaelar's voice on the orb, the person's
// voice on the spectrum — is literally the same code the desktop runs. If the orb changes there, it changes here.
// That is what makes the operator's «que se mueva cuando la gente nos habla» true by construction rather than by a
// second implementation that would drift.
//
// The canvas keeps the id `orb` deliberately: lib/ecg.js locates it as document.getElementById("orb"), so keeping
// the id means the heartbeat line can be switched on here later without touching that file.
//
// PURELY VISUAL — NO INTERACTION LIVES HERE (changed 2026-08-18). The orb is now the power switch, and its <button>
// is owned by DockBar so that BOTH faces of the centre slot (the ⏻ when stopped, the orb when running) go through
// one handler and cannot drift apart. Nesting a button inside a button is also invalid HTML, and on a phone that
// resolves in whichever way the browser feels like — the outer tap winning on one and the inner on another.
// Cycling the TTS voice moved to a row in the menu sheet, where a deliberate gesture belongs: the one thing that
// must never happen by accident on a phone in a pocket is a gesture that changes what the agent sounds like.
// ============================================================================

import { h, raw } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";

// ONE MIC INDICATOR (V2-876 P-19): the dock's mic button. The orb no longer wears a mic glyph for the mic's state —
// two indicators said the same thing (audit 2026-11-11). It wears the slashed mic only on a screen whose voice is
// ELSEWHERE (V2-792 §9), where it means «not here», not «muted». Built once, switched by CSS (the canvases beside it are
// held by reference — see DockBar.js).
const MIC_IN_ORB = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
  stroke-linejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0
  14 0"/><path d="M12 18v3"/><path class="zm-mic-slash" d="M4 4l16 16"/></svg>`;

export function OrbMini() {
  return h("div", {
    // `talking` only where the voice comes out (V2-792 §9): a screen whose voice is elsewhere receives the same
    // «speaking» events, and the agent is not talking THERE.
    class: () => "zm-orb " + store.agentState() + (store.screenState() === "speaking" ? " talking" : ""),
    // The label is the honest STATE (the wrapping button's own label says what a tap does): a screen reader on a
    // phone is often the only way to know whether anyone is on the other end.
    "aria-label": () => "zaelar: " + store.agentState(),
  },
    // Both canvases are 1:1 with their CSS box; visualizer.js handles DPR itself.
    h("canvas", { id: "orb", class: "zm-orb-c", width: "96", height: "96" }),
    h("canvas", { id: "viz", class: "zm-viz-c", width: "96", height: "96" }),
    h("div", { class: () => "zm-orb-mic" + (store.screenState() === "secondary" ? " muted" : "") },
      raw(MIC_IN_ORB)),
    // The transient "🗣 <voice>" flash after cycling the voice from the menu — the only feedback that it took.
    h("div", { class: () => "zm-vflash" + (store.voiceFlash().show ? " show" : "") }, () => store.voiceFlash().text),
  );
}

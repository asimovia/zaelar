// ============================================================================
// DockBar.js — EVERY control, at the very bottom, ARRANGED AROUND THE ORB.  The mobile counterpart of the desktop's
// «eye» (Orb.js: an arc of 7 icons above the orb) and of the TopBar.
//
// WHY BOTTOM, AND WHY THAT MATTERS FOR LAYOUT: a phone is held in one hand and the thumb reaches the bottom third.
// So this bar is the ONLY chrome with a fixed position in this shell, and its height (--dock-h) is the ONE piece of
// geometry the rest of the shell knows about: every card ends `--dock-h` above the bottom edge so the bar can never
// cover the last line of a widget. On iOS it also pads itself with env(safe-area-inset-bottom), or it would sit
// under the home indicator and every tap would be a swipe-up instead.
//
// ── THE COMPOSITION (V2-876 D-C, operator 2026-11-11): ≡ · chat · apps | ORB | mic · speaker.
//
//   ☰ menu     → store.mobileMenuOpen    processes · account · energy · settings · feedback · voice (+ the live
//                                        process count on the ☰, V2-822)
//   💬 chat    → store.chatOpen          the conversation
//   ▦ apps     → AppsPane.appsOpen       every app, full screen (feedback left for a row of the ☰ page; the wake word
//                                        for a row of Settings)
//   ◉  ORB     → the switch (below)
//   🎤 mic     → session.openMicHere / mic.toggle  opening it takes the voice to this device
//   🔊 speaker → session.openSpeakerHere / toggle  same rule
//
// The speaker sits in the dock because the voice belongs to ONE device and the hand that opens mic or speaker is what
// takes it there. The mic stays because silencing your own microphone is a PRIVACY gesture, and one that takes two
// taps is not one; the mic button is the ONE mic indicator (the orb's colour is the agent's state).
//
// THE ORB IS THE CENTRE, AND IT IS ALSO THE SWITCH (operator, 2026-08-18: «when stopped there is only the
// on/off button, and when we start it the orb appears; or we touch the orb and it stops»). One slot, two faces:
//
//   agentState() === "off"   →  a ⏻ button. Nothing else can be true about a stopped agent, so nothing else shows.
//   anything else            →  the ORB, live, and tapping it STOPS (or, mid-«pausing», cancels the stop).
//
// That is the same `!store.powerOff()` seam the desktop ⏻ uses — NOT a second one. It matters more here than
// anywhere: since V2-092 the switch is the SERVER's state, so a mobile-only power button that flipped a local
// signal would show "stopped" on the phone while the agent kept working — the exact class of lying state this
// codebase has already paid for once.
//
// THE GLYPHS ARE THE DESKTOP'S, BYTE FOR BYTE (operator: «as similar as possible to those already in the frontend of
// the UI»): MIC/CHAT/PWR are copied from `app/components/Orb.js` so an operator who knows one shell reads the other
// without learning a second vocabulary, and the host-contract test DERIVES that check from Orb.js itself. The two
// additions are MIC_OFF (the desktop only greys a muted mic, which is legible next to six icons on a big screen and
// ambiguous as a lone icon on a phone, so the slash is drawn over the SAME base glyph) and the two glyphs the
// desktop has no twin for: MENU, drawn in the same vocabulary (24-box, 2px stroke, round caps).
// ============================================================================

import { h, raw } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import * as session from "../../../app/services/session.js?v=3";
import * as api from "../../../app/services/api.js?v=2";
import * as mic from "../../../app/services/mic.js?v=1";
import { t } from "../../../app/core/i18n.js?v=1";
import { OrbMini } from "./OrbMini.js?v=3";
import * as power from "../../../app/services/power.js?v=1";
import { ProcessCount } from "../../../app/components/ProcessCount.js?v=1";
import * as consent from "./ai-consent.js?v=1";   // V2-870: in the app the voice asks first
import { appsOpen, setAppsOpen } from "./AppsPane.js?v=2";
import { APPS_ICON } from "../../../app/lib/icons.js?v=2";

const SW = `viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"`;
const MIC_ON  = `<svg ${SW}><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/></svg>`;
const MIC_OFF = `<svg ${SW}><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/><path d="M4 4l16 16"/></svg>`;
const CHAT    = `<svg ${SW}><path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.4 9.06 9.06 0 0 1-4-.9L3 21l1.9-4.5a8.38 8.38 0 0 1-.9-4A8.5 8.5 0 0 1 12.5 4 8.38 8.38 0 0 1 21 11.5z"/></svg>`;
// SPEAKER is the desktop's drawing, byte for byte (Orb.js SPK_ON/SPK_OFF); APPS is the desk's launcher glyph (lib/icons.js).
const SPK_ON  = `<svg ${SW}><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/></svg>`;
const SPK_OFF = `<svg ${SW}><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="m22 9-6 6"/><path d="m16 9 6 6"/></svg>`;
// MENU (2026-10-25, operator): the main menu is the classic three bars — a gear promised «settings» and opened the
// account, the energy and everything else; settings are now one row inside it.
const MENU    = `<svg ${SW}><path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/></svg>`;
const PWR     = `<svg ${SW}><path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/></svg>`;

// BLUE = on/live, pale GREY = off/closed. Same language as the desktop's lid icons.
const cls = (on) => "zm-ic" + (on ? " on" : " off");

// The switch, shared by BOTH faces of the centre slot (the ⏻ button and the orb) so the two can never drift apart.
// Identical to Orb.js's power handler, down to stamping the command BEFORE applying it: without that, a server
// reconciliation that went to fetch the state before this instant tears down the session just asked for (main.js).
// V2-792 §9 — switching the agent on/off and the centre tap live in ONE door both shells use
// (`app/services/power.js`). This file used to start the voice session BEFORE the server had the switch on, so the
// server refused it and the phone sat «off» over a running agent (2026-10-25 22:40:17).

export function DockBar() {
  // The wake-word state and the name are read once here, as the desktop orb does; SSE keeps them live afterwards.
  api.getSettings().then((cfg) => {
    const knob = (cfg.knobs || []).find((k) => k.key === "attention_mode");
    if (knob) store.setAttentionMode(knob.value === "wakeword" ? "smart" : knob.value);
    if (cfg.assistant_name) store.setAssistantName(cfg.assistant_name);
  }).catch(() => {});
  // Built ONCE, outside the reactive tree, because the visualiser holds this canvas by reference.
  const ORB = OrbMini();
  return h("nav", { class: "zm-dock", "aria-label": () => t("mobile.dock_label") },

    // ── LEFT of the orb: the menu, the conversation, the apps ──
    h("div", { class: "zm-side" },
      // V2-822 — the ☰ also carries the live count of RUNNING PROCESSES (ProcessCount.js, the same component and the
      // same number as the desktop's bar): the menu is the phone's processes view, so tapping the count is tapping ☰.
      h("button", {
        class: () => cls(store.mobileMenuOpen() || store.mobileSettingsOpen() || store.mobileFeedbackOpen()) + " zm-menu",
        "aria-label": () => (store.liveProcessCount() > 0
          ? t("mobile.menu_processes", { n: store.liveProcessCount() }) : t("mobile.menu")),
        onClick: () => { const v = !store.mobileMenuOpen(); store.setMobileMenuOpen(v); api.uiEvent("mobile:menu", { state: v ? "open" : "close" }); },
      }, raw(MENU), ProcessCount({ as: "span" })),

      h("button", {
        class: () => cls(store.chatOpen()),
        "aria-label": () => t("camera.chat_title"),
        onClick: () => { const v = !store.chatOpen(); store.setChatOpen(v); api.uiEvent("mobile:chat", { state: v ? "open" : "close" }); },
      }, raw(CHAT)),

      h("button", {
        class: () => cls(appsOpen()), "data-ctl": "apps",
        "aria-label": () => t("mobile.apps"),
        onClick: () => { const v = !appsOpen(); setAppsOpen(v); api.uiEvent("mobile:apps", { state: v ? "open" : "close" }); },
      }, raw(APPS_ICON)),
    ),

    // ── CENTRE: the orb, which is also the switch. Stopped → a ⏻ and nothing else; running → zaelar's face. ──
    //
    // BOTH faces are built ONCE and swapped by VISIBILITY — deliberately not `() => cond ? a : b`, which is the
    // obvious way to write this and is wrong. A reactive child function re-runs on every agentState change and
    // returns a NEW element tree, so each transition would mint a fresh OrbMini with a fresh <canvas>. main.js
    // hands `$("#orb")` to the visualiser exactly once at boot; after one re-render that reference is a DETACHED
    // node, whose clientWidth is 0, so the render loop keeps running (measured: 741 frames) and paints nothing
    // into a canvas nobody can see, while the canvas actually on screen is never drawn to. Symptom: an empty hole
    // in the middle of the dock, with no error anywhere. Measured 0 painted pixels of 9216 (2026-08-18).
    h("div", { class: "zm-centre" },
      h("button", {
        class: () => "zm-ic zm-pwr pwr-off off" + (store.screenState() === "off" ? "" : " zm-hide"),
        "aria-label": () => t("orb.power_off"),
        onClick: () => consent.gate(() => power.centreTap("dock")),
      }, raw(PWR)),
      h("button", {
        // The orb itself. `aria-label` says what a tap DOES, not what the orb is — the state is already
        // announced by OrbMini's own label, and a screen-reader user needs to know this is the stop button.
        // `zm-blocked` is V2-573: the browser is refusing to play audio, so the operator hears nothing while
        // everything else looks healthy. It rides the ORB because that is where someone who cannot hear the
        // agent looks, and tapping it (a gesture) is exactly what the unlock needs.
        class: () => "zm-orb-btn pwr-" + store.agentState() + " st-" + store.screenState()
          + (store.screenState() === "off" ? " zm-hide" : "")
          + (store.audioBlocked() ? " zm-blocked" : ""),
        // What a tap DOES on this screen: bring the voice here, or stop the agent (V2-792 §9).
        "aria-label": () => (store.screenState() === "secondary" ? t("orb.centre_secondary") : t("mobile.orb_stop")),
        onClick: () => consent.gate(() => power.centreTap("dock")),
      }, ORB),
    ),

    // ── RIGHT of the orb: the microphone (privacy, one tap) and everything else ──
    h("div", { class: "zm-side" },
      h("button", {
        class: () => cls(store.agentLive() && !store.micMuted()),
        // `data-ctl="mic"` is what the CAPTURE GLOW is scoped to, the same marker the desktop orb bar uses.
        // Without it the glow rule could only key off `.zm-ic.on`, which is ALSO the chat and dashboards
        // buttons — three buttons carrying a filter meant for one (2026-09-20 review).
        "data-ctl": "mic",
        // The icon IS the level meter (2026-08-10, same request that put the VU on the desktop mic): it scales with
        // the REAL mic RMS through a CSS custom property, so it costs no re-render. With the mic muted or the agent
        // stopped there is no effect, because there is no level — the meter can only move when we are truly hearing.
        style: { "--vu": () => (store.agentLive() && !store.micMuted() ? String(Math.min(1, store.micLevel() * 6)) : "0") },
        "aria-label": () => (store.micMuted() ? t("camera.mic_unmute") : t("camera.mic_mute")),
        // Opening the mic by hand brings the voice to this surface (session.openMicHere); closing it is local.
        onClick: () => {
          if (store.micMuted() && session.openMicHere) consent.gate(() => session.openMicHere("dock"));
          else mic.toggle("dock");
          api.uiEvent("mobile:mic", { state: store.micMuted() ? "muted" : "unmuted" });
        },
      }, () => raw(store.micMuted() ? MIC_OFF : MIC_ON)),

      // THE SPEAKER, back in the dock (operator, 2026-10-24). Opening it by hand brings the voice here, like the mic.
      h("button", {
        // Lilac only while the agent's voice really comes out of THIS screen (V2-792 §9): with the agent stopped or
        // the voice on another screen nothing is said here, whatever the toggle underneath says.
        class: () => cls(store.agentLive() && !store.botMuted()),
        "aria-label": () => (store.botMuted() ? t("orb.speaker_muted") : t("orb.speaker_unmuted")),
        onClick: () => {
          if (store.botMuted() && session.openSpeakerHere) consent.gate(() => session.openSpeakerHere("dock"));
          else session.toggleBotMute();
          api.uiEvent("mobile:speaker", { state: store.botMuted() ? "muted" : "unmuted" });
        },
      }, () => raw(store.botMuted() ? SPK_OFF : SPK_ON)),

    ),
  );
}

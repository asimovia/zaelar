// DormantVeil — ONE black veil over the whole screen for the two times this screen cannot use the agent
// (operator, 2026-11-10). Shared by both shells (desktop `system-surfaces.js`, phone `mobile-surfaces.js`); its CSS
// lives in `core/shared-surfaces.css`. It sits above every panel and the chat wall: under it nothing is usable.
//
//   · "sleep" — the engine said goodnight (`engine.sleep`, services/presence.js): it was idle and went to sleep. The
//     button wakes it the way any gesture does (`presence.reactivate` → the stream reopens with `wake=1`, which a
//     hosted edge reads as a person), and the veil stays, saying it is waiting, until the stream answers.
//   · "moved" — the voice is held by another screen (`store.remoteHeld`, services/session-lk.js). The button brings
//     it here (`session.claimVoice`); «continue here with text» lifts the veil until the voice changes hands again,
//     because the chat and the observer still work on a screen without the voice (V2-792).
//
// The agent's ⏻ is not touched by either face: a stopped agent has its own veil (PowerVeil.js).
import { h } from "../core/dom.js?v=2";
import { createSignal, createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as session from "../services/session.js?v=3";
import { reactivate } from "../services/presence.js?v=1";
import { t } from "../core/i18n.js?v=1";

/** Which face the veil shows, or "" when the screen is free. Pure: exported for the test. The engine's sleep wins —
 *  a sleeping engine has no voice for anyone, wherever it was. */
export function dormantFace(dormant, remoteHeld, powerOff, movedDismissed) {
  if (dormant && dormant.face === "sleep") return "sleep";
  if (remoteHeld && !powerOff && !movedDismissed) return "moved";
  return "";
}

export function DormantVeil() {
  const [dismissed, setDismissed] = createSignal(false);
  createEffect(() => { if (!store.remoteHeld()) setDismissed(false); });   // the next change of hands shows it again
  const face = () => dormantFace(store.dormant(), store.remoteHeld(), store.powerOff(), dismissed());
  const waking = () => face() === "sleep" && !!store.dormant().waking;
  const primary = (e) => {
    e.stopPropagation();
    if (face() === "sleep") return reactivate();
    if (session.claimVoice) session.claimVoice("veil");
  };
  const swallow = (e) => { e.stopPropagation(); };
  return h("div", {
    class: () => "dz-veil" + (face() ? " on " + face() : "") + (waking() ? " waking" : ""),
    "aria-hidden": () => (face() ? "false" : "true"),
    role: "alertdialog", "aria-live": "assertive", "aria-labelledby": "dz-title",
    onclick: swallow, ondblclick: swallow, onwheel: swallow,
  },
    h("div", { class: "dz-box" },
      h("div", { class: "dz-mark", "aria-hidden": "true" }, () => (face() === "moved" ? "⇄" : "☾")),
      h("h2", { class: "dz-title", id: "dz-title" }, () =>
        face() === "moved" ? t("dormant.moved_title") : face() === "sleep" ? t("dormant.sleep_title") : ""),
      h("p", { class: "dz-sub" }, () =>
        face() === "moved" ? t("dormant.moved_sub") : waking() ? t("dormant.waking") : face() === "sleep" ? t("dormant.sleep_sub") : ""),
      h("div", { class: "dz-actions" },
        h("button", { class: "dz-btn primary", type: "button", disabled: () => waking(), onclick: primary },
          () => (face() === "moved" ? t("dormant.use_here") : waking() ? t("dormant.waking_btn") : t("dormant.reactivate"))),
        h("button", {
          class: () => "dz-btn" + (face() === "moved" ? "" : " hidden"), type: "button",
          onclick: (e) => { e.stopPropagation(); setDismissed(true); },
        }, () => t("dormant.keep_text")),
      ),
    ),
  );
}

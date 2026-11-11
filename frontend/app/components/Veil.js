// Veil — the ONE veil for «this screen cannot use the agent» (V2-881). Both shells; CSS in `core/shared-surfaces.css`.
//
// There were two: DormantVeil (the engine asleep, the voice on another screen) and PowerVeil (the agent stopped, or in
// transit). Measured by the operator (2026-11-11): with the agent asleep he pressed ⏻ — the sleep veil lifted and the
// power veil appeared saying «the agent is stopped», and he had to press ⏻ again. Now ONE face at a time, by priority:
//
//   · pausing / off  — the agent is stopping or stopped by him (`store.agentState`). Stopped wins over asleep.
//   · sleep          — the engine said goodnight (`engine.sleep`, services/presence.js).
//   · starting       — the agent is coming up again after the first boot (the first boot has the loader).
//   · moved          — the voice is held by another screen (`store.remoteHeld`); «continue here with text» lifts it,
//                      because chat and the observer still work on a screen without the voice (V2-792).
//
// And ONE press activates everything on the screen where it was pressed (`activateHere`): it wakes the engine
// (`presence.reactivate` — the stream reopens with `wake=1`, which a hosted edge reads as a person), waits for the
// stream to answer, switches the agent on (`power.setPower`, the one power door) and brings the voice here
// (`session.claimVoice`). In that order: a power command sent to a sleeping engine is lost, and a voice claimed
// before the agent runs is refused (power.js).
import { h } from "../core/dom.js?v=2";
import { createSignal, createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as session from "../services/session.js?v=3";
import { reactivate } from "../services/presence.js?v=1";
import { setPower } from "../services/power.js?v=1";
import { t } from "../core/i18n.js?v=1";

/** Which face the veil shows, or "" when the screen is free. Pure: exported for the test. */
export function veilFace(state, dormant, remoteHeld, bootReady, movedDismissed) {
  if (state === "pausing" || state === "off") return state;
  if (dormant && dormant.face === "sleep") return "sleep";
  if (state === "starting" && bootReady) return "starting";
  if (remoteHeld && !movedDismissed) return "moved";
  return "";
}

/** Resolves once the engine is awake: the stream answered and presence.js lifted the sleep face. */
const awake = () => new Promise((resolve) => {
  let stop = null, done = false;
  stop = createEffect(() => {
    if (done || store.dormant().face === "sleep") return;
    done = true; resolve(); if (stop) stop();
  });
  if (done) stop();
});

let _busy = false;
/** The one gesture: wake the engine, switch the agent on, bring the voice here. Exported for the test. */
export async function activateHere(where = "veil") {
  if (_busy) return;
  _busy = true;
  try {
    reactivate();
    await awake();
    await setPower(false, where);
    if (session.claimVoice) await session.claimVoice(where);
  } finally { _busy = false; }
}

const MARK = { sleep: "☾", moved: "⇄", off: "⏻" };
const TITLE = { off: "veil.off_title", pausing: "veil.pausing", starting: "veil.starting",
                sleep: "dormant.sleeping", moved: "dormant.moved_title" };
const SUB = { off: "veil.off_sub", moved: "dormant.moved_sub" };
const BTN = { off: "veil.on_btn", sleep: "dormant.reactivate", moved: "dormant.use_here" };

export function Veil() {
  const [dismissed, setDismissed] = createSignal(false);
  createEffect(() => { if (!store.remoteHeld()) setDismissed(false); });   // the next change of hands shows it again
  const face = () => veilFace(store.agentState(), store.dormant(), store.remoteHeld(), store.bootReady(), dismissed());
  const waking = () => !!face() && !!store.dormant().waking;
  const swallow = (e) => { e.stopPropagation(); };
  return h("div", {
    class: () => "zv" + (face() ? " on " + face() : "") + (waking() ? " waking" : ""),
    "aria-hidden": () => (face() ? "false" : "true"),
    role: "alertdialog", "aria-live": "assertive", "aria-labelledby": "zv-title",
    onpointerdown: swallow, onclick: (e) => { e.stopPropagation(); if (face() === "sleep") activateHere("veil"); }, ondblclick: swallow, onwheel: swallow,
  },
    h("div", { class: "zv-box" },
      h("div", { class: "zv-mark", "aria-hidden": "true" }, () => MARK[face()] || ""),
      h("div", { class: "zv-zs", "aria-hidden": "true" }, h("span", {}, "Z"), h("span", {}, "Z"), h("span", {}, "Z")),
      h("h2", { class: "zv-title", id: "zv-title" }, () => (TITLE[face()] ? t(TITLE[face()]) : "")),
      h("p", { class: "zv-sub" }, () => (waking() ? t("dormant.waking") : SUB[face()] ? t(SUB[face()]) : "")),
      h("div", { class: "zv-actions" },
        h("button", {
          class: () => "zv-btn primary" + (BTN[face()] ? "" : " hidden"), type: "button", disabled: () => waking(),
          onclick: (e) => { e.stopPropagation(); activateHere("veil"); },
        }, () => (waking() ? t("dormant.waking_btn") : BTN[face()] ? t(BTN[face()]) : "")),
        h("button", {
          class: () => "zv-btn" + (face() === "moved" ? "" : " hidden"), type: "button",
          onclick: (e) => { e.stopPropagation(); setDismissed(true); },
        }, () => t("dormant.keep_text")),
      ),
    ),
  );
}

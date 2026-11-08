// PowerVeil — the desktop is LOCKED while the agent is not running (operator, 2026-11-08).
//
// With ⏻ off the cards stayed fully interactive: a tap on the music card's ▶ was refused by the server
// (`producers.gate` → `agent_stopped`) and nothing on screen said so — the card looked alive over a stopped agent,
// half on and half off. The veil makes the state impossible to miss: a shaded layer over the widget stage that
// swallows every click, a line that says what is going on, and the one way out (⏻ on, through `power.setPower`,
// the same door as the orb). The orb, the bottom rail and the panels sit ABOVE it on purpose — they are how the
// operator switches the agent back on or reads what happened.
//
// It shows for `off` and for the two transits (`pausing`, `starting` once the first boot is done — the first boot
// has its own overlay). `stalled` is not covered: a fallen agent has its own alarm and must stay inspectable, and
// `remote` is a RUNNING agent whose voice lives on another screen.
import { h } from "../core/dom.js?v=2";
import * as store from "../core/store.js?v=2";
import { setPower } from "../services/power.js?v=1";
import { t } from "../core/i18n.js?v=1";

/** Which face the veil shows for an agent state, or "" when the desktop is free. Exported for the test. */
export function veilFace(state, bootReady) {
  if (state === "off") return "off";
  if (state === "pausing") return "pausing";
  if (state === "starting" && bootReady) return "starting";
  return "";
}

export function PowerVeil() {
  const face = () => veilFace(store.agentState(), store.bootReady());
  const swallow = (e) => { e.stopPropagation(); };
  return h("div", {
    class: () => "power-veil" + (face() ? " on" : ""),
    "aria-hidden": () => (face() ? "false" : "true"),
    role: "status",
    onpointerdown: swallow, onclick: swallow, ondblclick: swallow, onwheel: swallow,
  },
    h("div", { class: "power-veil-box" },
      h("div", { class: "power-veil-title" }, () => {
        const f = face();
        return f === "off" ? t("veil.off_title") : f === "pausing" ? t("veil.pausing") : f === "starting" ? t("veil.starting") : "";
      }),
      h("div", { class: "power-veil-sub" }, () => (face() === "off" ? t("veil.off_sub") : "")),
      h("button", {
        class: () => "power-veil-btn" + (face() === "off" ? "" : " hidden"),
        type: "button",
        onclick: (e) => { e.stopPropagation(); setPower(false, "veil"); },
      }, "⏻ ", () => t("veil.on_btn")),
    ),
  );
}

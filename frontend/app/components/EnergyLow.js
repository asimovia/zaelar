// EnergyLow — less than 5 % of the cycle's Energy left, said BEFORE the agent stops (operator, 2026-11-19).
//
// Until then the first word about Energy was the out-of-energy notice, when the agent had already stopped — in the
// middle of an errand. This is the warning before it: a small card in a corner, never a modal, so it does not
// interfere with what he is doing. It says what will happen at zero and that nothing is lost: memory and everything
// of his stay; the agent only has no Energy to talk or keep working. Closable; closed, it stays closed until the
// balance climbs back above the line (a top-up) and drops under it again.
//
// SHARED by both shells (desktop `system-surfaces.js`, phone `mobile-surfaces.js`); CSS in `core/shared-surfaces.css`.
import { h } from "../core/dom.js?v=2";
import { createSignal, createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";
import * as api from "../services/api.js?v=2";
import { accountLink } from "../core/account-link.js?v=2";
import { inNativeApp } from "../core/native.js?v=1";   // V2-870: no purchase path inside the app

//: The share of the cycle under which the warning shows.
export const LOW_SHARE = 0.05;

/** Whether the battery is under the line and not yet empty. Pure: a known cloud balance, a cycle to measure it by,
 *  and no stop already in place (the out-of-energy notice speaks then). */
export function lowEnergy(e) {
  const x = e || {};
  const bal = Number(x.balance), cap = Number(x.capacity);
  if (!x.cloud || !x.known || x.exhausted || !(cap > 0) || !Number.isFinite(bal)) return false;
  return bal > 0 && bal < cap * LOW_SHARE;
}

export function EnergyLow() {
  const [closed, setClosed] = createSignal(false);
  const low = () => lowEnergy(store.energy());
  createEffect(() => { if (!low()) setClosed(false); });       // back above the line: the next drop warns again
  const close = () => { api.uiEvent("energy:low_close", {}); setClosed(true); };
  return h("div", { class: () => "en-low" + (low() && !closed() ? " on" : ""), role: "status", "aria-live": "polite" },
    h("div", { class: "en-low-mark", "aria-hidden": "true" }, "⚡"),
    h("div", { class: "en-low-text" },
      h("strong", { class: "en-low-title" }, () => t("energy.low.title")),
      h("p", { class: "en-low-body" }, () => t("energy.low.body")),
      h("a", {
        class: "en-low-link",
        href: () => accountLink(store.accountUrl(), inNativeApp() ? "" : "buy") || null,
        hidden: () => !store.accountUrl(),
        target: "_blank", rel: "noopener",
        onClick: () => api.uiEvent("energy:top_up", { reason: "low" }),
      }, () => t(inNativeApp() ? "energy.out.account" : "energy.out.top_up")),
    ),
    h("button", { class: "en-low-x", type: "button", "aria-label": () => t("energy.out.close"), onClick: close }, "×"),
  );
}

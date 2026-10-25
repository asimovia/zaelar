// ============================================================================
// EnergyLine.js — the Energy left, ALWAYS on screen on a phone (2026-10-25, operator: «en la versión mobile echo de
// menos en algún punto que se vea la energía»).
//
// The desktop draws a battery in its top bar; this shell has no top bar — every pixel above the dock belongs to the
// card. So the balance is a thin line along the TOP edge, under the notch: the whole width is this cycle's Energy
// (`capacity`), the lit part is what is left, the same proportion the desktop battery lights. It turns amber under a
// fifth and red when spent, so running out is never a surprise. The NUMBER lives one tap away, in the ☰ menu's Energy
// row, which also opens the top-up.
//
// Cloud only — on self-host there is no balance (`cloud:false`) and nothing is drawn. Not known yet (the machine still
// booting) draws nothing either: an empty line would read as «you are out», which is the one thing it must not say.
// The line takes no touches (`pointer-events:none`): the card header under it is where a one-finger swipe pages.
// ============================================================================

import { h } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";

/** Balance and capacity → {pct, level} or null. PURE — exported for the test. */
export function level(e) {
  if (!e || !e.cloud || !e.known) return null;
  const cap = Number(e.capacity), bal = Math.max(0, Number(e.balance) || 0);
  if (!Number.isFinite(cap) || cap <= 0) return null;
  const pct = Math.max(0, Math.min(100, (bal / cap) * 100));
  return { pct, level: bal <= 0 ? "out" : pct < 20 ? "low" : "ok" };
}

export function EnergyLine() {
  const lv = () => level(store.energy());
  return h("div", { class: () => "zm-eline" + (lv() ? " show " + lv().level : ""), "aria-hidden": "true" },
    h("i", { style: { width: () => (lv() ? lv().pct.toFixed(1) + "%" : "0%") } }));
}

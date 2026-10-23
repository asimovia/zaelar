// EnergyGauge — THE BATTERY. How much Energy the account has left, drawn to the LEFT of the top bar's controls,
// straight on the background.
//
// Born from a concrete complaint (operator, 2026-08-13): the agent ran out of energy halfway through a task and learned it
// from a banner, having NEVER seen how much remained. It is the same kind of failure as a down agent painted as alive:
// a state that can strand you must be VISIBLE beforehand, not announced afterward.
//
// CLOUD ONLY. On self-host, `/api/energy` returns `cloud:false` and nothing is rendered here — there is no balance to spend;
// the user pays for their own APIs.
//
// ── THE SCALE (2026-10-24) ───────────────────────────────────────────────────────────────────────────────────────────
// The SAME number of bars for every account — more, and thinner, on a wider screen — and each bar is worth the same:
// the gauge's full scale (`plan.scale`, the biggest cycle there is) divided by the bars. So:
//   · the bars of THIS cycle are `capacity / per`: a small cycle owns part of the gauge, the biggest owns all of it;
//   · of those, the lit ones are `balance / per` — «what the cycle gave you minus what you spent», nothing else;
//   · spent bars stay as grey boxes with a firmer grey edge (it reads as a battery running down, not as a shorter
//     list), and bars beyond this cycle are faint placeholders.
// The colour is the plan's tier (`plan.tier`), so a bigger plan is visibly a bigger plan. Without `plan.scale` (an
// older control plane) the cycle fills the gauge. Nothing here knows a price.
import { h } from "../core/dom.js?v=2";
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { accountLink } from "../core/account-link.js?v=1";

/** Bars for a screen width: enough to read as detail, never enough to crowd a narrow window. */
export function barsFor(width) {
  const w = Number(width) || 0;
  return w >= 1280 ? 30 : w >= 900 ? 20 : 12;
}

const TIERS = 5;                  // colour classes eg-tier0 … eg-tier4 in styles.css

/** Balance + capacity (+ the plan's gauge facts) → how to draw the battery. PURE: the only piece containing rules, so
 * it can be tested without the DOM. Returns `null` when there is nothing to render. */
export function scale(balance, capacity, plan, width) {
  const cap = Number(capacity);
  if (!Number.isFinite(cap) || cap <= 0) return null;
  const bars = barsFor(width);
  const full = Math.max(cap, Number(plan && plan.scale) || 0);
  const per = full / bars;
  const own = Math.min(bars, Math.max(1, Math.round(cap / per)));
  const bal = Math.max(0, Number.isFinite(Number(balance)) ? Number(balance) : 0);
  // Any Energy left lights at least one bar: an almost-empty account is not an empty one.
  const lit = bal <= 0 ? 0 : Math.min(own, Math.max(1, Math.round(bal / per)));
  const tier = Math.min(TIERS - 1, Math.max(0, Math.round(Number(plan && plan.tier) || 0)));
  return { bars, per, own, lit, tier };
}

// When an account url is configured the battery is a LINK to the account page's energy section (new tab, keyboard
// reachable because it is a real <a href>), with a translated label. Without one it is a plain <div>.
function shell(cls, title, ticks) {
  const href = accountLink(store.accountUrl(), "buy");
  const props = { class: cls, title };
  if (href) Object.assign(props, { href, target: "_blank", rel: "noopener", "aria-label": t("energy.buy_aria") });
  return h(href ? "a" : "div", props, ...ticks);
}

export function EnergyGauge() {
  return () => {
    const e = store.energy() || {};
    if (!e.cloud) return null;                       // self-host: there is no battery to render
    const width = typeof window !== "undefined" ? window.innerWidth : 1280;
    // NOT KNOWING AND BEING AT ZERO MUST NOT LOOK THE SAME: until the first lease answers there is no balance, so the
    // battery is all placeholders with its notice — never red, never «you are out».
    if (!e.known) {
      return shell("eg eg-unknown", t("energy.unknown"),
        Array.from({ length: barsFor(width) }, () => h("i", { class: "eg-t eg-free" })));
    }
    const s = scale(e.balance, e.capacity, e.plan, width);
    if (!s) return null;
    const bal = Math.max(0, Math.round(Number(e.balance) || 0));
    const name = e.plan && e.plan.name ? " · " + e.plan.name : "";
    const tip = (s.lit ? t("energy.tip") : t("energy.empty"))
      .replace("{balance}", String(bal))
      .replace("{cycle}", String(Math.round(Number(e.capacity) || 0)))
      .replace("{plan}", name);
    return shell("eg eg-tier" + s.tier + (s.lit ? "" : " eg-dead"), tip,
      Array.from({ length: s.bars }, (_, i) =>
        h("i", { class: "eg-t " + (i < s.lit ? "eg-on" : i < s.own ? "eg-spent" : "eg-free") })));
  };
}

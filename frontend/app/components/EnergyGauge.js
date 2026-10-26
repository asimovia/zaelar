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
// The gauge is THIS account's plan: the whole row is what the current cycle made available (`capacity`), and the lit
// bars are what is left of it, in proportion — «the cycle's Energy minus what you spent», nothing else. The SAME number
// of bars for every account (more, and thinner, on a wider screen); the plan shows in the COLOUR (`plan.tier`).
// Spent bars stay as grey boxes with a firmer grey edge, so it reads as a battery running down, not a shorter list.
// The lit bars sit at the RIGHT end, next to the box, and the battery empties from the left (the operator, 2026-10-26).
// (A first version drew every plan against the biggest one; the operator's own Free cycle then lit 1 bar of 30 with
// 394 of 398 left — it did not represent his Energy.) Nothing here knows a price.
import { h } from "../core/dom.js?v=2";
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { accountLink } from "../core/account-link.js?v=1";

/** Bars for a screen width. On a wide screen each bar is 2% of the cycle (50 bars, the operator's ask: «50 for 50%»),
 * 4% on a medium one and 5% on a narrow one — enough detail to read the battery, never enough to crowd the window. */
export function barsFor(width) {
  const w = Number(width) || 0;
  return w >= 1280 ? 50 : w >= 900 ? 25 : 20;
}

const TIERS = 5;                  // colour classes eg-tier0 … eg-tier4 in styles.css

/** Balance + capacity (+ the plan's gauge facts) → how to draw the battery. PURE: the only piece containing rules, so
 * it can be tested without the DOM. Returns `null` when there is nothing to render. */
export function scale(balance, capacity, plan, width) {
  const cap = Number(capacity);
  if (!Number.isFinite(cap) || cap <= 0) return null;
  const bars = barsFor(width);
  const per = cap / bars;
  const own = bars;
  const bal = Math.max(0, Number.isFinite(Number(balance)) ? Number(balance) : 0);
  // Any Energy left lights at least one bar: an almost-empty account is not an empty one.
  const lit = bal <= 0 ? 0 : Math.min(bars, Math.max(1, Math.round(bal / per)));
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
        h("i", { class: "eg-t " + (i >= s.bars - s.lit ? "eg-on" : i >= s.bars - s.own ? "eg-spent" : "eg-free") })));
  };
}

// Nutrition — meals by photo or by saying them, calories and macros, the day's balance and the weight log (V2-899).
// Five screens on one card: Today (balance + capture + meals), Weight, Coach (a restaurant menu), Evaluation (the
// week) and Profile (where the targets come from). Photos go up through ctx.upload into this app's own data dir;
// widget.js never touches the network. After every paint the card says what it shows (ctx.state, V2-884).

import { S, adoptOrder, go } from "./js/state.js";
import { bindLang, h, injectStyles, tt } from "./js/ui.js";
import { todayScreen } from "./js/today.js";
import { weightScreen } from "./js/weight.js";
import { coachScreen, evaluationScreen } from "./js/coach.js";
import { profileScreen } from "./js/profile.js";

const SCREENS = () => [
  ["today", tt("tab_today", null, "Today")], ["weight", tt("tab_weight", null, "Weight")],
  ["coach", tt("tab_coach", null, "Coach")], ["evaluation", tt("tab_evaluation", null, "Evaluation")],
  ["profile", tt("tab_profile", null, "Profile")],
];

function nav() {
  const n = h("div", "nu-nav hb-tabs");
  n.setAttribute("role", "tablist");
  for (const [key, label] of SCREENS()) {
    const b = h("button", "hb-tab" + (S.screen === key ? " is-on" : ""), label);
    b.type = "button";
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", S.screen === key ? "true" : "false");
    b.onclick = () => { if (S.screen !== key) { go(key, key === "today" ? S.day : undefined); S.repaint(); } };
    n.appendChild(b);
  }
  return n;
}

export function render(el, data, ctx) {
  bindLang(ctx);
  injectStyles();
  const d = data || {};
  adoptOrder(d.view);
  S.repaint = () => { if (el.isConnected !== false) render(el, d, ctx); };
  el.className = "hb-nutrition";
  el.textContent = "";
  el.appendChild(nav());
  if (d.error) el.appendChild(h("div", "nu-warn", tt("store_error", null, "The nutrition data could not be read.")));
  let shown = { day: "", meal: "", pending: 0 };
  try {
    if (S.screen === "weight") weightScreen(el, d, ctx);
    else if (S.screen === "coach") coachScreen(el, d, ctx);
    else if (S.screen === "evaluation") evaluationScreen(el, d, ctx);
    else if (S.screen === "profile") profileScreen(el, d, ctx);
    else { S.screen = "today"; shown = todayScreen(el, d, ctx); }
  } catch (e) {
    el.appendChild(h("div", "nu-warn", tt("render_error", null, "This screen could not be drawn.")));
  }
  reportShown(ctx, d, shown);
}

// V2-884 — what the face shows, said through the host's one door after every paint, with the revision it applied.
function reportShown(ctx, d, shown) {
  if (!ctx || typeof ctx.state !== "function") return;
  const today = (d.days && d.days.length) ? d.days[d.days.length - 1].date : "";
  const day = S.screen === "today" && shown.day && shown.day !== today ? shown.day : "";
  try {
    Promise.resolve(ctx.state({ screen: S.screen, day, meal: S.screen === "today" ? (shown.meal || "") : "",
      pending: Math.min(50, shown.pending || 0) }, { applied: true, of: d })).catch(() => {});
  } catch (_) {}
}

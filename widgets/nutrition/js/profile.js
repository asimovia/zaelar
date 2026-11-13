// Nutrition — the PROFILE screen: what the daily targets come from, and the targets they give.

import { S, repaint } from "./state.js";
import { btn, field, fmtNum, h, numIn, parseDecimal, select, tt } from "./ui.js";

const NUMS = () => [
  ["weight_kg", tt("weight_kg", null, "Weight kg")], ["height_cm", tt("height_cm", null, "Height cm")], ["age", tt("age", null, "Age")],
  ["surplus_pct", tt("surplus_pct", null, "Surplus / deficit %")], ["protein_per_kg", tt("protein_per_kg", null, "Protein g per kg")],
  ["target_weight_kg", tt("target_weight_kg", null, "Target weight kg")], ["target_calories", tt("target_calories", null, "Fixed kcal target")],
  ["target_protein_g", tt("target_protein_g", null, "Fixed protein target g")],
];

export function profileScreen(root, d, ctx) {
  const prof = d.profile || {}, t = d.targets || {};
  const sum = h("div", "nu-panel");
  sum.appendChild(h("h4", null, tt("your_targets", null, "Your daily targets")));
  const big = h("div", "nu-big");
  big.appendChild(h("b", null, fmtNum(t.calories) + " kcal"));
  big.appendChild(h("span", null, tt("protein_target", { n: fmtNum(t.protein_g) }, "{n} g protein")));
  sum.appendChild(big);
  sum.appendChild(h("div", "nu-note", t.calories_set_by_hand ? tt("kcal_by_hand", null, "Calories fixed by hand.")
    : tt("tdee_formula", { n: fmtNum(t.tdee) }, "Maintenance ~{n} kcal (Mifflin-St Jeor × 1.55), adjusted for your goal.")));
  root.appendChild(sum);

  const p = h("div", "nu-panel");
  p.appendChild(h("h4", null, tt("profile", null, "Profile")));
  const form = h("div", "nu-form"), ins = {};
  ins.goal = select([["gain", tt("goal_gain", null, "Gain muscle")], ["lose", tt("goal_lose", null, "Lose fat")],
    ["maintain", tt("goal_maintain", null, "Maintain")]], prof.goal || "gain");
  form.appendChild(field(tt("goal", null, "Goal"), ins.goal));
  ins.sex = select([["unknown", tt("sex_unknown", null, "Not said")], ["male", tt("sex_male", null, "Male")],
    ["female", tt("sex_female", null, "Female")]], prof.sex || "unknown");
  form.appendChild(field(tt("sex", null, "Sex (for the formula)"), ins.sex));
  for (const [k, label] of NUMS()) { ins[k] = numIn(prof[k]); form.appendChild(field(label, ins[k])); }
  p.appendChild(form);
  p.appendChild(h("div", "nu-note", tt("profile_hint", null, "Leave a fixed target empty to use the formula. Your weight follows your last weigh-in.")));
  const row = h("div", "nu-row");
  row.appendChild(h("span", "nu-grow"));
  row.appendChild(btn("hb-btn--primary", tt("save", null, "Save"), async () => {
    const pl = { goal: ins.goal.value, sex: ins.sex.value };
    for (const [k] of NUMS()) {
      const raw = ins[k].value.trim(), v = parseDecimal(raw);
      if (raw === "" && prof[k] != null) pl[k] = null;
      else if (v != null && v !== prof[k]) pl[k] = v;
    }
    const r = await ctx.action("set_profile", pl);
    S.error = r && r.invalid && r.invalid.length ? tt("invalid_fields", { f: r.invalid.join(", ") }, "Check: {f}") : "";
    repaint();
  }));
  p.appendChild(row);
  if (S.error) p.appendChild(h("div", "nu-warn", S.error));
  root.appendChild(p);
}

// Gym — the other screens: program choice, my gym (equipment + preferences), the trainer's plan, the program and its
// versions, a session's summary, an exercise's history and the manual log.
import { tt, loc, txt, btn, panel, img, dayLabel, duration, ymd, UI, go, act } from "./util.js";
import { planLabel, statusLabel } from "./home.js";

export function onboarding(root, data, ctx) {
  root.appendChild(txt("div", "gy-day-name", tt("choose_program", null, "Choose a program")));
  root.appendChild(txt("div", "gy-muted", tt("choose_hint", null, "Start with one. Later it adapts to your gym.")));
  const grid = txt("div", "gy-programs");
  for (const p of data.programs || []) {
    const c = txt("button", "hb-card hb-card--interactive gy-program");
    c.type = "button";
    c.appendChild(txt("div", "gy-ex-name", loc(p.name)));
    c.appendChild(txt("div", "gy-muted", loc(p.summary)));
    c.appendChild(txt("div", "gy-muted", tt("days_week", { n: p.days_per_week }, "{n} days a week") + " · " + loc(p.level)));
    c.onclick = () => act(ctx, "select_program", { program: p.key });
    grid.appendChild(c);
  }
  root.appendChild(grid);
}

const EQUIPMENT = ["dumbbells", "barbells", "squat_rack", "adjustable_bench", "leg_machines", "cables", "cardio", "functional", "pullup_bar"];
function equipLabel(k) {
  return ({ dumbbells: tt("eq_dumbbells", null, "Dumbbells"), barbells: tt("eq_barbells", null, "Olympic barbell + plates"),
    squat_rack: tt("eq_squat_rack", null, "Squat rack"), adjustable_bench: tt("eq_adjustable_bench", null, "Adjustable bench"),
    leg_machines: tt("eq_leg_machines", null, "Leg machines"), cables: tt("eq_cables", null, "Cables / pulleys"),
    cardio: tt("eq_cardio", null, "Cardio (treadmill · rower · bike)"), functional: tt("eq_functional", null, "Functional area"),
    pullup_bar: tt("eq_pullup_bar", null, "Pull-up bar") })[k] || k;
}

export function config(root, data, ctx) {
  const eq = Object.assign({}, data.equipment || {});
  const p1 = panel();
  p1.appendChild(txt("div", "hb-panel-title", tt("your_gym", null, "Your gym")));
  p1.appendChild(txt("div", "gy-muted", tt("your_gym_hint", null, "Tick what you have. The plan adapts to it.")));
  const grid = txt("div", "gy-equip");
  for (const k of EQUIPMENT) {
    const b = txt("button", "hb-card hb-card--interactive gy-equip-item" + (eq[k] ? " is-selected" : ""), equipLabel(k));
    b.type = "button"; b.setAttribute("aria-pressed", eq[k] ? "true" : "false");
    b.onclick = () => { eq[k] = !eq[k]; b.classList.toggle("is-selected", eq[k]); b.setAttribute("aria-pressed", eq[k] ? "true" : "false"); };
    grid.appendChild(b);
  }
  p1.appendChild(grid);
  root.appendChild(p1);
  const p2 = panel();
  p2.appendChild(txt("div", "hb-panel-title", tt("prefs", null, "Gym preferences")));
  p2.appendChild(txt("div", "gy-muted", tt("prefs_hint", null, "Free text the trainer respects: style, available weights, exercises to avoid.")));
  const ta = txt("textarea", "hb-textarea gy-textarea");
  ta.rows = 6; ta.value = data.preferences || ""; ta.placeholder = tt("prefs_ph", null, "Style, preferred exercises, exercises to avoid, weights…");
  p2.appendChild(ta);
  const f = txt("div", "hb-field");
  f.appendChild(txt("label", "hb-label", tt("age", null, "Age (for heart-rate zones)")));
  const age = txt("input", "hb-input gy-num");
  age.type = "number"; age.min = "10"; age.max = "100"; age.value = data.age == null ? "" : String(data.age);
  f.appendChild(age);
  p2.appendChild(f);
  root.appendChild(p2);
  root.appendChild(btn(tt("save", null, "✓ Save"), "primary", async () => {
    const r = await act(ctx, "configure", { equipment: eq, preferences: ta.value, age: age.value === "" ? null : Number(age.value) });
    if (r && r.ok) go("home", null, ctx);
  }, "gy-cta"));
}

export function planner(root, data, ctx) {
  root.appendChild(txt("div", "gy-muted", tt("planner_hint", null, "The next workouts the trainer proposes from your history.")));
  if ((data.plan || []).length) {
    for (const d of data.plan) {
      const c = panel();
      c.appendChild(txt("div", "gy-muted", dayLabel(d.date)));
      c.appendChild(txt("div", "gy-ex-name", planLabel(d, data)));
      if (d.reason) c.appendChild(txt("div", "gy-muted", d.reason));
      root.appendChild(c);
    }
  } else {
    root.appendChild(txt("div", "hb-empty-state gy-center", data.coach && data.coach.available
      ? tt("no_plan", null, "No plan yet.")
      : tt("no_plan_yet", null, "The trainer is not available yet: today's day follows your program's rotation.")));
  }
  root.appendChild(btn(tt("regenerate", null, "Regenerate plan"), "secondary", () => act(ctx, "refresh_plan", {})));
}

export function programView(root, data, ctx) {
  const p = data.program || {};
  const c = panel();
  c.appendChild(txt("div", "gy-day-name", loc(p.name)));
  c.appendChild(txt("div", "gy-muted", loc(p.summary)));
  const days = txt("div", "gy-muted", (p.schedule || []).map((k) => loc((p.day_names || {})[k]) || k).join(" → "));
  c.appendChild(days);
  for (const ph of p.phases || []) {
    const r = txt("div", "hb-card gy-phase" + (p.phase && loc(p.phase.name) === loc(ph.name) ? " is-selected" : ""));
    r.appendChild(txt("div", "gy-ex-name", loc(ph.name) + (ph.days ? " · " + tt("n_sessions", { n: ph.days }, "{n} sessions") : "")));
    r.appendChild(txt("div", "gy-muted", loc(ph.intensity)));
    if (ph.note) r.appendChild(txt("div", "gy-muted", loc(ph.note)));
    c.appendChild(r);
  }
  c.appendChild(txt("div", "gy-muted", tt("done_count", { n: p.done_count || 0 }, "{n} complete sessions")));
  root.appendChild(c);
  const v = panel();
  v.appendChild(txt("div", "hb-panel-title", tt("versions", null, "Plan versions")));
  for (const x of (p.versions || []).slice().reverse()) {
    const row = txt("div", "gy-version" + (x.version === p.version ? " is-current" : ""));
    row.appendChild(txt("strong", null, "v" + x.version));
    row.appendChild(txt("span", "gy-muted", (x.at ? dayLabel(ymd(new Date(x.at)), { day: "numeric", month: "short", year: "numeric" }) : "")
      + " · " + (x.reason === "select" ? tt("reason_select", null, "program chosen") : String(x.reason || ""))));
    v.appendChild(row);
  }
  root.appendChild(v);
  const others = (data.programs || []).filter((x) => x.key !== p.key);
  if (others.length) {
    const o = panel();
    o.appendChild(txt("div", "hb-panel-title", tt("change_program", null, "Change program")));
    for (const x of others) o.appendChild(btn(loc(x.name), "secondary", () => act(ctx, "select_program", { program: x.key })));
    root.appendChild(o);
  }
}

export function summary(root, data, ctx) {
  const s = (data.sessions || []).find((x) => String(x.id) === String(UI.arg));
  if (!s) { root.appendChild(txt("div", "hb-empty-state", tt("session_gone", null, "This workout is no longer here."))); return; }
  root.appendChild(txt("div", "gy-muted", dayLabel(s.date)));
  const hero = panel();
  hero.appendChild(txt("div", "gy-day-name", loc(s.day_name)));
  const stats = txt("div", "gy-stats");
  const st = (label, val) => { const b = txt("div", "hb-card gy-stat"); b.appendChild(txt("div", "gy-muted", label)); b.appendChild(txt("div", "gy-target-val", val)); return b; };
  stats.appendChild(st(tt("duration", null, "Duration"), duration(s.duration_s)));
  stats.appendChild(st(tt("calories", null, "Calories (est.)"), s.kcal != null ? "≈ " + s.kcal + " kcal" : "—"));
  stats.appendChild(st(tt("volume", null, "Volume"), (s.volume_kg || 0) + " kg"));
  stats.appendChild(st(tt("sets", null, "Sets"), String(s.sets_count || 0)));
  if (s.hr_avg) stats.appendChild(st(tt("hr_avg", null, "Avg heart rate"), s.hr_avg + " · " + tt("max", null, "max") + " " + (s.hr_max || "—")));
  hero.appendChild(stats);
  hero.appendChild(txt("div", "gy-muted", tt("status", { s: statusLabel(s.status) }, "Status: {s}")
    + (s.version ? " · v" + s.version : "") + (s.source === "manual" ? " · " + tt("manual", null, "logged by hand") : "")));
  if (s.notes) hero.appendChild(txt("div", "gy-muted", tt("notes", { n: s.notes }, "Notes: {n}")));
  root.appendChild(hero);
  if (!(s.exercises || []).length) root.appendChild(txt("div", "gy-muted", tt("no_sets", null, "No sets recorded in this workout.")));
  for (const g of s.exercises || []) {
    const c = panel("gy-sum-ex");
    const h = txt("button", "gy-sum-head");
    h.type = "button";
    const im = img(data, g.key, "gy-thumb", loc(g.name));
    if (im) h.appendChild(im);
    h.appendChild(txt("span", "gy-ex-label", g.label + ")"));
    h.appendChild(txt("span", "gy-ex-name", loc(g.name)));
    h.onclick = () => go("exercise", g.key || loc(g.name), ctx);
    c.appendChild(h);
    for (const x of g.sets) {
      const r = txt("div", "gy-sum-set");
      r.appendChild(txt("span", "gy-muted", x.label));
      r.appendChild(txt("strong", null, x.reps == null ? "—" : String(x.reps)));
      r.appendChild(txt("span", "gy-muted", tt("reps", null, "reps")));
      if (x.weight_kg != null) r.appendChild(txt("span", null, "× " + x.weight_kg + " kg"));
      if (x.rir != null) r.appendChild(txt("span", "gy-muted", "RIR " + x.rir));
      c.appendChild(r);
    }
    root.appendChild(c);
  }
  const ed = panel();
  ed.appendChild(txt("div", "hb-panel-title", tt("edit_title", null, "Change this workout")));
  ed.appendChild(txt("div", "gy-muted", tt("edit_hint", null, "Say or write it with the labels: «replace E1 with bench press, 3 sets of 10 at 50 kg» · «delete the last set of E2».")));
  const ta = txt("textarea", "hb-textarea gy-textarea");
  ta.rows = 3; ta.placeholder = tt("edit_ph", null, "What to change…");
  ed.appendChild(ta);
  ed.appendChild(btn(tt("apply", null, "Apply"), "secondary", () => { if (ta.value.trim()) act(ctx, "edit_session", { sessionId: String(s.id), instruction: ta.value.trim() }); }));
  root.appendChild(ed);
  root.appendChild(btn(UI.confirmDel === "sum" ? tt("tap_again_delete", null, "Tap again to delete") : tt("delete_workout", null, "Delete this workout"),
    "danger", () => {
      if (UI.confirmDel === "sum") { UI.confirmDel = null; act(ctx, "delete_session", { sessionId: String(s.id) }).then((r) => { if (r && r.ok) go("calendar", null, ctx); }); }
      else { UI.confirmDel = "sum"; if (UI.repaint) UI.repaint(); }
    }));
}

export function exerciseHistory(root, data, ctx) {
  const key = String(UI.arg || "");
  const e = (data.exercises || {})[key];
  const name = e ? loc(e.name) : key;
  const head = panel();
  const im = img(data, key, "gy-hero", name);
  if (im) head.appendChild(im);
  head.appendChild(txt("div", "gy-day-name", name));
  const lw = (data.last_weights || {})[key];
  if (lw) head.appendChild(txt("div", "gy-muted", tt("last_weight", { w: lw.weight_kg }, "Last weight: {w} kg")));
  root.appendChild(head);
  let any = false, best = null;
  for (const s of data.sessions || []) {
    const g = (s.exercises || []).find((x) => (x.key || loc(x.name)) === key);
    if (!g) continue;
    any = true;
    const r = txt("div", "gy-hist-row");
    r.appendChild(txt("span", "gy-muted", dayLabel(s.date, { day: "numeric", month: "short" })));
    r.appendChild(txt("span", null, g.sets.map((x) => (x.reps ?? "—") + (x.weight_kg != null ? "×" + x.weight_kg : "")).join("  ")));
    for (const x of g.sets) if (x.weight_kg != null && (best == null || x.weight_kg > best)) best = x.weight_kg;
    root.appendChild(r);
  }
  if (best != null) head.appendChild(txt("div", "gy-muted", tt("best", { w: best }, "Heaviest: {w} kg")));
  if (!any) root.appendChild(txt("div", "hb-empty-state", tt("no_history", null, "No sets of this exercise yet.")));
}

export function logView(root, data, ctx) {
  if (!UI.logRows) UI.logRows = [{ name: "", sets: 3, reps: 10, kg: "" }];
  if (!UI.logDate) UI.logDate = data.today || ymd(new Date());
  const p = panel();
  p.appendChild(txt("div", "hb-panel-title", tt("log_title", null, "Log a workout")));
  p.appendChild(txt("div", "gy-muted", tt("log_hint", null, "A workout done without the guided session. You can also just tell the agent: «yesterday 4×10 dumbbell bench at 20 kg».")));
  const f1 = txt("div", "gy-row");
  const date = txt("input", "hb-input"); date.type = "date"; date.value = UI.logDate;
  date.onchange = () => { UI.logDate = date.value; };
  f1.appendChild(date);
  const day = txt("select", "hb-select");
  const days = (data.program || {}).day_names || {};
  for (const k of Object.keys(days)) { const o = txt("option", null, loc(days[k])); o.value = k; if (UI.logDay === k) o.selected = true; day.appendChild(o); }
  day.onchange = () => { UI.logDay = day.value; };
  if (!UI.logDay) UI.logDay = day.value || null;
  f1.appendChild(day);
  p.appendChild(f1);
  const list = txt("datalist"); list.id = "gy-ex-names";
  for (const k of Object.keys(data.exercises || {})) { const o = txt("option"); o.value = loc(data.exercises[k].name); list.appendChild(o); }
  p.appendChild(list);
  UI.logRows.forEach((r, idx) => {
    const row = txt("div", "gy-log-row");
    const n = txt("input", "hb-input gy-log-name"); n.setAttribute("list", "gy-ex-names"); n.value = r.name;
    n.placeholder = tt("exercise", null, "Exercise"); n.oninput = () => { r.name = n.value; };
    const num = (v, ph, onv) => { const i = txt("input", "hb-input gy-num"); i.type = "number"; i.value = v === "" ? "" : String(v); i.placeholder = ph; i.oninput = () => onv(i.value); return i; };
    row.appendChild(n);
    row.appendChild(num(r.sets, tt("sets", null, "Sets"), (v) => { r.sets = v; }));
    row.appendChild(num(r.reps, tt("reps", null, "reps"), (v) => { r.reps = v; }));
    row.appendChild(num(r.kg, tt("kg", null, "kg"), (v) => { r.kg = v; }));
    const rm = btn("×", "ghost", () => { UI.logRows.splice(idx, 1); if (UI.repaint) UI.repaint(); }, "hb-btn--sm");
    rm.setAttribute("aria-label", tt("remove", null, "Remove"));
    row.appendChild(rm);
    p.appendChild(row);
  });
  p.appendChild(btn(tt("add_exercise", null, "+ Exercise"), "ghost", () => { UI.logRows.push({ name: "", sets: 3, reps: 10, kg: "" }); if (UI.repaint) UI.repaint(); }));
  root.appendChild(p);
  root.appendChild(btn(tt("log_save", null, "✓ Log it"), "primary", async () => {
    const exercises = UI.logRows.filter((r) => String(r.name).trim()).map((r) => ({ name: String(r.name).trim(),
      sets: Number(r.sets) || 1, reps: r.reps === "" ? null : Number(r.reps), weight_kg: r.kg === "" ? null : Number(r.kg) }));
    if (!exercises.length) return;
    const r = await act(ctx, "log_workout", { date: UI.logDate, day_key: UI.logDay, exercises });
    if (r && r.ok) go("summary", r.session, ctx);
  }, "gy-cta"));
  const t = panel();
  t.appendChild(txt("div", "hb-panel-title", tt("log_text_title", null, "Or describe it")));
  const ta = txt("textarea", "hb-textarea gy-textarea");
  ta.rows = 3; ta.placeholder = tt("log_text_ph", null, "Day, exercises, sets×reps, weight…");
  t.appendChild(ta);
  t.appendChild(btn(tt("log_save_text", null, "Log from text"), "secondary", () => { if (ta.value.trim()) act(ctx, "log_workout", { text: ta.value.trim() }); }));
  root.appendChild(t);
}

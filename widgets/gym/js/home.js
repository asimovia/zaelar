// Gym — the home (today, the last 7 days), the preview before starting, the calendar and the muscle map.
import { tt, loc, txt, btn, panel, img, dayLabel, timeLabel, duration, ymd, blockName, blockMeta, UI, go, act, lang } from "./util.js";

// the original app's previewByMuscleGroup: the exercises of a day grouped by body part, from their names.
const GROUP_ORDER = ["chest", "shoulders", "back", "biceps", "triceps", "quads", "hamstrings", "calves", "core", "other"];
function groupOf(name) {
  const n = String(name || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  if (/(plancha|plank|core|abdominal|abs|hollow|dead bug)/.test(n)) return "core";
  if (/(pantorrilla|gemelo|calf|soleo)/.test(n)) return "calves";
  if (/(femoral|rumano|romanian|rdl|hamstring|leg curl|peso muerto|deadlift|gluteo|glute|hip thrust|puente|swing)/.test(n)) return "hamstrings";
  if (/(sentadilla|squat|prensa|leg press|lunge|zancada|pistol|step.?up|bulgar|sled|trineo)/.test(n)) return "quads";
  if (/(biceps|bicep|curl)/.test(n)) return "biceps";
  if (/(triceps|tricep|pushdown|frances|skull|dips|fondos)/.test(n)) return "triceps";
  if (/(remo|row|pull[- ]?up|jalon|pulldown|dominada|face[- ]?pull|encogimiento|shrug|farmer|granjero)/.test(n)) return "back";
  if (/(press hombro|shoulder press|push press|military|militar|lateral|hombro|shoulder|deltoid|thruster|arnold)/.test(n)) return "shoulders";
  if (/(press|bench|banca|pecho|chest|fly|apertura|floor press|push-?ups?|flexion)/.test(n)) return "chest";
  return "other";
}
export function groupLabel(g) {
  return ({ chest: tt("grp_chest", null, "Chest"), shoulders: tt("grp_shoulders", null, "Shoulders"), back: tt("grp_back", null, "Back"),
    biceps: tt("grp_biceps", null, "Biceps"), triceps: tt("grp_triceps", null, "Triceps"), quads: tt("grp_quads", null, "Quads"),
    hamstrings: tt("grp_hamstrings", null, "Hamstrings · glutes"), calves: tt("grp_calves", null, "Calves"),
    core: tt("grp_core", null, "Core"), other: tt("grp_other", null, "Other") })[g] || g;
}

export function previewGroups(blocks, data, open) {
  const groups = {};
  for (const b of blocks || []) {
    if (!b || b.type !== "exercise") continue;
    const e = (data.exercises || {})[b.key];
    const g = groupOf(b.name ? loc(b.name) : e && e.name ? e.name.en + " " + e.name.es : blockName(b, data));
    (groups[g] = groups[g] || []).push(b);
  }
  const box = txt("div", "gy-groups");
  for (const g of GROUP_ORDER) {
    if (!groups[g]) continue;
    const d = txt("details", "gy-group");
    if (open) d.open = true;
    const s = txt("summary", "gy-group-head");
    s.appendChild(txt("span", "gy-group-name", groupLabel(g)));
    s.appendChild(txt("span", "gy-muted", tt("n_exercises", { n: groups[g].length }, "{n} exercises")));
    d.appendChild(s);
    for (const b of groups[g]) {
      const row = txt("div", "gy-ex-row");
      const im = img(data, b.key, "gy-thumb", blockName(b, data));
      if (im) row.appendChild(im);
      const body = txt("div", "gy-ex-body");
      body.appendChild(txt("div", "gy-ex-name", blockName(b, data)));
      body.appendChild(txt("div", "gy-muted", blockMeta(b)));
      row.appendChild(body);
      d.appendChild(row);
    }
    box.appendChild(d);
  }
  return box;
}

export function planLabel(p, data) {
  if (!p) return "";
  if (p.type === "gym") return tt("plan_gym", { day: loc(((data.program || {}).day_names || {})[p.day_key]) || p.day_key || "" }, "Gym · {day}");
  if (p.type === "cardio") return tt("plan_cardio", null, "Cardio");
  if (p.type === "rest") return tt("plan_rest", null, "Rest");
  return p.type;
}

function phaseLine(ph) {
  if (!ph) return "";
  return tt("phase_line", { name: loc(ph.name), min: ph.session_min, intensity: loc(ph.intensity) }, "Phase: {name} · ~{min} min · {intensity}");
}

function last7(data) {
  const box = txt("div", "gy-week");
  const today = new Date();
  const byDate = {};
  for (const s of data.sessions || []) (byDate[s.date] = byDate[s.date] || []).push(s);
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today); d.setDate(d.getDate() - i);
    const k = ymd(d), s = (byDate[k] || [])[0];
    const plan = (data.plan || []).find((p) => p.date === k);
    const cell = txt("button", "gy-week-cell" + (i === 0 ? " is-today" : "") + (s ? " is-done" : ""));
    cell.type = "button";
    cell.appendChild(txt("span", "gy-week-dow", d.toLocaleDateString(lang(), { weekday: "short" }).replace(".", "")));
    cell.appendChild(txt("span", "gy-week-mark", s ? "●" : (i === 0 && plan ? "○" : "·")));
    cell.appendChild(txt("span", "gy-week-label", s ? loc(s.day_name) : (i === 0 && plan ? planLabel(plan, data) : tt("rest", null, "Rest"))));
    cell.onclick = () => { if (s) go("summary", s.id); };
    box.appendChild(cell);
  }
  return box;
}

export function home(root, data, ctx) {
  const n = data.next || {};
  const today = panel("gy-today");
  today.appendChild(txt("div", "gy-muted", tt("today_is", null, "Today's workout")));
  today.appendChild(txt("div", "gy-day-name", loc(n.day_name)));
  const meta = tt("min_exercises", { min: n.estimated_min || 0, n: n.exercise_count || 0 }, "{min} min · {n} exercises");
  today.appendChild(txt("div", "gy-muted", meta));
  if (n.last) today.appendChild(txt("div", "gy-muted", tt("last_was", { day: loc(n.last_name) || n.last }, "Last session: {day}")));
  if (data.program && data.program.phase) today.appendChild(txt("div", "gy-muted", phaseLine(data.program.phase)));
  if (n.source === "plan") today.appendChild(txt("div", "gy-muted", tt("from_plan", null, "From the trainer's plan")));
  const go1 = btn(tt("train", null, "▶ Train"), "primary", () => go("preview", null, ctx), "gy-cta");
  today.appendChild(go1);
  today.appendChild(previewGroups(n.blocks, data, false));
  root.appendChild(today);

  const wk = panel();
  wk.appendChild(txt("div", "hb-panel-title", tt("last_7", null, "Last 7 days")));
  wk.appendChild(last7(data));
  root.appendChild(wk);

  const more = txt("div", "gy-links");
  more.appendChild(btn(tt("trainer", null, "Trainer"), "secondary", () => go("planner", null, ctx)));
  more.appendChild(btn(tt("my_gym", null, "My gym"), "secondary", () => go("config", null, ctx)));
  more.appendChild(btn(tt("program", null, "Program"), "secondary", () => go("program", null, ctx)));
  more.appendChild(btn(tt("log_manual", null, "Log a workout"), "secondary", () => go("log", null, ctx)));
  root.appendChild(more);
}

export function preview(root, data, ctx) {
  const n = data.next || {};
  const hero = panel("gy-today");
  hero.appendChild(txt("div", "gy-muted", tt("today_is", null, "Today's workout")));
  hero.appendChild(txt("div", "gy-day-name", loc(n.day_name)));
  hero.appendChild(txt("div", "gy-muted", tt("min_exercises", { min: n.estimated_min || 0, n: n.exercise_count || 0 }, "{min} min · {n} exercises")));
  hero.appendChild(btn(tt("start", null, "▶ Start"), "primary", () => { UI.tapped = true; act(ctx, "start_session", {}); }, "gy-cta"));
  root.appendChild(hero);
  root.appendChild(previewGroups(n.blocks, data, true));

  const adj = panel();
  adj.appendChild(txt("div", "hb-panel-title", tt("adjust_title", null, "Change today's workout")));
  adj.appendChild(txt("div", "gy-muted", tt("adjust_hint", null, "Tell the trainer what you want («30 minutes only», «something for legs»).")));
  const ta = txt("textarea", "hb-textarea gy-textarea");
  ta.rows = 3; ta.placeholder = tt("adjust_ph", null, "Today I want…");
  adj.appendChild(ta);
  adj.appendChild(btn(tt("apply", null, "Apply"), "secondary", () => { if (ta.value.trim()) act(ctx, "adjust_today", { instruction: ta.value.trim() }); }));
  const days = (data.program || {}).day_names || {};
  const pick = txt("div", "gy-other-day");
  pick.appendChild(txt("span", "gy-muted", tt("other_day", null, "Or train another day:")));
  for (const k of (data.program || {}).schedule || []) {
    if (k === n.day_key) continue;
    pick.appendChild(btn(loc(days[k]) || k, "ghost", () => { UI.tapped = true; act(ctx, "start_session", { day: k }); }, "hb-btn--sm"));
  }
  adj.appendChild(pick);
  root.appendChild(adj);
}

// ── calendar ────────────────────────────────────────────────────────────────────────────────────────────────────

export function sessionMeta(s) {
  const parts = [];
  if (s.started_at) parts.push(timeLabel(s.started_at));
  parts.push(tt("n_exercises", { n: s.exercises_count || 0 }, "{n} exercises"));
  parts.push(tt("n_sets", { n: s.sets_count || 0 }, "{n} sets"));
  if (s.duration_s) parts.push(duration(s.duration_s));
  parts.push(statusLabel(s.status));
  return parts.join(" · ");
}
export function statusLabel(st) {
  return ({ done: tt("st_done", null, "completed"), partial: tt("st_partial", null, "partial"),
    active: tt("st_active", null, "in progress") })[st] || st || "";
}

export function calendar(root, data, ctx) {
  const now = new Date();
  if (!UI.month) UI.month = ymd(now).slice(0, 7);
  const [yy, mm] = UI.month.split("-").map(Number);
  const p = panel("gy-cal");
  const head = txt("div", "gy-cal-head");
  const shift = (dl) => { const d = new Date(yy, mm - 1 + dl, 1); UI.month = ymd(d).slice(0, 7); UI.day = null; if (UI.repaint) UI.repaint(); };
  const prev = btn("‹", "ghost", () => shift(-1)); prev.setAttribute("aria-label", tt("prev_month", null, "Previous month"));
  const next = btn("›", "ghost", () => shift(1)); next.setAttribute("aria-label", tt("next_month", null, "Next month"));
  head.appendChild(prev);
  head.appendChild(txt("strong", null, new Date(yy, mm - 1, 1).toLocaleDateString(lang(), { month: "long", year: "numeric" })));
  head.appendChild(next);
  p.appendChild(head);
  const grid = txt("div", "gy-cal-grid");
  const monday = new Date(2024, 0, 1);              // a Monday: the week's day initials in his language
  for (let i = 0; i < 7; i++) {
    const d = new Date(monday); d.setDate(1 + i);
    grid.appendChild(txt("span", "gy-cal-dow", d.toLocaleDateString(lang(), { weekday: "narrow" })));
  }
  const first = new Date(yy, mm - 1, 1), dow = (first.getDay() + 6) % 7, dim = new Date(yy, mm, 0).getDate();
  for (let i = 0; i < dow; i++) grid.appendChild(txt("span", "gy-cal-empty"));
  const todayStr = ymd(now);
  for (let d = 1; d <= dim; d++) {
    const k = UI.month + "-" + String(d).padStart(2, "0");
    const has = (data.sessions || []).some((s) => s.date === k);
    const plan = (data.plan || []).find((x) => x.date === k);
    const c = txt("button", "gy-cal-cell" + (k === todayStr ? " is-today" : "") + (has ? " is-done" : "")
      + (!has && plan && k >= todayStr ? " is-plan" : "") + (UI.day === k ? " is-selected" : ""), String(d));
    c.type = "button";
    if (has) c.setAttribute("aria-label", tt("day_with_workout", { day: String(d) }, "{day}: workout done"));
    c.onclick = () => { UI.day = UI.day === k ? null : k; if (UI.repaint) UI.repaint(); };
    grid.appendChild(c);
  }
  p.appendChild(grid);
  root.appendChild(p);
  if (UI.day) root.appendChild(dayDetail(UI.day, data, ctx, todayStr));
  else root.appendChild(txt("div", "gy-muted gy-center", tt("tap_a_day", null, "Tap a day to see what you did.")));
}

function dayDetail(k, data, ctx, todayStr) {
  const p = panel();
  const list = (data.sessions || []).filter((s) => s.date === k);
  const plan = (data.plan || []).find((x) => x.date === k);
  p.appendChild(txt("div", "hb-panel-title", dayLabel(k)));
  for (const s of list) {
    const row = txt("div", "gy-day-row");
    const body = txt("button", "gy-day-body");
    body.type = "button";
    body.appendChild(txt("div", "gy-ex-name", loc(s.day_name)));
    body.appendChild(txt("div", "gy-muted", sessionMeta(s)));
    body.onclick = () => go("summary", s.id, ctx);
    row.appendChild(body);
    const del = btn(UI.confirmDel === s.id ? tt("tap_again_delete", null, "Tap again to delete") : tt("delete", null, "Delete"),
      "danger", () => {
        if (UI.confirmDel === s.id) { UI.confirmDel = null; act(ctx, "delete_session", { sessionId: String(s.id) }); }
        else { UI.confirmDel = s.id; if (UI.repaint) UI.repaint(); }
      }, "hb-btn--sm");
    row.appendChild(del);
    p.appendChild(row);
  }
  if (!list.length && plan) {
    p.appendChild(txt("div", "gy-ex-name", planLabel(plan, data)));
    if (plan.reason) p.appendChild(txt("div", "gy-muted", plan.reason));
  }
  if (!list.length && !plan) p.appendChild(txt("div", "gy-muted", tt("nothing_that_day", null, "No workout and no plan for this day.")));
  if (k === todayStr && !list.length) p.appendChild(btn(tt("train_today", null, "▶ Train today"), "primary", () => go("preview", null, ctx)));
  return p;
}

// ── the muscle recovery map ─────────────────────────────────────────────────────────────────────────────────────

export function muscleLabel(m) {
  return ({ chest: tt("m_chest", null, "Chest"), back: tt("m_back", null, "Back"), shoulders: tt("m_shoulders", null, "Shoulders"),
    biceps: tt("m_biceps", null, "Biceps"), triceps: tt("m_triceps", null, "Triceps"), quads: tt("m_quads", null, "Quads"),
    hamstrings: tt("m_hamstrings", null, "Hamstrings"), glutes: tt("m_glutes", null, "Glutes"), calves: tt("m_calves", null, "Calves"),
    core: tt("m_core", null, "Core"), traps: tt("m_traps", null, "Traps") })[m] || m;
}
function stateLabel(s) {
  return ({ building: tt("ms_building", null, "Building"), growing: tt("ms_growing", null, "Growing"), touched: tt("ms_touched", null, "Touched"),
    standby: tt("ms_standby", null, "Standby"), falling: tt("ms_falling", null, "Falling"), losing: tt("ms_losing", null, "Losing"),
    fatigued: tt("ms_fatigued", null, "Fatigued"), recovering: tt("ms_recovering", null, "Recovering"),
    optimal: tt("ms_optimal", null, "Optimal · train"), window_closing: tt("ms_window_closing", null, "Window closing"),
    train_soon: tt("ms_train_soon", null, "Train soon"), urgent: tt("ms_urgent", null, "Urgent"),
    critical: tt("ms_critical", null, "Critical · train now"), no_data: tt("ms_no_data", null, "No data") })[s] || s;
}
// the original app's colours by score, mapped onto the categorical range (the number is always printed beside it).
export function scoreHue(score, mode) {
  if (mode === "opportunity") {
    if (score >= 4) return "red";
    if (score >= 3) return "orange";
    if (score >= 1) return "amber";
    if (score === 0) return "green";
    if (score >= -3) return "grey";
    return "blue";
  }
  if (score >= 3) return "green";
  if (score >= 1) return "teal";
  if (score === 0) return "grey";
  if (score >= -2) return "amber";
  if (score >= -3) return "orange";
  return "red";
}

export function musclesView(root, data, ctx) {
  const p = panel("gy-muscles");
  const tabs = txt("div", "hb-tabs");
  for (const [mode, label] of [["opportunity", tt("mode_opportunity", null, "Opportunity")], ["building", tt("mode_building", null, "Building")]]) {
    const t = txt("button", "hb-tab" + (UI.mode === mode ? " is-on" : ""), label);
    t.type = "button"; t.setAttribute("aria-selected", UI.mode === mode ? "true" : "false");
    t.onclick = () => { UI.mode = mode; if (UI.repaint) UI.repaint(); };
    tabs.appendChild(t);
  }
  p.appendChild(tabs);
  p.appendChild(txt("div", "gy-muted", UI.mode === "opportunity"
    ? tt("hint_opportunity", null, "High = train it now · 0 = the best window · negative = just trained")
    : tt("hint_building", null, "High = building · 0 = standby · negative = losing")));
  const list = txt("div", "gy-ms-list");
  for (const m of data.muscles || []) {
    const score = UI.mode === "opportunity" ? m.opportunity_score : m.building_score;
    const state = UI.mode === "opportunity" ? m.opportunity_state : m.building_state;
    const hue = scoreHue(score, UI.mode);
    const row = txt("div", "gy-ms-row");
    row.appendChild(txt("span", "gy-ms-name", muscleLabel(m.muscle)));
    const track = txt("div", "gy-ms-track");
    track.appendChild(txt("span", "gy-ms-axis"));
    const fill = txt("span", "gy-ms-fill");
    const w = Math.abs(score / 5 * 50);
    fill.style.width = w + "%";
    if (score >= 0) fill.style.left = "50%"; else fill.style.right = "50%";
    fill.style.background = "var(--hb-c-" + hue + ")";
    track.appendChild(fill);
    track.title = stateLabel(state) + " · " + (m.days_since != null
      ? tt("days_ago", { n: m.days_since }, "last {n} d ago") : tt("no_data", null, "no data")) + " · " + tt("sets_7d", { n: m.sets_7d || 0 }, "{n} sets in 7 d");
    row.appendChild(track);
    row.appendChild(txt("span", "gy-ms-score", (score > 0 ? "+" : "") + score));
    row.appendChild(txt("span", "gy-ms-state", stateLabel(state)));
    list.appendChild(row);
  }
  p.appendChild(list);
  if (!(data.muscles || []).some((m) => m.days_since != null)) {
    p.appendChild(txt("div", "gy-muted", tt("muscles_empty", null, "No recent workouts yet. Record a few sessions and your state appears here.")));
  }
  root.appendChild(p);
}

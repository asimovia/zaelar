// Gym — shared helpers of the card: translation, DOM, formatting, and the card's own navigation state.

let _T = null;
let _LANG = "en";

export function bindLang(ctx) {
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  try { _LANG = String((ctx && ctx.lang) || "en").slice(0, 2); } catch (_) { _LANG = "en"; }
}
export function lang() { return _LANG; }

export function tt(key, params, fb) {
  try { if (_T) { const s = _T("widgets.gym." + key, params); if (s && s !== "widgets.gym." + key) return s; } } catch (_) {}
  let s = fb;
  if (params) for (const k in params) s = s.split("{" + k + "}").join(String(params[k]));
  return s;
}

// A program text is a plain string or {en, es}: the person's language, else English.
export function loc(v) {
  if (v == null) return "";
  if (typeof v === "object") return String(v[_LANG] || v.en || Object.values(v)[0] || "");
  return String(v);
}

export function txt(tag, cls, s) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (s != null) e.textContent = s;
  return e;
}
export function btn(label, variant, onClick, extra) {
  const b = txt("button", "hb-btn hb-btn--" + (variant || "secondary") + (extra ? " " + extra : ""), label);
  b.type = "button";
  if (onClick) b.onclick = onClick;
  return b;
}
export function panel(cls) { return txt("div", "hb-panel" + (cls ? " " + cls : "")); }

export function clock(sec) {
  sec = Math.max(0, Math.round(sec || 0));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : String(m)) + ":" + String(s).padStart(2, "0");
}
export function duration(sec) {
  if (!sec || sec < 0) return "—";
  const m = Math.floor(sec / 60), s = sec % 60;
  if (m < 60) return m + "m " + String(s).padStart(2, "0") + "s";
  return Math.floor(m / 60) + "h " + String(m % 60).padStart(2, "0") + "m";
}
export function dayLabel(dateStr, opts) {
  try { return new Date(dateStr + "T00:00").toLocaleDateString(_LANG, opts || { weekday: "long", day: "numeric", month: "long" }); }
  catch (_) { return dateStr; }
}
export function timeLabel(ms) {
  try { return new Date(ms).toLocaleTimeString(_LANG, { hour: "2-digit", minute: "2-digit" }); } catch (_) { return ""; }
}
export function ymd(d) {
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}

export function blockName(b, data) {
  if (!b) return "";
  if (b.name) return loc(b.name);
  if (b.type === "exercise") {
    const e = data && data.exercises && data.exercises[b.key];
    return e ? loc(e.name) : (b.key || "");
  }
  return typeLabel(b.type);
}
export function typeLabel(type) {
  return ({ stretch: tt("type_stretch", null, "Stretch"), cardio: tt("type_cardio", null, "Cardio"),
    transition: tt("type_transition", null, "Transition"), exercise: tt("type_exercise", null, "Exercise") })[type] || "";
}
export function blockMeta(b) {
  if (b.type === "exercise") {
    const sets = b.sets ? b.sets + "×" + loc(b.reps) : "";
    const w = b.weight_initial_kg ? " · " + b.weight_initial_kg + " kg" : "";
    return sets + w + (b.weight_hint ? " · " + loc(b.weight_hint) : "");
  }
  if (b.duration_sec) {
    const m = Math.floor(b.duration_sec / 60), r = b.duration_sec % 60;
    return (m ? m + ":" + String(r).padStart(2, "0") : r + "s") + (b.cue ? " · " + loc(b.cue) : "");
  }
  return loc(b.cue);
}

export function img(data, key, cls, alt) {
  const src = key && data && data.images && data.images[key];
  if (!src) return null;
  const i = document.createElement("img");
  i.className = cls; i.loading = "lazy"; i.decoding = "async"; i.alt = alt || ""; i.src = src;
  i.onerror = () => { i.remove(); };
  return i;
}

// The card's own navigation (module state: it outlives the re-render every data push causes).
export const UI = { view: "home", arg: null, seenN: null, month: null, day: null, mode: "opportunity",
  msg: null, confirmDel: null, logRows: null, logDate: null, logDay: null, from: null, fromArg: null };

// A screen change is ONE transition (widgets/AGENTS.md, V2-626): every entry point — a tap, a pushed view — comes
// through here and every per-screen flag is reset here, nowhere else.
export function go(view, arg, ctx) {
  if ((view === "summary" || view === "exercise") && UI.view !== view && !(view === "summary" && UI.view === "exercise")) { UI.from = UI.view; UI.fromArg = UI.arg; }
  UI.view = view; UI.arg = arg == null ? null : arg;
  UI.msg = null; UI.confirmDel = null; UI.day = view === "calendar" ? UI.day : null;
  if (view !== "log") { UI.logRows = null; UI.logDate = null; UI.logDay = null; }
  if (ctx && typeof ctx.top === "function") { try { ctx.top(); } catch (_) {} }
  if (UI.repaint) UI.repaint();
}

// An action's answer that says «the model is not available yet» becomes a sentence on the screen that asked.
export async function act(ctx, name, payload) {
  let r = null;
  try { r = await ctx.action(name, payload || {}); } catch (_) { r = null; }
  if (r && r.ok === false) {
    UI.msg = r.error === "model_unavailable"
      ? tt("model_unavailable", null, "The trainer is not available yet. Tell the agent instead, or use the form.")
      : tt("action_failed", { why: String(r.error || "") }, "Could not do it ({why}).");
    if (UI.repaint) UI.repaint();
  }
  return r;
}

// Nutrition — shared helpers: the translation helper, DOM builders, formats and the stylesheet (one injection).

let _T = null;
let _LANG = "en";
export function bindLang(ctx) {
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  try { _LANG = (ctx && ctx.lang) || "en"; } catch (_) { _LANG = "en"; }
}
export function lang() { return _LANG; }
export function tt(key, params, fb) {
  try { if (_T) { const s = _T("widgets.nutrition." + key, params); if (s && s !== "widgets.nutrition." + key) return s; } } catch (_) {}
  let s = fb;
  if (params) for (const k in params) s = s.split("{" + k + "}").join(String(params[k]));
  return s;
}

export function h(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = String(text);
  return e;
}
export function btn(cls, text, onClick, title) {
  const b = h("button", "hb-btn " + cls, text);
  b.type = "button";
  if (title) b.title = title;
  if (onClick) b.onclick = onClick;
  return b;
}
export function field(labelText, input) {
  const f = h("label", "hb-field nu-field");
  f.appendChild(h("span", "hb-label", labelText));
  f.appendChild(input);
  return f;
}
export function input(type, value, cls, attrs) {
  const i = document.createElement("input");
  i.type = type;
  i.className = "hb-input " + (cls || "");
  if (value != null) i.value = String(value);
  for (const k in (attrs || {})) i.setAttribute(k, attrs[k]);
  return i;
}
export function numIn(value, step, attrs) {
  return input("text", value == null ? "" : value, "nu-num", { inputmode: "decimal", step: step || "any", ...(attrs || {}) });
}
export function select(options, value) {
  const s = document.createElement("select");
  s.className = "hb-select";
  for (const [v, label] of options) {
    const o = document.createElement("option");
    o.value = v; o.textContent = label;
    if (String(v) === String(value ?? "")) o.selected = true;
    s.appendChild(o);
  }
  return s;
}
// «75,8» or «75.8» → 75.8; "" → null (source: parseDecimal).
export function parseDecimal(v) {
  const s = String(v ?? "").trim().replace(",", ".");
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}
export function round(n, d) { if (n == null) return null; const k = Math.pow(10, d || 0); return Math.round(n * k) / k; }
export function fmtNum(n, d) {
  if (n == null) return "—";
  try { return new Intl.NumberFormat(_LANG, { maximumFractionDigits: d || 0 }).format(n); } catch (_) { return String(round(n, d)); }
}
function asDate(s) { return new Date(String(s).length <= 10 ? s + "T12:00:00" : s); }
export function fmtDay(s, long) {
  if (!s) return "";
  try {
    return new Intl.DateTimeFormat(_LANG, long ? { weekday: "long", day: "numeric", month: "long" }
      : { weekday: "short", day: "numeric", month: "short" }).format(asDate(s));
  } catch (_) { return s; }
}
export function fmtTime(s) {
  if (!s) return "";
  try { return new Intl.DateTimeFormat(_LANG, { hour: "2-digit", minute: "2-digit" }).format(asDate(s)); } catch (_) { return String(s).slice(11, 16); }
}
export function pad(n) { return String(n).padStart(2, "0"); }
// The screen's own local clock, as the store keeps it: «YYYY-MM-DDTHH:MM».
export function localNow() {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
// The logical day starts at 03:00 (a snack at 02:30 is still yesterday).
export function logicalToday() {
  const d = new Date(Date.now() - 3 * 3600 * 1000);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
export function shiftDay(day, n) {
  const d = asDate(day); d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
// A rating's colour — always paired with a word or a shape, never colour alone.
export function hue(rating) {
  return ({ green: "var(--hb-c-green,#3DDC97)", yellow: "var(--hb-c-amber,#FFC53D)", orange: "var(--hb-c-orange,#FF8C42)",
    red: "var(--hb-c-red,#FF6259)" })[rating] || "var(--hb-c-grey,#8B98AC)";
}
// The day bar's colour comes from the day's quality (source: todayHealthColor): 4+ green, 3+ amber, 2+ orange, red.
export function qualityRating(avg) {
  if (avg == null) return "gray";
  return avg >= 4 ? "green" : avg >= 3 ? "yellow" : avg >= 2 ? "orange" : "red";
}
export function errorText(code) {
  const map = {
    estimator_unavailable: tt("err_estimator_unavailable", null, "Automatic estimates are not available yet. Enter the calories by hand."),
    estimator_failed: tt("err_estimator_failed", null, "The estimate failed. Try again or enter it by hand."),
    estimator_bad_answer: tt("err_estimator_failed", null, "The estimate failed. Try again or enter it by hand."),
    no_food_identified: tt("err_no_food", null, "No food was recognised in the photo."),
    photo_not_found: tt("err_photo_missing", null, "The photo is no longer there."),
    upload_failed: tt("err_upload", null, "The photo could not be uploaded."),
  };
  return map[code] || tt("err_generic", { code: String(code || "") }, "Something went wrong ({code}).");
}

export const CSS = `
.hb-nutrition{font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);width:100%;
  box-sizing:border-box;display:flex;flex-direction:column;gap:var(--sp-3,12px);color:var(--hb-ink,#F2F4F7);font-size:var(--fs-ui,.875rem);line-height:var(--hb-lh,1.55)}
.hb-nutrition .nu-nav{display:flex;gap:var(--sp-1,4px);overflow-x:auto;flex-wrap:nowrap;scrollbar-width:none}
.hb-nutrition .nu-nav .hb-tab{flex:0 0 auto}
.hb-nutrition .nu-dayhead{display:flex;align-items:center;justify-content:space-between;gap:var(--sp-2,8px)}
.hb-nutrition .nu-dayhead b{font-size:var(--fs-title,.95rem);font-weight:600;text-transform:capitalize;text-align:center;flex:1}
.hb-nutrition .nu-panel{background:var(--hb-bg-soft,#272D35);border:1px solid var(--hb-line,rgba(255,255,255,.14));border-radius:var(--hb-r-l,12px);
  padding:var(--sp-4,16px);display:flex;flex-direction:column;gap:var(--sp-3,12px)}
.hb-nutrition .nu-big{display:flex;align-items:baseline;gap:var(--sp-2,8px);flex-wrap:wrap}
.hb-nutrition .nu-big b{font-size:2rem;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.1}
.hb-nutrition .nu-big span{color:var(--hb-muted,#A9B3C1)}
.hb-nutrition .nu-track{height:10px;border-radius:6px;background:var(--hb-bubble,#313740);overflow:hidden}
.hb-nutrition .nu-fill{height:100%;border-radius:6px}
.hb-nutrition .nu-macros{display:grid;grid-template-columns:repeat(auto-fit,minmax(88px,1fr));gap:var(--sp-2,8px)}
.hb-nutrition .nu-macro{background:var(--hb-bubble,#313740);border:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));border-radius:var(--hb-r-m,10px);padding:var(--sp-2,8px) var(--sp-3,12px)}
.hb-nutrition .nu-macro b{display:block;font-size:1.15rem;font-variant-numeric:tabular-nums}
.hb-nutrition .nu-macro span{font-size:var(--fs-micro,.8rem);color:var(--hb-muted,#A9B3C1)}
.hb-nutrition .nu-row{display:flex;align-items:center;gap:var(--sp-2,8px);flex-wrap:wrap}
.hb-nutrition .nu-grow{flex:1 1 auto;min-width:0}
.hb-nutrition .nu-note{color:var(--hb-muted,#A9B3C1);font-size:var(--fs-caption,.86rem)}
.hb-nutrition .nu-warn{color:var(--hb-warn-ink,#FFC53D);font-size:var(--fs-caption,.86rem)}
.hb-nutrition .nu-score{display:inline-flex;align-items:baseline;gap:4px;font-weight:700;font-variant-numeric:tabular-nums}
.hb-nutrition .nu-score b{font-size:1.4rem}
.hb-nutrition .nu-comps{display:flex;gap:var(--sp-1,4px);flex-wrap:wrap}
.hb-nutrition .nu-comp{font-size:var(--fs-micro,.8rem);padding:2px var(--sp-2,8px);border-radius:999px;border:1px solid var(--hb-line,rgba(255,255,255,.14));color:var(--hb-muted,#A9B3C1)}
.hb-nutrition .nu-comp.is-on{color:var(--hb-ink,#F2F4F7);border-color:color-mix(in srgb,var(--hb-c-green,#3DDC97) 55%,transparent);background:color-mix(in srgb,var(--hb-c-green,#3DDC97) 16%,transparent)}
.hb-nutrition .nu-meals{display:flex;flex-direction:column;gap:var(--sp-2,8px)}
.hb-nutrition .nu-meal{background:var(--hb-bubble,#313740);border:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));border-radius:var(--hb-r-m,10px);
  padding:var(--sp-2,8px) var(--sp-3,12px);display:flex;flex-direction:column;gap:var(--sp-2,8px);border-left:4px solid var(--nu-hue,var(--hb-c-grey,#8B98AC))}
.hb-nutrition .nu-meal-head{display:flex;align-items:center;gap:var(--sp-2,8px);cursor:pointer;background:none;border:0;color:inherit;font:inherit;text-align:left;padding:0;width:100%}
.hb-nutrition .nu-meal-head:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF);border-radius:6px}
.hb-nutrition .nu-meal-head .nu-time{color:var(--hb-muted,#A9B3C1);font-variant-numeric:tabular-nums;font-size:var(--fs-caption,.86rem)}
.hb-nutrition .nu-meal-head .nu-kcal{font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}
.hb-nutrition .nu-thumb{width:44px;height:44px;border-radius:8px;object-fit:cover;flex:0 0 auto;background:var(--hb-hover,#3C434F)}
.hb-nutrition .nu-photo{width:100%;max-height:260px;object-fit:cover;border-radius:var(--hb-r-m,10px)}
.hb-nutrition .nu-ings{width:100%;border-collapse:collapse;font-size:var(--fs-caption,.86rem)}
.hb-nutrition .nu-ings td{padding:3px 4px;border-bottom:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));font-variant-numeric:tabular-nums}
.hb-nutrition .nu-ings td:first-child{width:50%}
.hb-nutrition .nu-wrap{overflow-x:auto}
.hb-nutrition .nu-form{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:var(--sp-2,8px)}
.hb-nutrition .nu-field{display:flex;flex-direction:column;gap:4px;min-width:0}
.hb-nutrition .nu-field .hb-input,.hb-nutrition .nu-field .hb-select{width:100%;box-sizing:border-box}
.hb-nutrition textarea.hb-textarea{width:100%;box-sizing:border-box;min-height:64px;resize:vertical;font-family:inherit}
.hb-nutrition .nu-file{position:relative;overflow:hidden}
.hb-nutrition .nu-file input{position:absolute;inset:0;opacity:0;cursor:pointer}
.hb-nutrition .nu-shots{display:flex;gap:var(--sp-2,8px);flex-wrap:wrap}
.hb-nutrition .nu-chart{width:100%;height:150px;display:block}
.hb-nutrition .nu-chart .nu-line{fill:none;stroke:var(--hb-c-orange,#FF8C42);stroke-width:2.2;stroke-linejoin:round;stroke-linecap:round}
.hb-nutrition .nu-chart .nu-area{fill:color-mix(in srgb,var(--hb-c-orange,#FF8C42) 22%,transparent);stroke:none}
.hb-nutrition .nu-chart .nu-dot{fill:var(--hb-c-orange,#FF8C42);stroke:var(--hb-bg-soft,#272D35);stroke-width:1.5}
.hb-nutrition .nu-chart text{fill:var(--hb-muted,#A9B3C1);font-size:10px}
.hb-nutrition .nu-strip{display:grid;grid-template-columns:repeat(30,minmax(0,1fr));gap:2px}
.hb-nutrition .nu-strip i{display:block;height:14px;border-radius:3px}
.hb-nutrition .nu-legend{display:flex;gap:var(--sp-3,12px);flex-wrap:wrap;font-size:var(--fs-micro,.8rem);color:var(--hb-muted,#A9B3C1)}
.hb-nutrition .nu-legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:4px;vertical-align:middle}
.hb-nutrition .nu-list{display:flex;flex-direction:column}
.hb-nutrition .nu-li{display:flex;align-items:center;gap:var(--sp-2,8px);padding:var(--sp-2,8px) 0;border-bottom:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));flex-wrap:wrap}
.hb-nutrition .nu-rec{display:flex;gap:var(--sp-2,8px);align-items:flex-start}
.hb-nutrition .nu-rec .hb-badge{flex:0 0 auto}
.hb-nutrition .nu-coach p{margin:0 0 var(--sp-2,8px)}
.hb-nutrition h4{margin:0;font-size:var(--fs-caption,.86rem);font-weight:600;color:var(--hb-muted,#A9B3C1);text-transform:uppercase;letter-spacing:.05em}
`;

export function injectStyles() {
  if (document.getElementById("hb-nutrition-css")) return;
  const s = document.createElement("style");
  s.id = "hb-nutrition-css";
  s.textContent = CSS;
  document.head.appendChild(s);
}

// Gym — guided strength sessions from a versioned plan (V2-900, ported from an earlier PWA).
// The session itself lives in data.py (`live`): every screen paints the same block, set and rest. ONE screen drives it
// (the one that claimed it: where he tapped Start, or the phone app): it reads the heart-rate strap through
// ctx.device(), beeps on each change of block and keeps the screen awake. Any screen reports a timer that ran out
// (`timer_done`, counted once against the cursor it saw). No network, no library: pictures are the app's own files.
import { bindLang, tt, txt, UI, go } from "./js/util.js";
import { home, preview, calendar, musclesView } from "./js/home.js";
import { session, timerLeft } from "./js/session.js";
import { onboarding, config, planner, programView, summary, exerciseHistory, logView } from "./js/screens.js";

function injectStyles() {
  if (document.getElementById("hb-gym-css")) return;
  const s = document.createElement("style"); s.id = "hb-gym-css"; s.textContent = `
  .hb-gym{font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);width:100%;box-sizing:border-box;
    display:flex;flex-direction:column;gap:var(--sp-3,12px);color:var(--hb-ink,#F2F4F7);font-size:var(--fs-ui,.875rem);line-height:var(--hb-lh,1.55)}
  .hb-gym .gy-muted{color:var(--hb-muted,#A7B0BE);font-size:var(--fs-caption,.8625rem)}
  .hb-gym .gy-center{text-align:center}
  .hb-gym .gy-row{display:flex;flex-wrap:wrap;gap:var(--sp-2,8px);align-items:center}
  .hb-gym .gy-links{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:var(--sp-2,8px)}
  .hb-gym .gy-cta{width:100%;font-size:1rem;padding:var(--sp-3,12px)}
  .hb-gym .gy-day-name{font-size:var(--fs-title,1.15rem);font-weight:700;line-height:var(--hb-lh-tight,1.35)}
  .hb-gym .gy-today{display:flex;flex-direction:column;gap:var(--sp-2,8px)}
  .hb-gym .gy-groups{display:flex;flex-direction:column;gap:var(--sp-2,8px)}
  .hb-gym .gy-group{background:var(--hb-bubble,#313740);border:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));border-radius:var(--hb-r-m,10px);padding:var(--sp-2,8px) var(--sp-3,12px)}
  .hb-gym .gy-group-head{display:flex;justify-content:space-between;gap:var(--sp-2,8px);cursor:pointer;font-weight:600}
  .hb-gym .gy-group-head:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-gym .gy-ex-row{display:flex;gap:var(--sp-3,12px);align-items:center;padding:var(--sp-2,8px) 0;border-top:1px solid var(--hb-line-subtle,rgba(255,255,255,.09))}
  .hb-gym .gy-ex-body{min-width:0}
  .hb-gym .gy-ex-name{font-weight:600}
  .hb-gym .gy-ex-label{color:var(--hb-muted,#A7B0BE);font-variant-numeric:tabular-nums;margin-right:var(--sp-1,4px)}
  .hb-gym .gy-thumb{width:56px;height:40px;object-fit:cover;border-radius:var(--hb-r-s,8px);flex:none;background:var(--hb-bg-soft,#272D35)}
  .hb-gym .gy-hero{width:100%;max-height:220px;object-fit:contain;border-radius:var(--hb-r-m,10px);background:#fff}
  .hb-gym .gy-week{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:var(--sp-1,4px)}
  .hb-gym .gy-week-cell{display:flex;flex-direction:column;align-items:center;gap:2px;padding:var(--sp-2,8px) 2px;border-radius:var(--hb-r-s,8px);
    border:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));background:var(--hb-bubble,#313740);color:var(--hb-ink,#F2F4F7);font:inherit;cursor:pointer;min-width:0}
  .hb-gym .gy-week-cell:hover{background:var(--hb-hover,#3C434F)}
  .hb-gym .gy-week-cell:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-gym .gy-week-cell.is-today{border-color:var(--hb-line-strong,rgba(255,255,255,.24))}
  .hb-gym .gy-week-cell.is-done .gy-week-mark{color:var(--hb-ok,#3DDC97)}
  .hb-gym .gy-week-dow{font-size:var(--fs-micro,.8rem);color:var(--hb-muted,#A7B0BE);text-transform:capitalize}
  .hb-gym .gy-week-label{font-size:var(--fs-micro,.8rem);text-align:center;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}
  .hb-gym .gy-cal-head{display:flex;justify-content:space-between;align-items:center;text-transform:capitalize}
  .hb-gym .gy-cal-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:var(--sp-1,4px);margin-top:var(--sp-2,8px)}
  .hb-gym .gy-cal-dow{text-align:center;color:var(--hb-muted,#A7B0BE);font-size:var(--fs-micro,.8rem);text-transform:uppercase}
  .hb-gym .gy-cal-cell{aspect-ratio:1/1;min-height:32px;border-radius:var(--hb-r-s,8px);border:1px solid transparent;background:var(--hb-bubble,#313740);
    color:var(--hb-ink,#F2F4F7);font:inherit;cursor:pointer;position:relative}
  .hb-gym .gy-cal-cell:hover{background:var(--hb-hover,#3C434F)}
  .hb-gym .gy-cal-cell:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-gym .gy-cal-cell.is-today{border-color:var(--hb-line-strong,rgba(255,255,255,.24))}
  .hb-gym .gy-cal-cell.is-done{background:color-mix(in srgb,var(--hb-c-green,#3DDC97) 24%,transparent);font-weight:700}
  .hb-gym .gy-cal-cell.is-plan{border-style:dashed;border-color:var(--hb-c-blue,#5B9BFF)}
  .hb-gym .gy-cal-cell.is-selected{background:color-mix(in srgb,var(--hb-accent,#AE90FF) 18%,transparent);box-shadow:0 0 0 1px color-mix(in srgb,var(--hb-accent,#AE90FF) 55%,transparent)}
  .hb-gym .gy-day-row{display:flex;gap:var(--sp-2,8px);align-items:center;padding:var(--sp-2,8px) 0;border-top:1px solid var(--hb-line-subtle,rgba(255,255,255,.09))}
  .hb-gym .gy-day-body,.hb-gym .gy-sum-head{flex:1;text-align:left;background:none;border:0;color:inherit;font:inherit;cursor:pointer;padding:0;display:flex;flex-direction:column;gap:2px}
  .hb-gym .gy-sum-head{flex-direction:row;align-items:center;gap:var(--sp-2,8px)}
  .hb-gym .gy-day-body:focus-visible,.hb-gym .gy-sum-head:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-gym .gy-ms-list{display:flex;flex-direction:column;gap:var(--sp-2,8px);margin-top:var(--sp-2,8px)}
  .hb-gym .gy-ms-row{display:grid;grid-template-columns:minmax(80px,1fr) minmax(100px,2fr) 2.5em minmax(70px,1fr);gap:var(--sp-2,8px);align-items:center}
  .hb-gym .gy-ms-track{position:relative;height:10px;border-radius:5px;background:var(--hb-bubble,#313740);overflow:hidden}
  .hb-gym .gy-ms-axis{position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--hb-line-strong,rgba(255,255,255,.24))}
  .hb-gym .gy-ms-fill{position:absolute;top:0;bottom:0}
  .hb-gym .gy-ms-score{font-variant-numeric:tabular-nums;font-weight:700;text-align:right}
  .hb-gym .gy-ms-state{font-size:var(--fs-micro,.8rem);color:var(--hb-muted,#A7B0BE)}
  .hb-gym .gy-sess-head{display:flex;justify-content:space-between;align-items:flex-start;gap:var(--sp-2,8px)}
  .hb-gym .gy-sess-progress{font-weight:600}
  .hb-gym .gy-elapsed{font-variant-numeric:tabular-nums;font-size:1.1rem;font-weight:600}
  .hb-gym .gy-progress{height:6px;border-radius:3px;background:var(--hb-bubble,#313740);overflow:hidden}
  .hb-gym .gy-progress-fill{height:100%;background:var(--hb-accent,#AE90FF)}
  .hb-gym .gy-block{display:flex;flex-direction:column;gap:var(--sp-2,8px);align-items:stretch}
  .hb-gym .gy-block > .hb-badge{align-self:flex-start}
  .hb-gym .gy-block-title{font-size:var(--fs-title,1.15rem);font-weight:700}
  .hb-gym .gy-set-progress{font-weight:600}
  .hb-gym .gy-big-timer{font-size:clamp(3rem,14vw,5rem);font-weight:700;text-align:center;font-variant-numeric:tabular-nums;line-height:1.1}
  .hb-gym .gy-targets,.hb-gym .gy-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:var(--sp-2,8px)}
  .hb-gym .gy-target-val{font-size:1.25rem;font-weight:700;font-variant-numeric:tabular-nums}
  .hb-gym .gy-inputs{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:var(--sp-2,8px)}
  .hb-gym .gy-input{display:flex;flex-direction:column;gap:var(--sp-1,4px)}
  .hb-gym .gy-stepper{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:var(--sp-1,4px)}
  .hb-gym .gy-num{text-align:center;font-variant-numeric:tabular-nums;min-width:0}
  .hb-gym .gy-done{font-size:1.15rem;font-weight:700}
  .hb-gym .gy-rest{display:flex;flex-direction:column;gap:var(--sp-2,8px);align-items:stretch}
  .hb-gym .gy-hr{display:flex;align-items:baseline;gap:var(--sp-2,8px);justify-content:center}
  .hb-gym .gy-hr-icon{color:var(--hb-risk,#FF7384)}
  .hb-gym .gy-hr-bpm{font-size:2rem;font-variant-numeric:tabular-nums}
  .hb-gym .gy-hr--threshold .gy-hr-bpm{color:var(--hb-c-orange,#FF8C42)}
  .hb-gym .gy-hr--max .gy-hr-bpm{color:var(--hb-c-red,#FF6259)}
  .hb-gym .gy-note{padding:var(--sp-2,8px) var(--sp-3,12px);border-radius:var(--hb-r-s,8px);background:var(--hb-warn-bg,rgba(255,197,61,.12));
    border:1px solid var(--hb-warn-border,rgba(255,197,61,.35));color:var(--hb-warn-ink,#FFC53D)}
  .hb-gym .gy-alt-card{display:flex;flex-direction:column;gap:var(--sp-1,4px)}
  .hb-gym .gy-programs,.hb-gym .gy-equip{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:var(--sp-2,8px)}
  .hb-gym .gy-program,.hb-gym .gy-equip-item{text-align:left;font:inherit;color:inherit;display:flex;flex-direction:column;gap:var(--sp-1,4px)}
  .hb-gym .gy-equip-item.is-selected{background:color-mix(in srgb,var(--hb-accent,#AE90FF) 18%,transparent);font-weight:700}
  .hb-gym .gy-textarea{width:100%;box-sizing:border-box}
  .hb-gym .gy-version{display:flex;gap:var(--sp-2,8px);align-items:baseline;padding:var(--sp-1,4px) 0}
  .hb-gym .gy-version.is-current strong{color:var(--hb-ink,#F2F4F7)}
  .hb-gym .gy-phase.is-selected{box-shadow:0 0 0 1px color-mix(in srgb,var(--hb-accent,#AE90FF) 55%,transparent)}
  .hb-gym .gy-sum-set,.hb-gym .gy-hist-row{display:flex;gap:var(--sp-2,8px);align-items:baseline;padding:var(--sp-1,4px) 0;font-variant-numeric:tabular-nums}
  .hb-gym .gy-log-row{display:grid;grid-template-columns:repeat(3,minmax(0,1fr)) auto;gap:var(--sp-1,4px);margin-top:var(--sp-2,8px)}
  .hb-gym .gy-log-name{grid-column:1/-1;min-width:0}
  .hb-gym .gy-other-day{display:flex;flex-wrap:wrap;gap:var(--sp-1,4px);align-items:center;margin-top:var(--sp-2,8px)}
  .hb-gym .gy-msg{padding:var(--sp-2,8px) var(--sp-3,12px);border-radius:var(--hb-r-s,8px);background:var(--hb-bg-soft,#272D35);border:1px solid var(--hb-line,rgba(255,255,255,.14))}
  .hb-gym .gy-nav{display:flex;flex-wrap:wrap;gap:var(--sp-2,8px);align-items:center;justify-content:space-between}
  `; document.head.appendChild(s);
}

// ── the screen that drives the session (module state: it outlives the re-render every data push causes) ──
const S = { owner: "g-" + Math.random().toString(36).slice(2) + Date.now().toString(36), offset: 0, hr: null, hrStarting: false,
  wake: null, lastCue: null, lastHrSent: 0, reported: null, tapped: false, tick: null, elapsedEl: null };

function beep(ctx, kind) {
  if (ctx && ctx.running === false) return;                     // the agent is stopped: silent
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ac = new AC(), osc = ac.createOscillator(), gain = ac.createGain();
    osc.connect(gain); gain.connect(ac.destination);
    osc.frequency.value = kind === "end" ? 880 : 660;              // the original app's two tones
    gain.gain.setValueAtTime(0, ac.currentTime);
    gain.gain.linearRampToValueAtTime(0.15, ac.currentTime + 0.01);
    gain.gain.linearRampToValueAtTime(0, ac.currentTime + 0.18);
    osc.start(); osc.stop(ac.currentTime + 0.2);
    setTimeout(() => { try { ac.close(); } catch (_) {} }, 300);
  } catch (_) {}
}

async function wakeOn() {
  try { if (!S.wake && typeof navigator !== "undefined" && navigator.wakeLock) S.wake = await navigator.wakeLock.request("screen"); } catch (_) {}
}
function wakeOff() { try { if (S.wake && S.wake.release) S.wake.release(); } catch (_) {} S.wake = null; }

async function hrOff() {
  const h = S.hr; S.hr = null;
  if (h && h.stop) { try { await h.stop(); } catch (_) {} }
}

// The strap: only on the driving screen, only where this screen has one (`sensors.heart_rate`), never on render alone
// for a session started elsewhere — he started it, here or by voice in the phone app he carries.
async function hrOn(ctx, d) {
  if (S.hr || S.hrStarting) return;
  S.hrStarting = true;
  try {
    const dev = await ctx.device();
    const info = await dev.details();
    if (!(info && info.sensors && info.sensors.heart_rate && info.sensors.heart_rate.available)) return;
    const r = await dev.activity({ sensors: ["heart_rate"], label: "gym", kind: "fitness" }, (s) => {
      if (!s || s.kind !== "heart_rate" || typeof s.bpm !== "number") return;
      const now = Date.now();
      if (now - S.lastHrSent >= 5000) { S.lastHrSent = now; ctx.action("hr", { owner: S.owner, bpm: s.bpm }); }
    });
    if (r && !r.error) S.hr = r;
  } catch (_) {} finally { S.hrStarting = false; }
}

async function drive(ctx, d) {
  const lv = d.live;
  if (!lv) { await hrOff(); wakeOff(); S.lastCue = null; return; }
  if (!lv.owner) {
    let mine = S.tapped;
    if (!mine) {
      try { const info = await (await ctx.device()).details(); mine = !!(info && (info.background_sessions || info.form === "phone")); } catch (_) {}
    }
    if (mine) { S.tapped = false; ctx.action("claim", { owner: S.owner }); }
    return;
  }
  if (lv.owner !== S.owner) { await hrOff(); wakeOff(); return; }
  wakeOn();
  hrOn(ctx, d);
  if (S.lastCue !== null && lv.cue !== S.lastCue) beep(ctx, lv.cue_kind);
  S.lastCue = lv.cue;
}

function startTick(el, d, ctx, timerEl) {
  clearInterval(S.tick);
  const lv = d.live;
  if (!lv) return;
  S.tick = setInterval(() => {
    if (!el.isConnected) { clearInterval(S.tick); hrOff(); wakeOff(); return; }
    if (S.elapsedEl) S.elapsedEl.textContent = clockOf((Date.now() + S.offset - lv.started_at) / 1000);
    const t = lv.timer;
    if (!t) return;
    const left = timerLeft(t, S.offset);
    if (timerEl) timerEl.textContent = clockOf(left);
    const key = lv.session_id + ":" + lv.i + ":" + lv.set + ":" + lv.resting + ":" + t.ends_at;
    if (left <= 0 && !t.paused && S.reported !== key) {
      S.reported = key;
      ctx.action("timer_done", { i: lv.i, set: lv.set, resting: lv.resting });
    }
  }, 250);
}
function clockOf(sec) {
  sec = Math.max(0, Math.round(sec || 0));
  const m = Math.floor(sec / 60), s = sec % 60;
  return (m >= 60 ? Math.floor(m / 60) + ":" + String(m % 60).padStart(2, "0") : String(m)) + ":" + String(s).padStart(2, "0");
}

function phaseOf(d) {
  const lv = d.live;
  if (!lv) return "idle";
  if (!lv.block) return "finished";
  if (lv.block.type !== "exercise") return "timed";
  return lv.resting ? "rest" : "exercise";
}

const TOP = ["home", "calendar", "muscles"];
function nav(root, view, ctx) {
  const n = txt("div", "gy-nav");
  if (TOP.includes(view)) {
    const tabs = txt("div", "hb-tabs");
    for (const [v, label] of [["home", tt("tab_today", null, "Today")], ["calendar", tt("tab_calendar", null, "Calendar")],
      ["muscles", tt("tab_muscles", null, "Muscles")]]) {
      const t = txt("button", "hb-tab" + (view === v ? " is-on" : ""), label);
      t.type = "button"; t.setAttribute("aria-selected", view === v ? "true" : "false");
      t.onclick = () => go(v, null, ctx);
      tabs.appendChild(t);
    }
    n.appendChild(tabs);
  } else {
    const c = txt("nav", "hb-crumbs");
    const back = view === "exercise" && UI.from === "summary" ? "summary" : view === "summary" && UI.from === "calendar" ? "calendar" : "home";
    const a = txt("button", "hb-crumb", back === "calendar" ? tt("tab_calendar", null, "Calendar") : back === "summary" ? tt("workout", null, "Workout") : tt("tab_today", null, "Today"));
    a.type = "button";
    const backArg = back === "summary" ? UI.fromArg : null;
    a.onclick = () => go(back, backArg, ctx);
    c.appendChild(a);
    c.appendChild(txt("span", "hb-crumb-sep", "›"));
    c.appendChild(txt("span", "hb-crumb-cur", ({ preview: tt("v_preview", null, "Today's workout"), config: tt("my_gym", null, "My gym"),
      planner: tt("trainer", null, "Trainer"), program: tt("program", null, "Program"), summary: tt("workout", null, "Workout"),
      exercise: tt("v_exercise", null, "Exercise"), log: tt("log_manual", null, "Log a workout") })[view] || ""));
    n.appendChild(c);
  }
  root.appendChild(n);
}

const PAINT = { home, preview, calendar, muscles: musclesView, config, planner, program: programView, summary,
  exercise: exerciseHistory, log: logView };

export function render(el, data, ctx) {
  bindLang(ctx);
  injectStyles();
  el.className = "hb-gym";
  el.textContent = "";
  const d = data || {};
  if (typeof d.now === "number") S.offset = d.now - Date.now();
  UI.repaint = () => { if (el.isConnected) render(el, d, ctx); };
  // A view pushed by the brain (open_view, or the one an action leaves) is ONE transition, like a tap.
  if (UI.seenN === null) { UI.seenN = d.view_n || 0; if (d.view && d.view !== "home") { UI.view = d.view; UI.arg = d.view_arg || null; } }
  else if ((d.view_n || 0) !== UI.seenN) { UI.seenN = d.view_n || 0; UI.view = d.view || "home"; UI.arg = d.view_arg || null; UI.msg = null; UI.confirmDel = null; }
  let view = d.status === "onboarding" ? "onboarding" : d.status === "session" ? "session" : UI.view;
  if (view === "session" && d.status !== "session") view = "home";
  if (!PAINT[view] && view !== "onboarding" && view !== "session") view = "home";

  if (view !== "onboarding" && view !== "session") nav(el, view, ctx);
  if (UI.msg) el.appendChild(txt("div", "gy-msg", UI.msg));
  let timerEl = null;
  try {
    if (view === "onboarding") onboarding(el, d, ctx);
    else if (view === "session") timerEl = session(el, d, ctx, S);
    else PAINT[view](el, d, ctx);
  } catch (e) {
    el.appendChild(txt("div", "hb-empty-state", tt("broken", null, "This screen could not be drawn.")));
  }
  drive(ctx, d);
  startTick(el, d, ctx, timerEl);
  report(ctx, d, view);
}

// V2-884 — what the card SHOWS, after every paint: the screen, and in a session the phase, block, set and exercise.
function report(ctx, d, view) {
  if (!ctx || typeof ctx.state !== "function") return;
  const lv = d.live, b = lv && lv.block;
  const name = b ? String((b.name && (b.name.en || b.name)) || ((d.exercises || {})[b.key] || { name: {} }).name.en || b.key || b.type || "") : "";
  try {
    Promise.resolve(ctx.state({ view, phase: phaseOf(d), block: lv ? Math.min(200, lv.i || 0) : 0,
      set: lv ? Math.min(50, lv.set || 0) : 0, exercise: name.slice(0, 60) }, { applied: true, of: d })).catch(() => {});
  } catch (_) {}
}

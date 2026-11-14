// Gym — the guided session (the original app's session view): the block, its timer or the set tracker, rests, the actions
// and the alternatives. Everything the session IS lives in data.py (`live`); this paints it and sends his taps.
import { tt, loc, txt, btn, panel, img, clock, dayLabel, blockName, typeLabel, UI, act } from "./util.js";

// the original app's hrZone: % of the theoretical maximum (220 − age). Only with an age: a zone from a guessed age is a
// reading we do not have.
export function hrZone(bpm, age) {
  if (!bpm || !age) return null;
  const pct = bpm / (220 - age);
  if (pct < 0.5) return "rest";
  if (pct < 0.65) return "easy";
  if (pct < 0.78) return "aerobic";
  if (pct < 0.88) return "threshold";
  return "max";
}
function zoneLabel(z) {
  return ({ rest: tt("z_rest", null, "rest"), easy: tt("z_easy", null, "easy"), aerobic: tt("z_aerobic", null, "aerobic"),
    threshold: tt("z_threshold", null, "threshold"), max: tt("z_max", null, "max") })[z] || "";
}

export function timerLeft(t, offset) {
  if (!t) return 0;
  if (t.paused) return Math.max(0, t.left || 0);
  return Math.max(0, Math.round((t.ends_at - (Date.now() + offset)) / 1000));
}

function hrPill(lv, data) {
  if (lv.heart_rate == null) return null;
  const z = hrZone(lv.heart_rate, data.age);
  const p = txt("div", "gy-hr" + (z ? " gy-hr--" + z : ""));
  p.appendChild(txt("span", "gy-hr-icon", "♥"));
  p.appendChild(txt("strong", "gy-hr-bpm", String(lv.heart_rate)));
  p.appendChild(txt("span", "gy-muted", tt("bpm", null, "bpm") + (z ? " · " + zoneLabel(z) : "")));
  return p;
}

function twoTap(id, first, second, variant, run, extra) {
  return btn(UI.confirmDel === id ? second : first, variant, () => {
    if (UI.confirmDel === id) { UI.confirmDel = null; run(); }
    else { UI.confirmDel = id; if (UI.repaint) UI.repaint(); }
  }, extra);
}

function altPanel(lv, data, ctx) {
  const a = lv.alt;
  const p = panel("gy-alt");
  p.appendChild(txt("div", "hb-panel-title", tt("alt_title", null, "Replace exercise")));
  p.appendChild(txt("div", "gy-muted", tt("alt_instead", { name: blockName(lv.block, data) }, "Instead of: {name}")));
  if (a.current) {
    const c = txt("div", "hb-card gy-alt-card");
    const im = img(data, a.current.key, "gy-thumb", loc(a.current.name));
    if (im) c.appendChild(im);
    c.appendChild(txt("div", "gy-ex-name", loc(a.current.name)));
    const meta = [];
    if (a.current.sets) meta.push(a.current.sets + "×" + loc(a.current.reps));
    if (a.current.weight_initial_kg) meta.push(a.current.weight_initial_kg + " kg");
    if (a.current.duration_sec) meta.push(Math.round(a.current.duration_sec / 60) + " min");
    if (a.current.rest_sec) meta.push(tt("rest_s", { s: a.current.rest_sec }, "rest {s}s"));
    c.appendChild(txt("div", "gy-muted", meta.join(" · ")));
    if (a.current.why) c.appendChild(txt("div", "gy-muted", loc(a.current.why)));
    p.appendChild(c);
  } else {
    p.appendChild(txt("div", "gy-muted", a.model ? tt("alt_none", null, "No alternative could be proposed.")
      : tt("alt_exhausted", null, "No more alternatives in the list. The trainer will propose more once it is available.")));
  }
  const row = txt("div", "gy-row");
  const use = btn(tt("alt_use", null, "✓ Use this"), "primary", () => act(ctx, "use_alternative", {}));
  use.disabled = !a.current;
  row.appendChild(use);
  const other = btn(tt("alt_other", null, "↻ Another"), "secondary", () => act(ctx, "suggest_alternative", {}));
  other.disabled = !a.current;
  row.appendChild(other);
  row.appendChild(btn(tt("cancel", null, "Cancel"), "ghost", () => act(ctx, "close_alternatives", {})));
  p.appendChild(row);
  if ((a.rejected || []).length) p.appendChild(txt("div", "gy-muted", tt("alt_rejected", { list: a.rejected.join(", ") }, "Already rejected: {list}")));
  return p;
}

function stepper(ctx, label, value, step, field, delta) {
  const box = txt("div", "gy-input");
  box.appendChild(txt("label", "gy-muted", label));
  const row = txt("div", "gy-stepper");
  const minus = btn("−", "secondary", () => act(ctx, "set_values", { [delta]: -step }));
  minus.setAttribute("aria-label", tt("less", null, "Less"));
  const inp = txt("input", "hb-input gy-num");
  inp.type = "number"; inp.inputMode = "decimal"; inp.step = field === "reps" ? "1" : "0.5";
  inp.value = value == null ? "" : String(value);
  inp.onchange = () => act(ctx, "set_values", { [field]: inp.value === "" ? null : Number(inp.value) });
  const plus = btn("+", "secondary", () => act(ctx, "set_values", { [delta]: step }));
  plus.setAttribute("aria-label", tt("more", null, "More"));
  row.appendChild(minus); row.appendChild(inp); row.appendChild(plus);
  box.appendChild(row);
  return box;
}

// Paints the session; returns the element whose text the card's tick updates (the timer), or null.
export function session(root, data, ctx, S) {
  const lv = data.live;
  const head = txt("div", "gy-sess-head");
  const left = txt("div");
  left.appendChild(txt("div", "gy-muted", loc(lv.day_name)));
  left.appendChild(txt("div", "gy-sess-progress", lv.finished ? tt("all_blocks_done", null, "All blocks done")
    : tt("block_of", { i: lv.i + 1, n: lv.total }, "Block {i} / {n}")));
  head.appendChild(left);
  const elapsed = txt("div", "gy-elapsed", clock((Date.now() + S.offset - lv.started_at) / 1000));
  S.elapsedEl = elapsed;
  head.appendChild(elapsed);
  root.appendChild(head);

  if (lv.stale) {
    const b = panel("gy-stale");
    b.appendChild(txt("div", "gy-ex-name", tt("stale_title", null, "You have a workout in progress")));
    b.appendChild(txt("div", "gy-muted", tt("stale_since", { day: dayLabel(new Date(lv.started_at).toISOString().slice(0, 10)) }, "Started {day}")));
    const r = txt("div", "gy-row");
    r.appendChild(btn(tt("finish_here", null, "■ Finish here"), "secondary", () => act(ctx, "finish", { notes: "finished later" })));
    r.appendChild(twoTap("abort", tt("discard", null, "Discard"), tt("tap_again_discard", null, "Tap again to discard"), "danger",
      () => act(ctx, "abort", {})));
    b.appendChild(r);
    root.appendChild(b);
  }

  const hr = hrPill(lv, data);
  if (hr) root.appendChild(hr);

  const track = txt("div", "gy-progress");
  const fill = txt("div", "gy-progress-fill");
  fill.style.width = (lv.progress || 0) + "%";
  track.appendChild(fill);
  root.appendChild(track);

  if (!lv.finished) {
    const acts = txt("div", "gy-row gy-acts");
    if (lv.sets_count > 0) acts.appendChild(btn(tt("undo", null, "↶ Back"), "ghost", () => act(ctx, "undo_set", {}), "hb-btn--sm"));
    acts.appendChild(btn(tt("replace", null, "⇄ Replace"), "ghost", () => act(ctx, "suggest_alternative", {}), "hb-btn--sm"));
    if (lv.block && lv.block.type !== "transition") acts.appendChild(btn(tt("skip", null, "⤳ Skip"), "ghost", () => act(ctx, "skip_exercise", {}), "hb-btn--sm"));
    acts.appendChild(twoTap("end", tt("end", null, "■ End"), tt("tap_again_end", null, "Tap again to end"), "ghost",
      () => act(ctx, "end_early", {}), "hb-btn--sm"));
    if (lv.owner !== S.owner) {
      acts.appendChild(btn(tt("drive_here", null, "Drive from this screen"), "ghost",
        () => { S.tapped = true; ctx.action("claim", { owner: S.owner, force: true }); }, "hb-btn--sm"));
    }
    root.appendChild(acts);
  }
  if (lv.alt) root.appendChild(altPanel(lv, data, ctx));
  if (lv.note && lv.note.kind === "rest_extended") {
    root.appendChild(txt("div", "gy-note", tt("rest_extended", { bpm: lv.note.bpm, s: lv.note.seconds }, "♥ {bpm} still high · +{s}s rest")));
  }

  const b = lv.block;
  if (!b) {
    const fin = panel("gy-block gy-final");
    fin.appendChild(txt("div", "gy-day-name", tt("session_done", null, "Session complete")));
    fin.appendChild(txt("div", "gy-muted", tt("total_time", { t: elapsed.textContent }, "Total time: {t}")));
    fin.appendChild(btn(tt("save_exit", null, "Save and exit"), "primary", () => act(ctx, "finish", {}), "gy-cta"));
    root.appendChild(fin);
    return null;
  }
  if (b.type !== "exercise") {
    const card = panel("gy-block");
    card.appendChild(txt("span", "hb-badge hb-badge--info", typeLabel(b.type)));
    card.appendChild(txt("div", "gy-block-title", blockName(b, data)));
    if (b.cue) card.appendChild(txt("div", "gy-muted", loc(b.cue)));
    const timerEl = txt("div", "gy-big-timer", clock(timerLeft(lv.timer, S.offset)));
    card.appendChild(timerEl);
    const r = txt("div", "gy-row");
    const paused = !!(lv.timer && lv.timer.paused);
    r.appendChild(btn(paused ? tt("resume", null, "Resume") : tt("pause", null, "Pause"), "secondary",
      () => act(ctx, paused ? "resume_timer" : "pause_timer", {})));
    r.appendChild(btn(tt("start_now", null, "Start now ▸"), "primary", () => act(ctx, "next", {})));
    card.appendChild(r);
    root.appendChild(card);
    return timerEl;
  }

  let timerEl = null;
  const card = panel("gy-block");
  card.appendChild(txt("span", "hb-badge hb-badge--accent", typeLabel("exercise")));
  const im = lv.resting ? null : img(data, b.key || b.muscle_key, "gy-hero", blockName(b, data));   // the rest clock first
  if (im) card.appendChild(im);
  card.appendChild(txt("div", "gy-block-title", blockName(b, data)));
  card.appendChild(txt("div", "gy-set-progress", tt("set_of", { i: lv.set + 1, n: b.sets || 1 }, "Set {i} of {n}")));
  const targets = txt("div", "gy-targets");
  const tgt = (label, val) => { const t = txt("div", "hb-card gy-target"); t.appendChild(txt("div", "gy-muted", label)); t.appendChild(txt("div", "gy-target-val", val)); return t; };
  targets.appendChild(tgt(tt("reps_target", null, "Target reps"), loc(b.reps) || "—"));
  if (lv.last_weight != null) targets.appendChild(tgt(tt("last_time", null, "Last time"), lv.last_weight + " kg"));
  else if (b.weight_initial_kg) targets.appendChild(tgt(tt("suggested", null, "Suggested"), b.weight_initial_kg + " kg"));
  card.appendChild(targets);
  if (b.weight_hint) card.appendChild(txt("div", "gy-muted", loc(b.weight_hint)));

  if (!lv.resting) {
    const inputs = txt("div", "gy-inputs");
    inputs.appendChild(stepper(ctx, tt("weight_kg", null, "Weight (kg)"), lv.weight, 2.5, "weight_kg", "weight_delta"));
    inputs.appendChild(stepper(ctx, tt("reps_done", null, "Reps done"), lv.reps, 1, "reps", "reps_delta"));
    const rirBox = txt("div", "gy-input");
    rirBox.appendChild(txt("label", "gy-muted", tt("rir", null, "RIR (reps in reserve)")));
    const rir = txt("select", "hb-select");
    const none = txt("option", null, "—"); none.value = ""; rir.appendChild(none);
    for (let k = 0; k <= 5; k++) { const o = txt("option", null, String(k)); o.value = String(k); if (lv.rir === k) o.selected = true; rir.appendChild(o); }
    rir.onchange = () => act(ctx, "set_values", { rir: rir.value === "" ? null : Number(rir.value) });
    rirBox.appendChild(rir);
    inputs.appendChild(rirBox);
    card.appendChild(inputs);
    const done = btn(tt("done", null, "✓ DONE"), "primary", async () => {
      done.disabled = true;
      await act(ctx, "set_done", { i: lv.i });
    }, "gy-cta gy-done");
    card.appendChild(done);
  } else {
    const rest = txt("div", "gy-rest");
    rest.appendChild(txt("div", "gy-muted", tt("resting", null, "Rest")));
    timerEl = txt("div", "gy-big-timer", clock(timerLeft(lv.timer, S.offset)));
    rest.appendChild(timerEl);
    const r = txt("div", "gy-row");
    r.appendChild(btn(tt("minus_15", null, "−15s"), "secondary", () => act(ctx, "adjust_rest", { seconds: -15 })));
    r.appendChild(btn(tt("start_now", null, "Start now ▸"), "primary", () => act(ctx, "next", {})));
    r.appendChild(btn(tt("plus_15", null, "+15s"), "secondary", () => act(ctx, "adjust_rest", { seconds: 15 })));
    rest.appendChild(r);
    card.appendChild(rest);
  }
  root.appendChild(card);
  if ((lv.sets || []).length) {
    const so = panel();
    so.appendChild(txt("div", "hb-panel-title", tt("sets_so_far", null, "Sets so far")));
    for (const g of lv.sets) {
      so.appendChild(txt("div", "gy-muted", g.label + ") " + loc(g.name) + " · "
        + g.sets.map((s) => (s.reps ?? "—") + (s.weight_kg != null ? "×" + s.weight_kg + " kg" : "")).join(", ")));
    }
    root.appendChild(so);
  }
  return timerEl;
}

// Nutrition — the COACH screen (photos of a restaurant menu → what to order) and the EVALUATION screen (the week).
// Both answers come from a model through the app's one door; until it exists they say so and change nothing.

import { S, repaint } from "./state.js";
import { photoPicker, shrink } from "./today.js";
import { btn, errorText, fmtDay, fmtNum, h, localNow, tt } from "./ui.js";

const MAX_SHOTS = 5;

// «**Starter** — …» lines → paragraphs with a bold lead, built as DOM (no HTML from the model ever reaches the page).
export function richText(text) {
  const box = h("div", "nu-coach");
  for (const raw of String(text || "").split(/\n+/)) {
    const line = raw.replace(/^\s*[-•]\s+/, "");
    if (!line.trim()) continue;
    const p = h("p");
    const parts = line.split(/\*\*([^*]+)\*\*/);
    parts.forEach((part, i) => { if (part) p.appendChild(i % 2 ? h("strong", null, part) : document.createTextNode(part)); });
    box.appendChild(p);
  }
  return box;
}

function contextLine(d) {
  const day = (d.days || [])[d.days.length - 1] || {};
  const t = d.targets || {};
  if (!t.calories) return tt("no_day_data", null, "No data for today yet");
  return tt("coach_context", { a: fmtNum(day.kcal_in || 0), b: fmtNum(t.calories), m: fmtNum(Math.max(0, t.calories - (day.kcal_in || 0))) },
    "{a}/{b} kcal · margin ~{m}");
}

export function coachScreen(root, d, ctx) {
  const p = h("div", "nu-panel");
  p.appendChild(h("h4", null, tt("coach_title", null, "What should I order?")));
  p.appendChild(h("div", "nu-note", tt("coach_hint", null, "Take up to five photos of the menu; the advice takes into account what you have eaten today and your targets.")));
  p.appendChild(h("div", "nu-note", contextLine(d)));
  const shots = h("div", "nu-shots");
  S.coachShots.forEach((s, i) => {
    const im = h("img", "nu-thumb"); im.src = s.url; im.alt = tt("menu_photo_n", { n: i + 1 }, "Menu photo {n}");
    shots.appendChild(im);
  });
  if (S.coachShots.length < MAX_SHOTS) {
    shots.appendChild(photoPicker(tt("add_menu_photo", null, "📷 Menu photo"), true, (files) => {
      for (const f of files.slice(0, MAX_SHOTS - S.coachShots.length)) S.coachShots.push({ file: f, url: URL.createObjectURL(f) });
      repaint();
    }));
  }
  p.appendChild(shots);
  const ta = document.createElement("textarea");
  ta.className = "hb-textarea";
  ta.placeholder = tt("coach_ph", null, "Anything else? I trained this morning, I fancy fish…");
  ta.value = S.coachText;
  ta.oninput = () => { S.coachText = ta.value; };
  p.appendChild(ta);
  const row = h("div", "nu-row");
  row.appendChild(btn("hb-btn--secondary", tt("new_query", null, "New query"), () => {
    for (const s of S.coachShots) { try { URL.revokeObjectURL(s.url); } catch (_) {} }
    S.coachShots = []; S.coachText = ""; S.error = ""; repaint();
  }));
  row.appendChild(h("span", "nu-grow"));
  const ask = btn("hb-btn--primary", S.busy ? tt("thinking", null, "Thinking…") : tt("ask", null, "Ask"), async () => {
    if (!S.coachShots.length) return;
    S.busy = true; S.error = ""; repaint();
    const names = [];
    for (const s of S.coachShots) {
      const up = typeof ctx.upload === "function" ? await ctx.upload(await shrink(s.file)) : null;
      if (!up || up.error || !up.name) { S.busy = false; S.error = errorText("upload_failed"); repaint(); return; }
      names.push(up.name);
    }
    await ctx.action("coach_menu", { photos: names, context_text: S.coachText.trim(), lang: ctx.lang || "en", at: localNow() });
    S.busy = false; repaint();
  });
  ask.disabled = S.busy || !S.coachShots.length;
  row.appendChild(ask);
  p.appendChild(row);
  if (S.error) p.appendChild(h("div", "nu-warn", S.error));
  root.appendChild(p);
  const c = d.coach;
  if (c && (c.recommendation || c.error)) {
    const r = h("div", "nu-panel");
    r.appendChild(h("h4", null, tt("coach_answer", null, "Recommendation")));
    if (c.recommendation) r.appendChild(richText(c.recommendation));
    else r.appendChild(h("div", "nu-warn", errorText(c.error)));
    r.appendChild(h("div", "nu-note", fmtDay(c.asked_at)));
    root.appendChild(r);
  }
}

function evalCard(e, full) {
  const p = h("div", "nu-panel");
  const head = h("div", "nu-row");
  const sc = h("span", "nu-score"); sc.appendChild(h("b", null, e.score != null ? String(e.score) : "—")); sc.appendChild(h("span", "nu-note", "/100"));
  head.appendChild(sc);
  const cls = e.score == null ? "info" : e.score >= 80 ? "ok" : e.score >= 60 ? "warn" : "error";
  head.appendChild(h("span", "hb-badge hb-badge--" + cls, fmtDay(e.period_start) + " – " + fmtDay(e.period_end)));
  p.appendChild(head);
  if (e.summary) p.appendChild(h("div", null, e.summary));
  if (!full) return p;
  const sec = (title, items, mark) => {
    if (!(items || []).length) return;
    p.appendChild(h("h4", null, title));
    for (const s of items) p.appendChild(h("div", null, mark + " " + s));
  };
  sec(tt("strengths", null, "What is going well"), e.strengths, "✓");
  sec(tt("issues", null, "Problems"), e.issues, "⚠");
  if ((e.recommendations || []).length) {
    p.appendChild(h("h4", null, tt("recommendations", null, "Recommendations")));
    for (const r of [...e.recommendations].sort((a, b) => (a.priority || 3) - (b.priority || 3))) {
      const row = h("div", "nu-rec");
      row.appendChild(h("span", "hb-badge hb-badge--" + (r.priority === 1 ? "accent" : "bare"), tt("priority_n", { n: r.priority || 3 }, "P{n}")));
      const body = h("div");
      body.appendChild(h("div", null, r.action));
      if (r.why) body.appendChild(h("div", "nu-note", r.why));
      row.appendChild(body);
      p.appendChild(row);
    }
  }
  return p;
}

export function evaluationScreen(root, d, ctx) {
  const top = h("div", "nu-panel");
  top.appendChild(h("h4", null, tt("eval_title", null, "Weekly evaluation")));
  top.appendChild(h("div", "nu-note", tt("eval_hint", null, "A look at the last seven days: a score, what is going well, what is not, and small changes.")));
  const run = btn("hb-btn--primary", S.busy ? tt("evaluating", null, "Analysing your week…") : tt("evaluate", null, "Evaluate my week"), async () => {
    S.busy = true; repaint();
    await ctx.action("evaluate_week", { days: 7, lang: ctx.lang || "en" });
    S.busy = false; repaint();
  });
  run.disabled = S.busy;
  top.appendChild(run);
  if (d.evaluating && d.evaluating.error) top.appendChild(h("div", "nu-warn", errorText(d.evaluating.error)));
  root.appendChild(top);
  const list = d.evaluations || [];
  if (!list.length) root.appendChild(h("div", "hb-empty-state nu-note", tt("no_eval", null, "No evaluation yet")));
  else {
    root.appendChild(evalCard(list[0], true));
    if (list.length > 1) {
      root.appendChild(h("h4", null, tt("eval_history", { n: list.length - 1 }, "Earlier evaluations ({n})")));
      for (const e of list.slice(1)) root.appendChild(evalCard(e, false));
    }
  }
}

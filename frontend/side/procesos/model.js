// side/procesos/model.js — what each row of the «Procesos» column SAYS, with no DOM and no imports; the view paints it.

// The sub-tabs in his reading order: happening now, repeating, waiting for its moment. A task that ended is not one any
// more: it leaves the queue for his short-term memory (INI-078 Q-2), so there is no «done» tab.
export const SUBTABS = Object.freeze(["live", "recurring", "scheduled"].map((id) => {
  const k = "chat.sub" + id[0].toUpperCase() + id.slice(1);
  return { id, label: k, empty: k + "Empty" };
}));

export function dur(ms) {
  const s = Math.max(0, Math.round(ms / 1000)), m = Math.floor(s / 60);
  return s < 60 ? s + " s" : m < 60 ? m + " min" : Math.floor(m / 60) + " h " + (m % 60) + " min";
}

export function ago(ts, now, t) {           // `ts` in epoch seconds, like Python's time.time()
  if (!ts) return "";
  const s = Math.max(0, now / 1000 - Number(ts)), d = Math.floor(s / 86400);
  if (s < 60) return t("chat.agoNow");
  if (s < 3600) return t("chat.agoMinutes", { n: Math.floor(s / 60) });
  if (s < 86400) return t("chat.agoHours", { n: Math.floor(s / 3600) });
  return d === 1 ? t("chat.agoYesterday") : t("chat.agoDays", { n: d });
}

// The live row is the SAME row the orb's chips use, so the two cannot disagree about a running task. The table
// stores epoch SECONDS, the chip milliseconds.
export const taskToChip = (r) => ({
  id: r.id, session: r.session || "", title: r.title || r.goal || "", note: r.note || r.phase || "", num: r.num || null,
  queued: r.state === "pending",
  startedAt: r.started_at ? r.started_at * 1000 : null, pct: typeof r.pct === "number" ? r.pct : -1, stepTag: "",
  waiting: (r.state === "waiting" && r.waiting_for !== "reply") || r.waiting_on === "user", reply: r.waiting_for === "reply",
  paused: !!r.paused, internal: r.visible === false,
  silentS: typeof r.silent_s === "number" ? r.silent_s : 0, attempts: r.attempts || 0,
});

// V2-608 F7 — the title holds still; what the worker does now goes under it (only when it adds something), and the
// facts after, the state first as a pill. V2-776 D5: the pulse's view (silent a minute or more, restarted N times).
export function liveView(task, now, t, lang) {
  const k = task.waiting ? 0 : task.reply ? 1 : task.paused ? 2 : task.queued ? 4 : 3;     // reply: INI-042 #26
  // INI-078 S3 — its #number, the one the agent names it by: «stop the 7» is the same task here and there
  const title = (task.num ? "#" + task.num + " " : "") + ((task.title || "").trim() || (task.note || "").trim()
    || t("chat.working"));
  const note = (task.note || "").trim(), at = task.startedAt;
  const meta = [
    t(["chat.waitingYou", "chat.sentAwaitingReply", "chat.paused", "chat.running", "chat.queuedInLine"][k]),
    task.stepTag || "",
    (typeof task.pct === "number" && task.pct >= 0 ? task.pct + "%" : ""),
    at ? t("chat.procElapsed", { t: dur(now - at) }) : "",
    at ? t("chat.procSince", { t: new Date(at).toLocaleTimeString(lang || "en", { hour: "2-digit", minute: "2-digit" }) }) : "",
    (task.silentS >= 60 ? t("chat.procSilent", { t: dur(task.silentS * 1000) }) : ""),
    (task.attempts > 0 ? t("chat.procRestarted", { n: task.attempts }) : ""),
  ].filter(Boolean);
  return { cls: "live " + ["waiting", "reply", "paused", "run", "queued"][k], glyph: ["⏳", "✉", "⏸", "●", "◌"][k], title,
           note: note && note !== title ? note : "", meta };
}

// A periodic or timed row: its cadence and its next moment — «will this still happen, and when».
export function schedView(task, t, lang) {
  const sch = task.schedule || {}, next = sch.next_run ? new Date(sch.next_run * 1000) : null;
  const meta = [sch.display || "", next ? t("chat.taskNextRun", {
    t: next.toLocaleString(lang || "en", { weekday: "short", hour: "2-digit", minute: "2-digit" }) }) : ""];
  return { cls: "sched", glyph: "⏱", title: task.title || task.goal || task.id, meta: meta.filter(Boolean).join(" · ") };
}

// ============================================================================
// test_the_procesos_rows_say_what_happened.mjs — the «Procesos» column's model, under Node, with no DOM.
//
// What each row SAYS is decided in `frontend/side/procesos/model.js`; the view only paints it. Measured here:
//   · a finished row never lies: every ending has its glyph, an UNKNOWN one is «cut» (✂), never ✓;
//   · a running row's title holds still, its note shows only when it adds something, its state comes first;
//   · the pulse's view (silent for a minute, restarted N times) and why a row failed reach the facts line;
//   · a timed row says its cadence and its next moment; the table's seconds become the chip's milliseconds.
//
// Run: node tests/browser/unit/side_procesos/test_the_procesos_rows_say_what_happened.mjs
// ============================================================================
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "../../../..");
const M = await import(path.join(root, "frontend/side/procesos/model.js"));

// A `t` that shows which key was asked, with its params, so a word is measured by its key.
const t = (k, p) => (p ? `${k}(${Object.values(p).join(",")})` : k);
const NOW = 1_700_000_600_000;

// ── the sub-tabs, in his reading order: no «done» — an ended task leaves the queue (INI-078 Q-2) ──
assert.deepEqual(M.SUBTABS.map((s) => s.id), ["live", "recurring", "scheduled"]);
assert.equal(M.histView, undefined, "no row shape for a finished task: there is none to paint");

// ── a running row ──
const chip = M.taskToChip({ id: "a1", session: "s1", title: "w1 w2", phase: "w3", started_at: 1_700_000_000,
                            pct: 40, state: "running", silent_s: 75, attempts: 1 });
assert.equal(chip.startedAt, 1_700_000_000_000, "the table's seconds are the chip's milliseconds");
assert.equal(chip.note, "w3");
const live = M.liveView(chip, NOW, t, "en");
assert.equal(live.cls, "live run");
assert.equal(live.glyph, "●");
assert.equal(live.title, "w1 w2");
assert.equal(live.note, "w3");
assert.equal(live.meta[0], "chat.running", "the state comes first: it is the pill");
assert.ok(live.meta.includes("40%"));
assert.ok(live.meta.includes("chat.procElapsed(10 min)"), live.meta);
assert.ok(live.meta.some((m) => m.startsWith("chat.procSince(")), live.meta);
assert.ok(live.meta.includes("chat.procSilent(1 min)"), live.meta);
assert.ok(live.meta.includes("chat.procRestarted(1)"), live.meta);
assert.equal(M.liveView(M.taskToChip({ id: "a", title: "w1", phase: "w1" }), NOW, t, "en").note, "",
             "a note that repeats the title is not shown");
assert.equal(M.liveView(M.taskToChip({ id: "a", phase: "w5" }), NOW, t, "en").title, "w5", "no title: the note names it");
const waiting = M.liveView(M.taskToChip({ id: "a2", title: "w1", state: "waiting" }), NOW, t, "en");
assert.deepEqual([waiting.cls, waiting.glyph, waiting.meta[0]], ["live waiting", "⏳", "chat.waitingYou"]);
const reply = M.liveView(M.taskToChip({ id: "a3", title: "w1", state: "waiting", waiting_for: "reply" }), NOW, t, "en");
assert.deepEqual([reply.cls, reply.glyph, reply.meta[0]], ["live reply", "✉", "chat.sentAwaitingReply"],
                 "waiting for a third party's reply is not waiting for him");
assert.equal(M.liveView(M.taskToChip({ id: "a4", title: "w1", paused: true }), NOW, t, "en").glyph, "⏸");
assert.ok(!M.liveView(M.taskToChip({ id: "a5", title: "w1", silent_s: 30 }), NOW, t, "en").meta.some((m) => m.includes("procSilent")),
          "under a minute of silence says nothing");

// ── a timed row ──
const sched = M.schedView({ id: "c1", title: "w1", schedule: { display: "w2", next_run: 1_700_600_000 } }, t, "en");
assert.equal(sched.glyph, "⏱");
assert.ok(sched.meta.startsWith("w2 · chat.taskNextRun("), sched.meta);
assert.equal(M.schedView({ id: "c2", goal: "w3" }, t, "en").meta, "", "no schedule: no facts invented");

// ── the clocks ──
assert.equal(M.dur(42_000), "42 s");
assert.equal(M.dur(125 * 60_000), "2 h 5 min");
assert.equal(M.ago(0, NOW, t), "");
assert.equal(M.ago(NOW / 1000 - 86400 * 1.5, NOW, t), "chat.agoYesterday");
assert.equal(M.ago(NOW / 1000 - 86400 * 3, NOW, t), "chat.agoDays(3)");

console.log("ok — the procesos rows say what happened");

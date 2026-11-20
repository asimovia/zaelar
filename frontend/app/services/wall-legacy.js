// wall-legacy.js — the old path's lines on the chat wall, as actions with ids (INI-042 #49, the wall plan commit 3/5;
// `.meshkore/docs/modules/zaelar-chat-wall.md`). FlashBrain, the tasks, A2A, the old path's notices: their events become
// actions on lines this module names, through writers named `legacy:<source>` — never the manager's (`ear:`, `mouth`),
// and a keyboard only to acknowledge a typed line by its `cid` (`ackTyped`). An event the manager writes itself
// (`conv`) never reaches here. It imports nothing: the bridge attaches the wall (`attach`), the tests a bare model.
// The old rules moved here unchanged (they retire with the old path): his line in course is ONE line, partial to
// verdict (V2-647/743/745); our voiced line is owed until its voice starts it, crawls as heard and settles to what was
// heard (V2-745/747/752), the record matched by trace (V2-852 T12); the ladder for the rest compares with the LAST line.
// What the wall changes: a line's place is where it STARTS (§5.1), and a final line of ours only shortens (M5).
const MARKERS = /^(?:🔔|💬)\s*/;
const norm = (s) => String(s || "").replace(MARKERS, "").trim();
const lead = (s) => { const x = String(s || ""); return x.length - x.replace(MARKERS, "").trimStart().length; };
/** A screen's name as the engine cleans it (`voice/screens.clean`): the keyboard's writer is `keyboard:<this>`. */
export const cleanDevice = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9:_-]/g, "").slice(0, 40);
export const MAX_TEXT = 4000;            // the engine's own cut of a typed line (`entry.typed`): one door, one length
const QUEUED_MAX = 400;                  // actions kept while no wall is attached (a page still mounting)
const MUTED_MAX = 16;
const EARLY_CAPTION_MS = 30000;
// the voice went quiet: its line waits this long for its last caption before it settles. A final line only shortens
// (M5), and the caption that says all of it was heard can land just after the voice's own «idle».
export const IDLE_GRACE_MS = 1500;

export function createLegacyWall({ now = () => Date.now(), setTimer = setTimeout, clearTimer = clearTimeout } = {}) {
  let sink = null, wipe = null;
  const queued = [];
  let seq = 0;
  const lines = new Map();               // id → what this module knows of a line it wrote (or saw: `seen`)
  let order = [];                        // ids, in the wall's order (its own and the ones it saw appended)
  const changed = new Set();
  const counts = { extended: 0 };
  const id = (p) => `${p}_${now().toString(36)}${(++seq).toString(36)}`;

  function act(writer, op) {
    if (!sink) { queued.push([writer, op]); if (queued.length > QUEUED_MAX) queued.shift(); return { ok: true }; }
    try { return sink(writer, op) || { ok: true }; } catch (_) { return { ok: false, reason: "sink" }; }
  }
  const traceSet = () => new Set([...lines.values()].map((l) => l.trace).filter(Boolean));
  let told = "";
  const tell = () => {                     // the turns on the wall changed (an ask's anchor): said only then
    const k = [...traceSet()].sort().join("|");
    if (k === told) return;
    told = k;
    for (const fn of changed) { try { fn(); } catch (_) { /* a listener never breaks the wall */ } }
  };
  function add(writer, line) {
    const r = act(writer, { op: "append", ...line });
    if (r.ok === false) return null;
    lines.set(line.id, { ...line, writer });
    order.push(line.id);
    if (order.length > 600) { const gone = order.splice(0, order.length - 600); for (const g of gone) lines.delete(g); }
    tell();
    return line.id;
  }
  function edit(lid, change) {
    const l = lines.get(lid);
    if (!l || l.seen) return { ok: false, reason: "not_mine" };
    const { op = "update", cut, ...rest } = change;
    const r = act(l.writer, { op, id: lid, ...rest });
    if (r.ok === false) return r;
    if (op === "delete") { lines.delete(lid); order = order.filter((x) => x !== lid); tell(); }
    else Object.assign(l, rest, cut ? { cut: true } : {});
    return r;
  }
  const last = () => (order.length ? lines.get(order[order.length - 1]) : null);
  const lastHis = () => { for (let k = order.length - 1; k >= 0; k--) { const l = lines.get(order[k]); if (l && l.role === "you") return l.id; } return null; };

  // ── his line in course (the old path's caption, then his line) ──────────────────────────────────────────────
  let his = null;
  function setLiveChat(text) {
    const t = String(text || "").slice(0, MAX_TEXT);
    if (!t) return clearLiveChat();
    if (his && lines.has(his)) return void edit(his, { text: t });
    his = add("legacy:you", { id: id("h"), role: "you", state: "live", text: t, at: now() });
  }
  function clearLiveChat() {                 // the gate ruled the room, or it was delivered (then it is final already)
    const h = his; his = null;
    const l = h && lines.get(h);
    if (l && l.state !== "final") edit(h, { op: "delete" });
  }
  /** The gate released his words: the line he was saying becomes final with them, where it started. */
  function youSaid(text, at) {
    const t = String(text || "").slice(0, MAX_TEXT);
    if (his && lines.has(his)) { const h = his; his = null; return void edit(h, { text: t, state: "final", at }); }
    add("legacy:you", { id: id("y"), role: "you", state: "final", text: t, at });
  }

  // ── what the old path writes as it is ───────────────────────────────────────────────────────────────────────
  const NOTE_ROLES = new Set(["sys", "record", "peer"]);
  function pushChat(m) {
    if (!m || !m.role) return;
    if (m.role === "you") return void add("legacy:you", { id: id("y"), role: "you", state: "final", text: String(m.text || "").slice(0, MAX_TEXT), at: m.at || now() });
    if (m.role === "a2a") return void add("legacy:a2a", { id: id("a2a"), role: "box", kind: "a2a", data: m, text: String(m.text || ""), at: now() });
    if (m.role === "agent") return void pushAgentChat(m.text, m);
    if (NOTE_ROLES.has(m.role)) add("legacy:note", { id: id("n"), role: "note", kind: m.role, data: m, text: String(m.text || ""), at: now() });
  }
  /** An errand's reference box (V2-862): one box per task row, replaced in place by every later event of it. */
  function upsertChatRef(d) {
    const ref = String((d && d.ref) || "");
    if (!ref || d.label === "skipped") return;
    const row = { role: "ref", ref, text: String(d.title || d.text || ""), surface: String(d.surface || ""),
                  card: String(d.card || ""), state: String(d.state || "started"), file: String(d.file || "") };
    const lid = `ref_${ref}`, was = lines.get(lid);
    if (!was) return void add("legacy:ref", { id: lid, role: "box", kind: "ref", data: row, text: row.text, at: now() });
    const data = { ...was.data, ...row, text: row.text || was.data.text, card: row.card || was.data.card, file: row.file || was.data.file };
    edit(lid, { op: "replace", data, text: data.text });
  }
  /** A notice's 🔔 line (`notify`): one per notice, by its id — a retry of the same notice paints nothing new. */
  function notice(text, key) {
    if (key) { const lid = `notice_${key}`; if (lines.has(lid)) return; return void ladder("🔔 " + text, { lid }); }
    ladder("🔔 " + text, {});
  }
  /** F3-2: the engine's announcement of a typed line, with the screen's own id for it: the keyboard's line — on the
   *  screen that typed it, an acknowledgement; on every other, the same line. With no id (an engine before it), a line
   *  from another screen is written as his; this screen's own already is. */
  function ackTyped(text, cid, dev, me, clean = (s) => s) {
    const t = String(text || "").slice(0, MAX_TEXT);
    if (cid) return void act(`keyboard:${clean(dev || me)}`, { op: "append", id: cid, role: "you", state: "final", text: t, at: now() });
    if (dev && clean(dev) !== clean(me)) add("legacy:you", { id: id("y"), role: "you", state: "final", text: t, at: now() });
  }
  /** The open questions anchored on the wall: each a box of its own, appended when it opens, repainted in place,
   *  deleted when it closes. Open, so `live` — never kept across a reload: the questions come back from the engine. */
  function asks(open) {
    const want = new Map((open || []).map((a) => [`ask_${a.ask_id}`, a]));
    for (const [lid, l] of [...lines]) if (l.kind === "ask" && !want.has(lid)) edit(lid, { op: "delete" });
    for (const [lid, a] of want) {
      if (lines.has(lid)) edit(lid, { op: "replace", data: a });
      else add("legacy:ask", { id: lid, role: "box", kind: "ask", state: "live", data: a, text: String(a.text || ""), at: now() });
    }
  }
  /** A line some other writer appended (the keyboard, the manager): the ladder's «last line» is the wall's. */
  function seen(line) {
    if (!line || !line.id || lines.has(line.id)) return;
    lines.set(line.id, { id: line.id, role: line.role, text: String(line.text || ""), seen: true });
    order.push(line.id);
  }

  // ── our voiced line: owed, then written when the voice starts it ─────────────────────────────────────────────
  let capSeq = 0, owed = null, owedQueue = [], sounding = null, early = null;
  const muted = [];
  const mute = (tr) => { muted.push(tr); if (muted.length > MUTED_MAX) muted.shift(); };
  const isMuted = (tr) => !!tr && muted.includes(tr);
  const heardChars = (full, heard) => (heard ? lead(full) + norm(heard).length : 0);
  /** A line of ours, final unless said otherwise, named by the turn it belongs to. */
  const ours = (text, trace, more = {}) => add("legacy:agent", { id: id("a"), role: "agent", state: "final", text,
                                                                trace: trace || "", data: { trace: trace || "" }, at: now(), ...more });

  function paint(at) {                       // the voice STARTED it: now it is on the wall, live, and crawls
    const p = owed;
    if (!p || p.painted) return;
    p.painted = true;
    const re = lastHis();
    p.id = ours(p.full, p.trace, { state: "live", re: re ? [re] : [], at: Number(at) || now(),
                                   ...(p.heard ? { heard: heardChars(p.full, p.heard) } : {}) });
  }
  function crawl() { const p = owed; if (p && p.painted && p.id && p.heard) edit(p.id, { heard: heardChars(p.full, p.heard) }); }
  function promote() {
    if (owed || !owedQueue.length) return;
    owed = owedQueue.shift();
    if (sounding !== null && owed.trace && sounding === owed.trace) paint();
    claimEarly();
  }
  function noteVoiceStarted(trace, at) {
    if (owed && owed.painted && owedQueue.length && (trace || "") !== (owed.trace || "")
        && (!trace || !owedQueue[0].trace || owedQueue.some((q) => q.trace === trace))) settleAgentSpoken();
    const p = owed;
    if (!p || p.painted || (trace && p.trace && trace !== p.trace)) sounding = trace || "";
    if (!p || p.painted) return;
    if (p.trace && trace !== p.trace) { if (!trace) sounding = ""; return; }   // a notice's voice is not this turn's
    paint(at);
  }
  let idleTimer = null;
  function noteVoiceIdle() {
    sounding = null;
    if (!owed || !owed.painted) return;
    const p = owed;
    clearTimer(idleTimer);
    idleTimer = setTimer(() => { idleTimer = null; if (owed === p) settleAgentSpoken(); }, IDLE_GRACE_MS);
  }
  function dropUnspokenLine(trace) {
    if (trace) owedQueue = owedQueue.filter((q) => q.trace !== trace);
    const p = owed;
    if (!p || (trace && p.trace && trace !== p.trace)) return;
    if (p.painted) return void settleAgentSpoken();
    if (p.trace) mute(p.trace);
    owed = null;
  }
  function claimEarly() {
    const c = early, p = owed;
    if (!c || !p) return;
    if (now() - c.at > EARLY_CAPTION_MS) { early = null; return; }
    const h = norm(c.text);
    if (!h || !norm(p.full).startsWith(h)) return;
    early = null;
    noteSpokenAloud(c.text, false, true);
  }
  /** One audio-synced caption segment: what he is HEARING of our line, cumulative, `final` at its end. */
  function noteSpokenAloud(text, final, replay = false) {
    if (!replay) capSeq += 1;
    const h = norm(text);
    if (owed && h && !norm(owed.full).startsWith(h) && owedQueue.length && norm(owedQueue[0].full).startsWith(h)) settleAgentSpoken();
    if (!owed || !h || !norm(owed.full).startsWith(h)) { early = h && !final ? { text, at: now() } : null; return; }
    early = null;
    owed.heard = h;
    if (!owed.painted) paint(); else crawl();
    if (final) settleAgentSpoken();
  }
  function settleAgentSpoken() { clearTimer(idleTimer); idleTimer = null; settle(); promote(); }
  function settle() {
    const p = owed; owed = null;
    if (!p || !p.painted || !p.id) return;           // never painted = never said: it does not exist
    const full = norm(p.full), heard = norm(p.heard);
    if (!full || heard === full || (!heard && capSeq === p.capAt)) return void edit(p.id, { state: "final", heard: p.full.length });
    if (heard) return void edit(p.id, { state: "final", heard: heardChars(p.full, p.heard), cut: true });
    edit(p.id, { op: "delete" });                    // the voice demonstrably said something else
  }
  function agentByTrace(trace, full) {
    for (let k = order.length - 1; k >= 0; k--) {
      const l = lines.get(order[k]);
      if (l && !l.seen && l.role === "agent" && (trace ? l.trace === trace : norm(l.text) === full)) return l;
    }
    return null;
  }
  /** The spoken record writes its line: all of it, or what was said of it, marked cut. A record LONGER than the owed
   *  line is the line plus what the turn said after it (V2-850): a line still being said takes it whole; a settled one
   *  never grows (M5), so the tail is a line of its own, after it — never lost. */
  function fromSpoken(l, text) {
    const owedText = norm(l.text), said = norm(text);
    if (!said) return;
    if (said !== owedText && said.startsWith(owedText)) {
      if (l.state !== "final") return void edit(l.id, { text, state: "final", heard: String(text).length });
      counts.extended += 1;
      return void ours(said.slice(owedText.length).trim(), l.trace, { re: l.re || [] });
    }
    if (owedText === said) return void edit(l.id, { state: "final", heard: l.text.length });
    if (owedText.startsWith(said)) edit(l.id, { state: "final", heard: heardChars(l.text, text), cut: true });
  }
  function pushAgentChat(text, opts) {
    const o = opts || {};
    if (o.voiced && owed && owed.painted && (o.trace || "") !== (owed.trace || "") && norm(owed.heard) !== norm(owed.full)) {
      owedQueue.push({ full: text, heard: "", capAt: capSeq, trace: o.trace || "", painted: false });
      return;
    }
    if (o.voiced) settleAgentSpoken();
    if (o.voiced) {
      if (o.trace) for (const l of lines.values()) if (l.role === "agent" && l.trace === o.trace) l.trace = o.trace + "~";
      owed = { full: text, heard: "", capAt: capSeq, trace: o.trace || "", painted: false };
      if (sounding !== null && o.trace && sounding === o.trace) paint();
      claimEarly();
      return;
    }
    if (o.spoken && owed && !owed.painted && !isMuted(o.trace || "") && (!o.trace || !owed.trace || o.trace === owed.trace)
        && norm(text) && (norm(owed.full).startsWith(norm(text)) || norm(text).startsWith(norm(owed.full)))) {
      const p = owed;                                // a record of a line never matched to its start: it DID sound
      owed = null;
      const said = norm(text), cut = norm(p.full).startsWith(said) && norm(p.full) !== said;
      const re = lastHis();
      return void ours(cut ? p.full : text, p.trace, { re: re ? [re] : [], at: Number(o.at) || now(),
                                                       ...(cut ? { heard: heardChars(p.full, text) } : {}) });
    }
    if (o.spoken && o.trace && owedQueue.some((q) => q.trace === o.trace)) {
      owedQueue = owedQueue.filter((q) => q.trace !== o.trace);
      return void ours(text, o.trace, { at: Number(o.at) || now() });
    }
    if (o.spoken && o.trace && (isMuted(o.trace) || (owed && owed.trace === o.trace && !owed.painted))) {
      if (owed && owed.trace === o.trace) { mute(o.trace); owed = null; }
      return;
    }
    if (o.spoken && o.trace) {
      const l = agentByTrace(o.trace);
      if (l) { fromSpoken(l, text); if (owed && owed.trace === o.trace) owed = null; return; }
    }
    ladder(text, o);
  }
  /** What is not the voice's own line — a filler, a notice, a probe's text, a record with no trace — against the LAST
   *  line: the same text is already there; a record that is a prefix of it says the voice was cut there. */
  function ladder(text, o) {
    const l = last();
    if (l && l.role === "agent") {
      const a = norm(l.text), b = norm(text);
      if (a && b && a === b) return;
      if (a && b && o.spoken && a.startsWith(b)) { if (!l.seen) edit(l.id, { state: "final", heard: heardChars(l.text, text), cut: true }); owed = null; return; }
      if (a && b && a.startsWith(b)) return;
      if (a && b && b.startsWith(a)) counts.extended += 1;    // a final line never grows (M5): the longer one is its own
    }
    ours(text, o.trace, { ...(o.lid ? { id: o.lid } : {}), ...(o.kind ? { kind: o.kind, data: { trace: o.trace || "", kind: o.kind } } : {}),
                          at: Number(o.at) || now() });
  }

  return {
    attach(apply, clear) { sink = apply; wipe = clear || null; while (queued.length && sink) { const [w, op] = queued.shift(); act(w, op); } },
    detach() { sink = null; wipe = null; },
    onChange(fn) { changed.add(fn); return () => changed.delete(fn); },
    traces: traceSet,
    counts: () => ({ ...counts }),
    setLiveChat, clearLiveChat, youSaid, pushChat, upsertChatRef, notice, ackTyped, seen, asks,
    noteVoiceStarted, noteVoiceIdle, dropUnspokenLine, noteSpokenAloud: (t, f) => noteSpokenAloud(t, f), settleAgentSpoken,
    pushAgentChat,
    /** The reset: the wall is cleared and nothing of the old path's state survives it. */
    reset() {
      lines.clear(); order = []; his = null; owed = null; owedQueue = []; sounding = null; early = null;
      muted.length = 0; queued.length = 0;
      if (wipe) { try { wipe(); } catch (_) { /* the wall is the host's */ } }
      tell();
    },
  };
}

/** The app's one old-path writer: every module of the page writes through it; the bridge attaches the wall. */
export const legacy = createLegacyWall();

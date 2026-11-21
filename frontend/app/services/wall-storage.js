// wall-storage.js — where the chat wall keeps its final lines across a reload (INI-042 #49, the wall plan §3). Only
// final lines come back (M7). localStorage and not the server, as before (V2-681 T-1): it is the render buffer, and
// the conversation's record travels to memory by its own path. Every read and write is guarded: a private window or a
// blocked origin starts the wall blank, which is what it did before this existed.
//
// The old wall kept its rows under another key (`hb_chat_log`): they are moved over ONCE, each row a final line with
// its old place, and the old key is removed — so an update loses nothing he saw, and nothing visible changes. The cap
// is the old wall's (100 lines) and so is the byte budget. Imports nothing.
export const KEY = "hb_wall_lines";
export const OLD_KEY = "hb_chat_log";
export const CAP = 100;
const MAX_BYTES = 256000;               // what one browser keeps: past it the OLDEST lines go, never part of one
const NOTES = new Set(["sys", "record", "peer"]);

/** One row of the old wall → a final line of the component, owned as the old path owned it. */
export function fromOldRow(m, i) {
  const text = String(m.text || ""), base = { id: `old_${i}`, state: "final", text, at: Number(m.at) || 0 };
  const data = { ...m, text };
  if (m.role === "you") return { ...base, owner: "legacy:you", role: "you", ...(Array.isArray(m.att) && m.att.length ? { kind: "att", data } : {}) };
  if (m.role === "agent") return { ...base, owner: "legacy:agent", role: "agent", data: { trace: m.trace || "" } };
  if (m.role === "ref") return { ...base, owner: "legacy:ref", role: "box", kind: "ref", data };
  if (m.role === "a2a") return { ...base, owner: "legacy:a2a", role: "box", kind: "a2a", data };
  if (NOTES.has(m.role)) return { ...base, owner: "legacy:note", role: "note", kind: m.role, data };
  return null;
}

export function createWallStorage(ls = (typeof localStorage !== "undefined" ? localStorage : null), cap = CAP) {
  let at = 0;
  const read = (key) => { try { const raw = ls && ls.getItem(key); return raw ? JSON.parse(raw) : null; } catch (_) { return null; } };
  function migrate() {
    const old = read(OLD_KEY);
    const rows = old && Array.isArray(old.msgs) ? old.msgs.filter((m) => m && typeof m.text === "string") : [];
    const lines = rows.slice(-cap).map(fromOldRow).filter(Boolean);
    at = Number(old && old.at) || 0;
    if (lines.length) write(lines);
    try { ls && ls.removeItem(OLD_KEY); } catch (_) { /* nothing to remove */ }
    return lines;
  }
  function write(lines) {
    try {
      if (!ls) return;
      if (!lines.length) { ls.removeItem(KEY); return; }
      let xs = lines.slice(-cap);
      let body = JSON.stringify({ v: 2, at: Date.now(), lines: xs });
      while (body.length > MAX_BYTES && xs.length > 1) {       // over the budget: the oldest go, as the cap trims
        xs = xs.slice(Math.ceil(xs.length / 4));
        body = JSON.stringify({ v: 2, at: Date.now(), lines: xs });
      }
      ls.setItem(KEY, body);
    } catch (_) { /* quota, private window: the wall works, it just will not restore */ }
  }
  return {
    load() {
      const got = read(KEY);
      if (!got) return migrate();
      at = Number(got.at) || 0;
      return Array.isArray(got.lines) ? got.lines : [];
    },
    save: write,
    /** When the restored lines were kept (0: none), for the divider that says they were said earlier. */
    at: () => at,
  };
}

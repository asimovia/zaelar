// chat-wall/model.js — the wall's lines and the one door that changes them. No DOM, no imports.
//
// A line is { id, owner, role, state, re, n, at, text, heard, kind, data }:
//   · id     its identity, given by whoever creates it, never reused;
//   · owner  who created it — set HERE, from the writer that appended it, never from the action;
//   · role   "you" (his), "agent" (ours), "box" (a task, a question: drawn by a renderer), "note";
//   · state  "pending" (its place is kept, not shown yet) · "live" (being said) · "final";
//   · re     the ids it answers (ours);
//   · n      the order: a counter set at the append, never changed — the wall is in `n` order, never by time;
//   · at     the engine's time, only to show;
//   · heard  for a line of ours, how many characters of it sounded (undefined: all of it).
//
// Four actions, through a writer: append · update · replace · delete. Every refusal changes nothing, is counted and
// is told (`onRejected`). Invariants (M1–M9 of the plan; each has its test):
//   M2 only appended at the end; M3 a writer touches only its own lines; M4 a final line of his never changes;
//   M5 a final line of ours only shortens to what sounded; M6 nothing is found by text, prefix, position or time;
//   M9 a line with `re` comes after every line it names (a missing cause is counted, `cause_missing`).

export const ROLES = Object.freeze(["you", "agent", "box", "note"]);
export const STATES = Object.freeze(["pending", "live", "final"]);
const RANK = { pending: 0, live: 1, final: 2 };

export function createModel({ cap = 200, onChange = () => {}, onRejected = () => {} } = {}) {
  const byId = new Map();
  let order = [];                 // ids, in `n` order
  let next = 1;
  const counts = { rejected: 0, cause_missing: 0, trimmed: 0 };

  const reject = (op, owner, reason) => {
    counts.rejected += 1;
    counts[reason] = (counts[reason] || 0) + 1;     // by reason too: `final_grows` is read by its name
    onRejected({ reason, op: op && op.op, id: op && op.id, owner });
    return { ok: false, reason };
  };
  const copy = (l) => ({ ...l, re: [...l.re], data: l.data === undefined ? undefined : l.data });

  function append(owner, op) {
    const id = String(op.id || "");
    if (!id) return reject(op, owner, "no_id");
    const have = byId.get(id);
    if (have) {
      if (have.owner !== owner) return reject(op, owner, "not_owner");
      const same = (op.text === undefined || op.text === have.text) && (op.role === undefined || op.role === have.role);
      return same ? { ok: true, ack: true } : reject(op, owner, "id_taken");
    }
    const role = op.role || "note";
    if (!ROLES.includes(role)) return reject(op, owner, "bad_role");
    const state = op.state || "final";
    if (!STATES.includes(state)) return reject(op, owner, "bad_state");
    const re = Array.isArray(op.re) ? op.re.map(String) : (op.re ? [String(op.re)] : []);
    if (re.some((r) => !byId.has(r))) counts.cause_missing += 1;
    const line = { id, owner, role, state, re, n: next++, at: Number(op.at) || 0, text: String(op.text || ""),
                   heard: op.heard === undefined ? undefined : Math.max(0, Number(op.heard) || 0),
                   kind: op.kind, data: op.data };
    byId.set(id, line);
    order.push(id);
    const gone = [];
    while (order.length > cap) {
      const old = order.shift();
      byId.delete(old);
      gone.push(old);
      counts.trimmed += 1;
    }
    onChange({ op: "append", id, gone });
    return { ok: true };
  }

  function update(owner, op) {
    const line = byId.get(String(op.id || ""));
    if (!line) return reject(op, owner, "no_line");
    if (line.owner !== owner) return reject(op, owner, "not_owner");
    if (op.state !== undefined && (!STATES.includes(op.state) || RANK[op.state] < RANK[line.state])) {
      return reject(op, owner, "state_back");
    }
    if (line.state === "final") {
      if (line.role !== "agent") return reject(op, owner, "final");                          // M4
      const changes = op.text !== undefined && op.text !== line.text;
      const was = line.heard === undefined ? line.text.length : line.heard;
      const now = op.heard === undefined ? was : Math.max(0, Number(op.heard) || 0);
      if (changes || now > was) return reject(op, owner, "final_grows");                     // M5
      if (now === was) return { ok: true, ack: true };
      line.heard = now;
      onChange({ op: "update", id: line.id });
      return { ok: true };
    }
    if (op.text !== undefined) line.text = String(op.text);
    if (op.heard !== undefined) line.heard = Math.max(0, Number(op.heard) || 0);
    if (op.state !== undefined) line.state = op.state;
    if (op.at !== undefined) line.at = Number(op.at) || line.at;
    onChange({ op: "update", id: line.id });
    return { ok: true };
  }

  function replace(owner, op) {
    const line = byId.get(String(op.id || ""));
    if (!line) return reject(op, owner, "no_line");
    if (line.owner !== owner) return reject(op, owner, "not_owner");
    if (line.role !== "box") return reject(op, owner, "not_a_box");
    line.data = op.data;
    if (op.text !== undefined) line.text = String(op.text);
    onChange({ op: "replace", id: line.id });
    return { ok: true };
  }

  function remove(owner, op) {
    const line = byId.get(String(op.id || ""));
    if (!line) return reject(op, owner, "no_line");
    if (line.owner !== owner) return reject(op, owner, "not_owner");
    if (line.state === "final") return reject(op, owner, "final");
    byId.delete(line.id);
    order = order.filter((x) => x !== line.id);
    onChange({ op: "delete", id: line.id });
    return { ok: true };
  }

  const DOORS = { append, update, replace, delete: remove };

  function writer(owner) {
    const me = String(owner || "");
    if (!me) throw new Error("a writer has an owner");
    return Object.freeze({
      owner: me,
      apply(op) {
        if (!op || typeof op !== "object" || !DOORS[op.op]) return reject(op, me, "bad_op");
        if (op.owner !== undefined && op.owner !== me) return reject(op, me, "forged_owner");
        return DOORS[op.op](me, op);
      },
    });
  }

  return {
    writer,
    lines: () => order.map((id) => copy(byId.get(id))),
    line: (id) => (byId.has(String(id)) ? copy(byId.get(String(id))) : null),
    counts: () => ({ ...counts }),
    /** Only the reset clears the wall. */
    clear() {
      const gone = [...order];
      byId.clear();
      order = [];
      onChange({ op: "clear", gone });
    },
    /** Restored lines (final only, M7), in their order, owners as they were. */
    restore(lines) {
      for (const l of lines || []) {
        if (!l || l.state !== "final" || !l.id || byId.has(String(l.id))) continue;
        const line = { id: String(l.id), owner: String(l.owner || "restored"), role: ROLES.includes(l.role) ? l.role : "note",
                       state: "final", re: Array.isArray(l.re) ? l.re.map(String) : [], n: next++, at: Number(l.at) || 0,
                       text: String(l.text || ""), heard: l.heard, kind: l.kind, data: l.data, restored: true };
        byId.set(line.id, line);
        order.push(line.id);
        onChange({ op: "append", id: line.id, gone: [] });
      }
    },
  };
}

/** What is kept across a reload: the final lines only (M7). */
export const keepable = (lines) => lines.filter((l) => l.state === "final");

/** What a line shows: ours cut to what sounded, with «…» when it was cut. */
export function shown(line, cutMark = "…") {
  if (line.role === "agent" && line.heard !== undefined && line.heard < line.text.length) {
    return line.text.slice(0, line.heard) + (line.state === "final" ? cutMark : "");
  }
  return line.text;
}

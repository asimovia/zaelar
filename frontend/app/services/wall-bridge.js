// wall-bridge.js — the ONE file that knows both sides (INI-042 #49, the wall plan §3): the chat wall component
// (`frontend/chat-wall/`) and Zaelar's stream. It mounts the component, hands it the words, the look, the box renderers
// and the storage, gives every writer the stream names its own door, and carries the component's notices out:
//   · a `wall` event of the manager ({ writer, op }) → that writer's `apply(op)` — the component sets the owner;
//   · the old path's lines (`wall-legacy.js`) → the same doors, by the writers it names (`legacy:<source>`);
//   · `submit` → `send(text, id, extra)`: the line goes out with its own id, so the engine's acknowledgement of it
//     (written by this screen's keyboard, `keyboard:<device>`) is the same line, here and on every other screen.
// A line of his left open by a writer that never closed it (its event lost) is swept after `STALE_MS` with no news.
// Every action the wall refuses is reported (`report`: the host's debug stream), with the wall's counts.
// Nothing else imports the component (a static test holds it).
import { createChatWall } from "../../chat-wall/chat-wall.js";
import { legacy, MAX_TEXT } from "./wall-legacy.js?v=1";   // the page's one instance: every importer names ?v=1
import { clientLog } from "./api.js?v=2";

/** A refused action, on the session's debug stream (`/debug`), with the wall's counts (`final_grows`, …). */
const refused = (r, c) => clientLog("🧱 chat wall refused an action", { text: `${r.reason} · ${r.owner} · ${r.id || ""}`, state: JSON.stringify(c) });

export const STALE_MS = 60000;
const EARLY_MAX = 200;
let current = null;
const early = [];                       // the manager's actions that arrived before a wall was mounted

export function createWallBridge({ mount, device, labels = {}, renderers = {}, storage = null, send = () => {},
                                   cap = 200, input = true, format = null, classes = null, now = () => Date.now(),
                                   report = refused }) {
  const wall = createChatWall({ mount, labels, renderers, storage, cap, input, format, classes, maxText: MAX_TEXT,
                                keyboard: `keyboard:${device}` });
  const writers = new Map();
  const writer = (owner) => writers.get(owner) || writers.set(owner, wall.writer(owner)).get(owner);
  const open = new Map();               // a line of his still open (ear:*) → [its writer, its last news]
  let saying = null;                    // our line its voice is saying: { id, text, heard } — it grows as it sounds
  function apply(owner, op) {
    const r = writer(String(owner)).apply(op);
    if (r && r.ok && op.op === "append" && !String(owner).startsWith("legacy:")) legacy.seen(op);
    if (owner === "mouth" && r && r.ok && op.op === "append" && op.state === "live") saying = { id: op.id, text: String(op.text || ""), heard: 0 };
    if (owner === "mouth" && saying && op.id === saying.id && op.state === "final") saying = null;   // cut or done: frozen there
    if (String(owner).startsWith("ear:")) {
      if (op.op === "delete" || op.state === "final") open.delete(op.id);
      else open.set(op.id, [owner, now()]);
    }
    return r;
  }
  const sweep = () => {                 // his line no writer closed (its event lost): gone after STALE_MS with no news
    for (const [lid, [owner, at]] of [...open]) if (now() - at >= STALE_MS) { open.delete(lid); writer(owner).apply({ op: "delete", id: lid }); }
  };
  const sweeping = setInterval(sweep, Math.min(STALE_MS, 15000));
  wall.on("rejected", (r) => { try { report(r, wall.counts()); } catch (_) { /* a report never breaks the wall */ } });
  wall.on("submit", ({ id, text, ...extra }) => { legacy.seen({ id, role: "you", text }); send(text, id, extra); });
  legacy.attach(apply, () => { open.clear(); wall.clear(); });
  const api = {
    wall,
    /** One event of the stream: true when it was the wall's. */
    route(d) {
      if (!d || d.kind !== "wall" || !d.writer || !d.op) return false;
      apply(d.writer, d.op);
      return true;
    },
    submit: (text, extra) => wall.submit(text, extra),
    /** The voice's audio-synced caption of our line (what he has HEARD so far): the line shows that much, word by word. */
    heardAloud(text) {
      const n = saying ? spokenChars(saying.text, text) : 0;
      if (n > saying?.heard) { saying.heard = n; writer("mouth").apply({ op: "update", id: saying.id, heard: n }); }
    },
    sweep,
    destroy() {
      clearInterval(sweeping);
      legacy.detach();
      if (current === api) current = null;
      wall.destroy();
    },
  };
  current = api;
  while (early.length) api.route(early.shift());
  return api;
}

/** The stream's `wall` events reach the page's mounted wall (kept a moment if none is mounted yet). */
export function routeWall(d) {
  if (!d || d.kind !== "wall") return false;
  if (current) return current.route(d);
  early.push(d);
  if (early.length > EARLY_MAX) early.shift();
  return true;
}

/** How much of `line` the caption `heard` covers, in characters of `line`: its first words, compared word by word
 *  (case and punctuation aside); 0 when the caption is not the beginning of this line (a filler, another line). */
export function spokenChars(line, heard) {
  const word = (w) => w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
  const said = String(heard || "").split(/\s+/).map(word).filter(Boolean);
  const re = /\S+/g;
  let m, k = 0, end = 0;
  while (k < said.length && (m = re.exec(String(line || "")))) {
    if (!word(m[0])) { end = m.index + m[0].length; continue; }
    if (word(m[0]) !== said[k]) return k ? end : 0;
    k += 1; end = m.index + m[0].length;
  }
  return k ? end : 0;
}

/** The voice's caption of our line reaches the page's wall (`heardAloud`). */
export const heardAloud = (text) => current && current.heardAloud(text);

/** His typed line through the page's wall: the id it gets there is the one the engine acknowledges. Null: no wall. */
export const submitLine = (text, extra) => (current ? current.submit(text, extra) : null);

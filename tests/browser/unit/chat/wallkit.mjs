// wallkit.mjs — the old path's writer on the chat wall's own model, under Node, for the tests that pin how the old
// path writes the wall (INI-042 #49, the wall plan's commit 3/5). It loads the REAL `services/wall-legacy.js` and the
// REAL `chat-wall/model.js` — no slice of a file, no shim — and attaches one to the other exactly as the bridge does:
// every action through the writer it names, the owner set by the model.
//
//   const w = await wall();          // a fresh writer and wall
//   w.legacy.pushAgentChat(…); w.legacy.noteVoiceStarted(…);
//   w.lines()      → the model's lines, in order
//   w.said()       → what each line SHOWS ({ role, text }), ours cut to what sounded with «…»
//   w.counts()     → the model's refusals and missing causes
//   w.rejected     → every refusal, with its reason
//   w.flush()      → run the timers the writer set (the voice's idle grace), as if their time had come
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const legacyMod = await import(pathToFileURL(path.join(root, "frontend/app/services/wall-legacy.js")).href);
const modelMod = await import(pathToFileURL(path.join(root, "frontend/chat-wall/model.js")).href);

export async function wall({ now } = {}) {
  const rejected = [];
  const model = modelMod.createModel({ cap: 200, onRejected: (r) => rejected.push(r) });
  const writers = new Map();
  const writer = (o) => { if (!writers.has(o)) writers.set(o, model.writer(o)); return writers.get(o); };
  const timers = new Map();
  let tid = 0;
  const legacy = legacyMod.createLegacyWall({ ...(now ? { now } : {}),
    setTimer: (fn) => { timers.set(++tid, fn); return tid; }, clearTimer: (t) => timers.delete(t) });
  const flush = () => { for (const [t, fn] of [...timers]) { timers.delete(t); fn(); } };
  legacy.attach((owner, op) => writer(owner).apply(op), () => model.clear());
  const said = () => model.lines().filter((l) => !(l.state === "pending" && !l.text))
    .map((l) => ({ role: l.role, text: modelMod.shown(l), state: l.state }));
  return { legacy, model, writer, rejected, lines: () => model.lines(), said, counts: () => model.counts(), flush };
}

export const { shown } = modelMod;
export const { createLegacyWall, cleanDevice, IDLE_GRACE_MS } = legacyMod;

// wall-bridge.js — the ONE file that knows both sides (INI-042 #49, the wall plan §3): the chat wall component
// (`frontend/chat-wall/`) and Zaelar's stream. It mounts the component, hands it the words, the box renderers and the
// storage, gives every writer the stream names its own door, and carries the component's notices out:
//   · a `wall` event ({ writer, op }) → that writer's `apply(op)` — the component sets the owner, never the event;
//   · `submit` → `send(text, id)`: the line goes out with its own id, so the engine's acknowledgement of it (written
//     by this screen's keyboard, `keyboard:<device>`) is the same line, here and on every other screen.
// Nothing else imports the component (a static test holds it).
import { createChatWall } from "../../chat-wall/chat-wall.js";

export function createWallBridge({ mount, device, labels = {}, renderers = {}, storage = null, send = () => {} }) {
  const wall = createChatWall({ mount, labels, renderers, storage, keyboard: `keyboard:${device}` });
  const writers = new Map();
  const writer = (owner) => {
    if (!writers.has(owner)) writers.set(owner, wall.writer(owner));
    return writers.get(owner);
  };
  wall.on("submit", ({ id, text }) => send(text, id));
  return {
    wall,
    /** One event of the stream: true when it was the wall's. */
    route(d) {
      if (!d || d.kind !== "wall" || !d.writer || !d.op) return false;
      writer(String(d.writer)).apply(d.op);
      return true;
    },
    destroy: () => wall.destroy(),
  };
}

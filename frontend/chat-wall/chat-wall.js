// chat-wall/chat-wall.js — the chat wall as a component of its own (INI-042 #49). It imports nothing from outside
// this folder (M10): no store, no engine events, no strings, no widget. It mounts on a blank page and works.
//
//   createChatWall({ mount, labels, renderers, storage, cap, keyboard })
//     → { writer(owner), lines(), counts(), on(notice, fn), clear(), destroy() }
//   writer(owner) → { apply(op) }        op: { op: "append" | "update" | "replace" | "delete", id, … }
//
// In: one door, `apply`, always through a writer — the owner of a line is the writer that appended it, never a field
// of the action (a forged one is refused). Out: three notices and nothing else:
//   · submit   — he sent a text: { id, text }; the line is already on the wall, owned by the keyboard's writer
//                (`keyboard`, so the host acknowledges it with that same writer);
//   · action   — he pressed something inside a line (a box's button): { id, action };
//   · rejected — an action was refused: { reason, op, id, owner }.
// What it is handed and does not decide: the interface's words (`labels`), how each kind of box is drawn
// (`renderers`), where final lines are kept across a reload (`storage`: { load() → lines, save(lines) }).
import { createModel, keepable } from "./model.js";
import { createView } from "./view.js";

let _seq = 0;
const newId = (prefix) => `${prefix}_${Date.now().toString(36)}${(++_seq).toString(36)}`;

export function createChatWall({ mount, labels = {}, renderers = {}, storage = null, cap = 200,
                                 keyboard = "keyboard" } = {}) {
  if (!mount) throw new Error("createChatWall needs a mount element");
  const listeners = { submit: new Set(), action: new Set(), rejected: new Set() };
  const tell = (name, detail) => { for (const fn of listeners[name]) { try { fn(detail); } catch (_) { /* a listener never breaks the wall */ } } };

  const root = document.createElement("section");
  root.className = "cw-root";
  const list = document.createElement("div");
  list.className = "cw-list";
  list.setAttribute("role", "log");
  list.setAttribute("aria-live", "polite");
  const form = document.createElement("form");
  form.className = "cw-form";
  const box = document.createElement("textarea");
  box.className = "cw-input";
  box.rows = 1;
  box.placeholder = labels.placeholder || "";
  const send = document.createElement("button");
  send.type = "submit";
  send.className = "cw-send";
  send.textContent = labels.send || "Send";
  form.append(box, send);
  root.append(list, form);
  mount.appendChild(root);

  const view = createView({ list, renderers, labels, onAction: (d) => tell("action", d) });
  let saveTimer = null;
  const save = () => {
    if (!storage || typeof storage.save !== "function") return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => { try { storage.save(keepable(model.lines())); } catch (_) { /* storage is the host's */ } }, 50);
  };
  const model = createModel({
    cap,
    onRejected: (r) => tell("rejected", r),
    onChange: (c) => {
      for (const id of c.gone || []) view.remove(id);
      if (c.op === "append") view.append(model.line(c.id));
      else if (c.op === "update" || c.op === "replace") view.update(model.line(c.id));
      else if (c.op === "delete") view.remove(c.id);
      save();
    },
  });
  if (storage && typeof storage.load === "function") {
    try { model.restore(storage.load() || []); } catch (_) { /* a broken store restores nothing */ }
  }

  const keys = model.writer(keyboard);
  function submit(ev) {
    if (ev) ev.preventDefault();
    const text = box.value.trim();
    if (!text) return;
    box.value = "";                                            // the only thing the wall does to his box (M8)
    const id = newId("c");
    keys.apply({ op: "append", id, role: "you", state: "final", text, at: Date.now() });
    tell("submit", { id, text });
  }
  form.addEventListener("submit", submit);
  box.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) submit(ev);
  });

  return {
    writer: (owner) => model.writer(owner),
    lines: () => model.lines(),
    counts: () => model.counts(),
    node: (id) => view.node(id),
    on(name, fn) {
      if (!listeners[name]) throw new Error(`no notice named ${name}`);
      listeners[name].add(fn);
      return () => listeners[name].delete(fn);
    },
    clear() { model.clear(); view.clear(); save(); },
    destroy() {
      clearTimeout(saveTimer);
      root.remove();
      for (const s of Object.values(listeners)) s.clear();
    },
  };
}

// chat-wall/chat-wall.js — the chat wall as a component of its own (INI-042 #49). It imports nothing from outside
// this folder (M10): no store, no engine events, no strings, no widget. It mounts on a blank page and works.
//
//   createChatWall({ mount, labels, renderers, storage, cap, keyboard, input, maxText, format, classes })
//     → { writer(owner), lines(), counts(), on(notice, fn), submit(text, extra), clear(), destroy() }
//   writer(owner) → { apply(op) }        op: { op: "append" | "update" | "replace" | "delete", id, … }
//
// In: one door, `apply`, always through a writer — the owner of a line is the writer that appended it, never a field
// of the action (a forged one is refused). Out: three notices and nothing else:
//   · submit   — he sent a text: { id, text }; the line is already on the wall, owned by the keyboard's writer
//                (`keyboard`, so the host acknowledges it with that same writer);
//   · action   — he pressed something inside a line (a box's button): { id, action };
//   · rejected — an action was refused: { reason, op, id, owner }.
// What it is handed and does not decide: the interface's words (`labels`), how each kind of box is drawn
// (`renderers`), where final lines are kept across a reload (`storage`: { load() → lines, save(lines) }), how a line's
// body is drawn and which classes it wears (`format`, `classes`: the host's look; plain text and its own classes
// otherwise). `input: false`: the host keeps its own composer — `mount` is then the list itself, and the host's
// composer sends through `submit(text, extra)`, the same door the wall's own box uses. A line is cut at `maxText`
// before it is written, so the host's acknowledgement of it (cut the same way) is the same line.
import { createModel, keepable } from "./model.js";
import { createView } from "./view.js";

let _seq = 0;
const newId = (prefix) => `${prefix}_${Date.now().toString(36)}${(++_seq).toString(36)}`;

export function createChatWall({ mount, labels = {}, renderers = {}, storage = null, cap = 200,
                                 keyboard = "keyboard", input = true, maxText = 4000, format = null,
                                 classes = null } = {}) {
  if (!mount) throw new Error("createChatWall needs a mount element");
  const listeners = { submit: new Set(), action: new Set(), rejected: new Set() };
  const tell = (name, detail) => { for (const fn of listeners[name]) { try { fn(detail); } catch (_) { /* a listener never breaks the wall */ } } };

  const el = (tag, cls, props = {}) => Object.assign(document.createElement(tag), { className: cls }, props);
  const root = input ? el("section", "cw-root") : mount;
  const list = input ? el("div", "cw-list") : mount;
  list.setAttribute("role", "log");
  list.setAttribute("aria-live", "polite");
  const box = input ? el("textarea", "cw-input", { rows: 1, placeholder: labels.placeholder || "" }) : null;
  const form = input ? el("form", "cw-form") : null;
  if (input) {
    form.append(box, el("button", "cw-send", { type: "submit", textContent: labels.send || "Send" }));
    root.append(list, form);
    mount.appendChild(root);
  }

  const view = createView({ list, renderers, labels, format, classes, onAction: (d) => tell("action", d) });
  let saveTimer = null;
  let restoring = false;                     // what a reload restores is already kept: never written again (its time)
  const save = () => {
    if (restoring || !storage || typeof storage.save !== "function") return;
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
    restoring = true;
    try { model.restore(storage.load() || []); } catch (_) { /* a broken store restores nothing */ }
    restoring = false;
    view.restored(model.lines().filter((l) => l.restored).length);
  }

  const keys = model.writer(keyboard);
  /** His line, written by the keyboard's writer and told (`submit`): its id is the wall's, for the host to send. */
  function write(text, extra = {}) {
    const t = String(text || "").trim().slice(0, maxText);
    if (!t && !extra.data) return null;
    const id = newId("c");
    keys.apply({ op: "append", id, role: "you", state: "final", text: t, at: Date.now(),
                 ...(extra.kind ? { kind: extra.kind } : {}), ...(extra.data ? { data: extra.data } : {}) });
    tell("submit", { id, text: t, ...extra });
    return id;
  }
  function submit(ev) {
    if (ev) ev.preventDefault();
    if (!box.value.trim()) return;
    const text = box.value;
    box.value = "";                                            // the only thing the wall does to his box (M8)
    write(text);
  }
  if (form) {
    form.addEventListener("submit", submit);
    box.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) submit(ev);
    });
  }

  return {
    writer: (owner) => model.writer(owner),
    lines: () => model.lines(),
    counts: () => model.counts(),
    node: (id) => view.node(id),
    submit: write,
    on(name, fn) {
      if (!listeners[name]) throw new Error(`no notice named ${name}`);
      listeners[name].add(fn);
      return () => listeners[name].delete(fn);
    },
    clear() { model.clear(); view.clear(); save(); },
    destroy() {
      clearTimeout(saveTimer);
      if (input) root.remove(); else view.clear();
      for (const s of Object.values(listeners)) s.clear();
    },
  };
}

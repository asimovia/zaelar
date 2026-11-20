// chat-wall/view.js — the wall's lines on the page: one node per line id, for as long as the line exists (M1).
//
// A node is created when its line is appended and placed at the END of the list — never inserted above another one
// (M2). An update changes that node's text and classes in place; nothing is rebuilt. A `pending` line has its node
// (its place is kept) but it is not shown. A box is drawn by the renderer its `kind` names, handed in by the host.
// If he scrolled up to read, a change never moves the scroll; at the bottom, the wall follows the newest line.
import { shown } from "./model.js";

export function createView({ list, renderers = {}, labels = {}, onAction = () => {} }) {
  const nodes = new Map();          // line id → its element (M1)
  const NEAR = 24;                  // px from the bottom that still counts as «at the bottom»

  const atBottom = () => list.scrollHeight - list.scrollTop - list.clientHeight <= NEAR;

  function paint(el, line) {
    el.className = `cw-line cw-${line.role} cw-${line.state}` + (line.restored ? " cw-restored" : "");
    el.dataset.state = line.state;
    el.hidden = line.state === "pending";
    if (line.role === "box") {
      const draw = renderers[line.kind];
      const inner = draw ? draw(line.data, (action) => onAction({ id: line.id, action }), line) : null;
      el.replaceChildren(...(inner ? [inner] : []));
      if (!inner) el.textContent = line.text;
      return;
    }
    const text = el.firstChild && el.firstChild.nodeType === 3 ? el.firstChild : document.createTextNode("");
    text.nodeValue = shown(line, labels.cut || "…");
    if (el.firstChild !== text) el.replaceChildren(text);
  }

  return {
    append(line) {
      const follow = atBottom();
      const el = document.createElement("div");
      el.dataset.id = line.id;
      paint(el, line);
      list.appendChild(el);
      nodes.set(line.id, el);
      if (follow) list.scrollTop = list.scrollHeight;
    },
    update(line) {
      const el = nodes.get(line.id);
      if (!el) return;
      const follow = atBottom();
      paint(el, line);
      if (follow) list.scrollTop = list.scrollHeight;
    },
    remove(id) {
      const el = nodes.get(id);
      if (el) el.remove();
      nodes.delete(id);
    },
    node: (id) => nodes.get(String(id)) || null,
    clear() {
      for (const el of nodes.values()) el.remove();
      nodes.clear();
    },
  };
}

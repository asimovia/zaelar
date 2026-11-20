// chat-wall/view.js — the wall's lines on the page: one node per line id, for as long as the line exists (M1).
//
// A node is created when its line is appended and placed at the END of the list — never inserted above another one
// (M2). An update changes that node's text and classes in place; nothing is rebuilt. A `pending` line has its node
// (its place is kept): with no words yet it is not shown, with words it is shown dimmed (not judged yet). A box is
// drawn by the renderer its `kind` names, handed in by the host; any other line by the host's `format` (its body),
// or as plain text. If he scrolled up to read, a change never moves the scroll; at the bottom, the wall follows the
// newest line. After the lines a reload restored, one divider says they were said earlier (`labels.earlier`).
import { shown } from "./model.js";

export function createView({ list, renderers = {}, labels = {}, format = null, classes = null, onAction = () => {} }) {
  const nodes = new Map();          // line id → its element (M1)
  const NEAR = 24;                  // px from the bottom that still counts as «at the bottom»

  const atBottom = () => list.scrollHeight - list.scrollTop - list.clientHeight <= NEAR;

  function paint(el, line) {
    const extra = classes ? classes(line) : "";
    el.className = `cw-line cw-${line.role} cw-${line.state}` + (line.restored ? " cw-restored" : "") + (extra ? " " + extra : "");
    el.dataset.state = line.state;
    el.hidden = line.role !== "box" && !shown(line, "");    // nothing said yet (his voice rising, ours not heard)
    if (line.role === "box") {
      const draw = renderers[line.kind];
      const inner = draw ? draw(line.data, (action) => onAction({ id: line.id, action }), line) : null;
      el.replaceChildren(...(inner ? [inner] : []));
      if (!inner) el.textContent = line.text;
      return;
    }
    const said = shown(line, labels.cut || "…");
    const body = format ? format(line, said) : null;
    if (body) { el.replaceChildren(body); return; }
    const text = el.firstChild && el.firstChild.nodeType === 3 ? el.firstChild : document.createTextNode("");
    text.nodeValue = said;
    if (el.firstChild !== text) el.replaceChildren(text);
  }
  let divider = null;

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
    /** `n` lines were restored by a reload: one divider after them says so (none when nothing was). */
    restored(n) {
      if (!n || divider) return;
      divider = document.createElement("div");
      divider.className = "cw-earlier";
      divider.textContent = labels.earlier || "";
      list.appendChild(divider);
    },
    clear() {
      for (const el of nodes.values()) el.remove();
      nodes.clear();
      if (divider) { divider.remove(); divider = null; }
    },
  };
}

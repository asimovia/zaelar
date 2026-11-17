// menu-row.js — one row of the ☰ page and of the pages it opens: an outline icon (app/lib/icons.js, the shell's one
// visual language), bold label, quiet subtitle, chevron. `label`/`sub` may be a string OR a function — a function is a
// reactive binding (core/dom.js), which is how a row's subtitle can track a signal (the current voice, say) without
// the row knowing which signal it was. `tone` "danger" paints the label in the warning colour.
import { h, raw } from "../../../app/core/dom.js?v=2";
import { CHEVRON_RIGHT_ICON } from "../../../app/lib/icons.js?v=2";

export function Row(icon, label, sub, onClick, tone = "") {
  return h("button", { class: "zm-row" + (tone ? " zm-row-" + tone : ""), onClick },
    icon ? h("span", { class: "zm-row-i", "aria-hidden": "true" }, raw(icon)) : null,
    h("span", { class: "zm-row-t" },
      h("b", null, label),
      sub ? h("small", null, sub) : null,
    ),
    h("span", { class: "zm-row-c", "aria-hidden": "true" }, raw(CHEVRON_RIGHT_ICON)),
  );
}

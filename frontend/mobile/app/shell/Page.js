// Page.js — every shell surface on the phone is a PAGE (V2-876 D-A/D-D, operator 2026-11-11: «las apps van a pantalla
// completa… no ocupan full screen, queda vacío por arriba y parece un contenido que sube desde abajo»): the whole
// screen from the status bar to the dock, one header (‹ back · title · × close, the card header's shape, V2-699),
// a body that scrolls, no handle, no half height, no slide from below. Pages never stack: main.js keeps one open, and
// a page opened FROM another (settings, feedback from the menu) replaces it and its ‹ goes back to it.
import { h, raw } from "../../../app/core/dom.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";

const SW = `viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"`;
const BACK = `<svg ${SW}><path d="m15 5-7 7 7 7"/></svg>`;
const X = `<svg ${SW}><path d="M6 6l12 12"/><path d="M18 6 6 18"/></svg>`;

/** `open` a signal accessor; `back` (optional) returns to the page this one was opened from; `scroll: false` when the
 *  page brings its own scroller (the chat's message list). Extra attributes (role…) go on the section. */
export function Page({ id, open, title, close, back = null, scroll = true, attrs = {} }, ...children) {
  return h("section", {
    ...attrs, class: () => "zm-page zm-" + id + (open() ? " open" : ""), "data-page": id,
    "aria-hidden": () => (open() ? "false" : "true"),
  },
    h("header", { class: "zm-page-h" },
      back ? h("button", { class: "zm-page-btn zm-page-back", "aria-label": () => t("mobile.back"), onClick: back }, raw(BACK))
           : h("span", { class: "zm-page-btn" }),
      h("h2", null, title),
      close ? h("button", { class: "zm-page-btn zm-page-x", "aria-label": () => t("desktop.close"), onClick: close }, raw(X))
            : h("span", { class: "zm-page-btn" })),
    scroll ? h("div", { class: "zm-page-b" }, ...children) : children);
}

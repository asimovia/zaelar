// feedback-sent-note.js — what a SENT report leaves on screen once its window has closed (2026-10-25).
//
// The operator: «cuando mandamos algo, se debe limpiar el form, y cerramos el form window». A send that worked
// now clears the form and closes it, on the desktop panel and on the phone sheet alike — so the thank-you can no
// longer live inside the panel, which is gone the moment it would show. It lives here instead: one short line,
// bottom-left, that leaves on its own. Both shells call this one function; neither keeps a copy.

let timer = null;

/** Show `text` for a few seconds as a polite status line. A second call replaces the first. */
export function noteSent(text, ms = 3500) {
  if (typeof document === "undefined" || !text) return;
  let el = document.querySelector(".hb-sent-note");
  if (!el) {
    el = document.createElement("div");
    el.className = "hb-sent-note";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    document.body.appendChild(el);
  }
  el.textContent = text;
  el.classList.add("on");
  clearTimeout(timer);
  timer = setTimeout(() => el.classList.remove("on"), ms);
}

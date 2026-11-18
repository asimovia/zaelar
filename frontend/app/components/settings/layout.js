// Settings layout — the ONE page shape every ⚙ Settings area is drawn with, so no section builds its own header,
// rows or buttons. A page is: a header (breadcrumb · title · one line), groups of rows (a fixed label column, the
// field beside it, stacked on a phone), and an action bar at the bottom right. A page that edits values carries
// Cancel + Save; both stay disabled until a field differs from what was loaded, Cancel puts the loaded values back
// and Save says its result in the bar. Controls that apply at once (a microphone, the language) are marked
// `data-set-live` and never make the page dirty. Styles: `.set-*` in styles.css, sized by the `--st-*` tokens.
import { t } from "../../core/i18n.js?v=1";

export const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/** A button in the house metrics. kind: "primary" | "secondary". `attrs` is raw attribute text. */
export const btn = (label, { kind = "secondary", cls = "", attrs = "" } = {}) =>
  `<button type="button" class="set-btn set-btn--${kind}${cls ? " " + cls : ""}" ${attrs}>${esc(label)}</button>`;

/** One setting: the label in the fixed column, the control (+ an optional hint under it) beside it. */
export const row = (label, ctl, hint, forId) =>
  `<div class="set-row"><label class="set-label"${forId ? ` for="${esc(forId)}"` : ""}>${esc(label)}</label>` +
  `<div class="set-ctl">${ctl}${hint ? `<span class="set-hint">${hint}</span>` : ""}</div></div>`;

/** A group of rows, with an optional small heading and an optional note under it. */
export const group = (rows, { title = "", note = "", attrs = "" } = {}) =>
  `<div class="set-group" ${attrs}>${title ? `<h3 class="set-group-h">${esc(title)}</h3>` : ""}` +
  `<div class="set-rows">${rows}</div>${note ? `<p class="set-hint set-group-note">${esc(note)}</p>` : ""}</div>`;

/** The bottom bar. `form` adds Cancel + Save (disabled until something changes); `tools` are secondary buttons
 * on the left of it (Refresh, Restore default…). Every page has the status line, so a result is said in place. */
export const actions = ({ form = false, tools = "" } = {}) =>
  `<footer class="set-actions"><div class="set-tools">${tools}</div><span class="set-status" role="status" aria-live="polite"></span>` +
  (form ? btn(t("settings.form.cancel"), { attrs: "data-set-cancel disabled" }) +
    btn(t("settings.form.save"), { kind: "primary", attrs: "data-set-save disabled" }) : "") + `</footer>`;

/** The page. `crumb` is the trail after «Settings»; `id` names the page for the tests and the wiring. `after` is a
 * block that is NOT saved by this page's bar (it acts on its own), drawn below the bar so the bar is not read as its. */
export const page = ({ id, crumb = [], title, sub = "", body = "", form = false, tools = "", after = "" }) =>
  `<section class="set-page" data-settings-page="${esc(id)}" id="cf_${esc(id)}"><header class="set-head">` +
  `<nav class="set-crumb" aria-label="breadcrumb"><span>${esc(t("config.tab.settings"))}</span>` +
  crumb.map((c, i) => `<span class="set-crumb-sep" aria-hidden="true">›</span>${i === crumb.length - 1 ? `<b>${esc(c)}</b>` : `<span>${esc(c)}</span>`}`).join("") +
  `</nav><h2 class="set-title">${esc(title)}</h2>${sub ? `<p class="set-sub">${esc(sub)}</p>` : ""}</header>` +
  `<div class="set-body">${body}</div>${actions({ form, tools })}${after ? `<div class="set-body set-after">${after}</div>` : ""}</section>`;

/** Writes a result into the bar of the page on screen (kind: "" | "ok" | "error" | "busy"). */
export function say(scope, text, kind = "") {
  const el = scope && scope.querySelector(".set-status");
  if (!el) return false;
  el.textContent = text || "";
  el.className = "set-status" + (kind ? " is-" + kind : "");
  return true;
}

const isLive = el => !!(el && el.closest && el.closest("[data-set-live]"));
const read = el => (el.type === "checkbox" || el.type === "radio") ? el.checked : el.value;

/** Wires a page's Cancel + Save. `save(changed)` gets the fields that differ and returns {ok, message} (or throws);
 * `reset()` restores the loaded values (default: write the snapshot back into the fields). */
export function bindForm(root, { save, reset } = {}) {
  const bar = root && root.querySelector(".set-actions");
  const saveB = bar && bar.querySelector("[data-set-save]"), cancelB = bar && bar.querySelector("[data-set-cancel]");
  if (!saveB || !cancelB) return null;
  const fields = () => [...root.querySelectorAll(".set-body input[id], .set-body select[id], .set-body textarea[id]")].filter(el => !isLive(el));
  let base = new Map();
  const snap = () => { base = new Map(fields().map(el => [el.id, read(el)])); };
  const changed = () => fields().filter(el => !base.has(el.id) || base.get(el.id) !== read(el));
  const sync = () => {
    const dirty = changed().length > 0;
    saveB.disabled = cancelB.disabled = !dirty;
    root.classList.toggle("is-dirty", dirty);
    return dirty;
  };
  const onEdit = e => { if (isLive(e.target)) return; say(root, ""); sync(); };
  root.addEventListener("input", onEdit);
  root.addEventListener("change", onEdit);
  cancelB.onclick = () => {
    if (reset) { reset(); return; }
    fields().forEach(el => { if (!base.has(el.id)) return; if (el.type === "checkbox" || el.type === "radio") el.checked = base.get(el.id); else el.value = base.get(el.id); });
    say(root, ""); sync();
  };
  saveB.onclick = async () => {
    saveB.disabled = cancelB.disabled = true;
    say(root, t("settings.form.saving"), "busy");
    let r;
    try { r = await save(changed()); } catch (e) { r = { ok: false, message: (e && e.message) || "" }; }
    // A save may rebuild the page; the result is said on whichever page is on screen now.
    const here = root.isConnected ? root : document.querySelector(`.set-page[data-settings-page="${root.dataset.settingsPage}"]`);
    if (r && r.ok === false) { say(here, "✗ " + (r.message || t("settings.form.error")), "error"); if (root.isConnected) sync(); return; }
    if (root.isConnected) { snap(); sync(); }
    say(here, "✓ " + ((r && r.message) || t("settings.form.saved")), "ok");
  };
  snap(); sync();
  return { snap, sync, changed };
}

// PermissionsSection — ⚙ Settings → Permissions (V2-875): the person's switches, the same four the phone's Settings
// shows (services/privacy.js): location → the agent's state, reading files (the master key above the daemon's
// folder grants), keeping the agent's events for debugging, and tagging personal data in what is kept. One row each,
// label then control (cf-row2, CRIT-K19); the engine has the value before the box changes.
import * as privacy from "../services/privacy.js?v=1";
import { t } from "../core/i18n.js?v=1";

const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export function mountPermissions(host, msg, cfg) {
  if (!host) return;
  if (cfg) privacy.loadFrom(cfg);
  const v = privacy.values();
  host.innerHTML = `<section class="cf-panel-sec"><header class="cf-panel-head"><h4>${esc(t("config.sec.permissions"))}</h4>` +
    `<p>${esc(t("config.perm.sub"))}</p></header><div class="cf-group">` +
    privacy.KEYS.map((k) => `<div class="cf-row2"><label class="cf-row2-label" for="cf_perm_${k}">${esc(t(`config.perm.${k}`))}</label>` +
      `<div class="cf-row2-ctl"><input type="checkbox" id="cf_perm_${k}" data-perm="${k}"${v[k] ? " checked" : ""}/>` +
      `<span class="cf-hint">${esc(t(`config.perm.${k}_hint`))}</span></div></div>`).join("") +
    `</div></section>`;
  host.querySelectorAll("input[data-perm]").forEach((box) => box.addEventListener("change", async () => {
    const ok = await privacy.set(box.dataset.perm, box.checked);
    if (!ok) box.checked = !box.checked;
    if (msg) msg(ok ? t("config.perm.saved") : t("config.perm.failed"), !ok);
  }));
}

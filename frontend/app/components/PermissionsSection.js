// PermissionsSection — ⚙ Settings → Permissions (V2-875): the person's switches, the same four the phone's Settings
// shows (services/privacy.js): location → the agent's state, reading files (the master key above the daemon's
// folder grants), keeping the agent's events for debugging, and tagging personal data in what is kept. One row
// each, drawn with the Settings layout; a change waits for the page's Save, and Cancel puts the switches back.
import * as privacy from "../services/privacy.js?v=1";
import { t } from "../core/i18n.js?v=1";
import { row, group, bindForm } from "./settings/layout.js?v=1";

export function mountPermissions(host, msg, cfg, pageEl) {
  if (!host) return;
  if (cfg) privacy.loadFrom(cfg);
  const draw = () => {
    const v = privacy.values();
    host.innerHTML = group(privacy.KEYS.map((k) => row(t(`config.perm.${k}`),
      `<input type="checkbox" id="cf_perm_${k}" data-perm="${k}"${v[k] ? " checked" : ""}/>`, t(`config.perm.${k}_hint`), `cf_perm_${k}`)).join(""));
  };
  draw();
  if (!pageEl) return;
  const form = bindForm(pageEl, {
    save: async (changed) => {
      for (const box of changed) if (!(await privacy.set(box.dataset.perm, box.checked))) { draw(); form.snap(); form.sync(); return { ok: false, message: t("config.perm.failed") }; }
      return { ok: true, message: t("config.perm.saved") };
    },
    reset: () => { draw(); form.sync(); },
  });
}

// RulesSection — ⚙ Settings → Rules (V2-806): his standing rules and preferences, ONE table, grouped by scope.
// Each row reads his own words (or the key it sets), its value, and where it came from: «yours» or «default».
// His rows can be edited, switched off and deleted; a default can be edited — that writes a row of his at the
// same scope, and the factory row stays. Drawn with the Settings layout (`settings/layout.js`): edits wait for the
// page's Save, Cancel puts the listed values back; Delete acts at once. The server checks every value against its
// key's domain (`rules/api.py`).
import * as api from "../services/api.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { esc, row, group, btn, bindForm } from "./settings/layout.js?v=1";

function control(r) {
  const id = `cf_rule_${esc(r.id)}`;
  const opts = r.choices;           // the closed set the server says this key admits, or null for free text
  if (opts) {
    return `<select id="${id}" class="cf-rule-val" data-rule="${esc(r.id)}" data-type="${typeof r.value}">` +
      opts.map(o => `<option value="${esc(o)}"${o === r.value ? " selected" : ""}>${esc(t(`config.rules.v.${o}`))}</option>`).join("") +
      `</select>`;
  }
  return `<input id="${id}" class="cf-rule-val" data-rule="${esc(r.id)}" data-type="${typeof r.value}" value="${esc(r.value)}"/>`;
}

function rowHtml(r) {
  const mine = r.source === "user";
  const until = r.until ? " · " + t("config.rules.until", { at: new Date(r.until * 1000).toLocaleString() }) : "";
  const except = (r.except_labels || []).length ? " · " + t("config.rules.except", { what: r.except_labels.join(", ") }) : "";
  const hint = (mine ? t("config.rules.mine") : t("config.rules.default")) + except + until + (r.live ? "" : " · " + t("config.rules.off"));
  const acts = mine
    ? `<span class="set-inline"><label class="set-check"><input type="checkbox" id="cf_rule_on_${esc(r.id)}" class="cf-rule-on" data-rule="${esc(r.id)}"${r.active ? " checked" : ""}/> ${esc(t("config.rules.active"))}</label>` +
      btn(t("config.rules.delete"), { cls: "cf-rule-del", attrs: `data-rule="${esc(r.id)}"` }) + `</span>`
    : "";
  // the label is his words, or what the row sets — in his language, from the server
  return row(r.name, (r.key === "note" ? "" : control(r)) + acts, esc(hint), r.key === "note" ? "" : `cf_rule_${r.id}`);
}

export function rulesHtml(data) {
  const groups = (data && data.groups) || [];
  return groups.length ? groups.map(g => group(g.rows.map(rowHtml).join(""), { title: g.label })).join("")
    : `<p class="set-hint">${esc(t("config.rules.empty"))}</p>`;
}

// Fills `host` with the list and wires it to the page's Cancel + Save; every save reloads the list from the
// server, so the page never shows a value the table does not hold.
export async function mountRules(host, say, pageEl) {
  if (!host) return;
  const load = async () => {
    const data = await api.getRules().catch(() => null);
    if (!data || !data.ok) { host.innerHTML = `<p class="set-hint cf-warn-text">${esc(t("config.rules.error"))}</p>`; return; }
    host.innerHTML = rulesHtml(data);
    host.querySelectorAll(".cf-rule-del").forEach(el => el.onclick = async () => {
      const res = await api.deleteRule(el.dataset.rule);
      say(res && res.ok === false ? (res.message || t("config.rules.error")) : t("config.rules.saved"), res && res.ok === false);
      await load();
    });
    if (form) form.snap(), form.sync();
  };
  const save = async (changed) => {
    for (const el of changed) {
      const patch = el.classList.contains("cf-rule-on") ? { active: el.checked }
        : { value: el.dataset.type === "boolean" ? el.value === "true" : el.dataset.type === "number" ? Number(el.value) : el.value };
      const res = await api.editRule(el.dataset.rule, patch);
      if (res && res.ok === false) { await load(); return { ok: false, message: res.message || t("config.rules.error") }; }
    }
    await load();
    return { ok: true, message: t("config.rules.saved") };
  };
  const form = pageEl ? bindForm(pageEl, { save, reset: () => load() }) : null;
  host.innerHTML = `<p class="set-hint">…</p>`;
  await load();
}

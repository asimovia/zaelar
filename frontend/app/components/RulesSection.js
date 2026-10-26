// RulesSection — ⚙ Settings → Rules (V2-806): his standing rules and preferences, ONE table, grouped by scope.
// Each row reads his own words (or the key it sets), its value, and where it came from: «yours» or «default».
// His rows can be edited, switched off and deleted; a default can be edited — that writes a row of his at the
// same scope, and the factory row stays. Built from the panel's own pieces (cf-sub, cf-row2, cf-btn-ghost):
// a label column then a control column, from the left (CRIT-K19). Nothing here decides anything: the server
// checks every value against its key's domain (`rules/api.py`).
import * as api from "../services/api.js?v=2";
import { t } from "../core/i18n.js?v=1";

const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

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
  const except = (r.except || []).length ? " · " + t("config.rules.except", { what: r.except.join(", ") }) : "";
  const hint = (mine ? t("config.rules.mine") : t("config.rules.default")) + except + until + (r.live ? "" : " · " + t("config.rules.off"));
  const named = t(`config.rules.k.${r.key}`);    // a key's name in his language; the key itself if it has none
  const label = r.text || (r.key === "note" ? String(r.value) : (named.startsWith("config.") ? r.key : named));
  const acts = mine
    ? `<div class="cf-acts"><label class="cf-hint"><input type="checkbox" class="cf-rule-on" data-rule="${esc(r.id)}"${r.active ? " checked" : ""}/> ${esc(t("config.rules.active"))}</label>` +
      `<button type="button" class="cf-btn cf-btn-ghost cf-rule-del" data-rule="${esc(r.id)}">${esc(t("config.rules.delete"))}</button></div>`
    : "";
  return `<div class="cf-row2"><label class="cf-row2-label" for="cf_rule_${esc(r.id)}">${esc(label)}</label>` +
    `<div class="cf-row2-ctl">${r.key === "note" ? "" : control(r)}${acts}<span class="cf-hint">${esc(hint)}</span></div></div>`;
}

export function rulesHtml(data) {
  const groups = (data && data.groups) || [];
  const body = groups.length
    ? groups.map(g => `<div class="cf-sub"><h5 class="cf-sub-h">${esc(g.label)}</h5>${g.rows.map(rowHtml).join("")}</div>`).join("")
    : `<p class="cf-hint">${esc(t("config.rules.empty"))}</p>`;
  return `<section class="cf-panel-sec" id="cf_rules"><header class="cf-panel-head"><h4>${esc(t("config.rules.title"))}</h4>` +
    `<p>${esc(t("config.rules.sub"))}</p></header><div class="cf-group">${body}</div></section>`;
}

// Fills `host` with the list and wires it; every change reloads the list from the server, so the panel never
// shows a value the table does not hold.
export async function mountRules(host, say) {
  if (!host) return;
  const load = async () => {
    const data = await api.getRules().catch(() => null);
    if (!data || !data.ok) { host.innerHTML = `<p class="cf-error">${esc(t("config.rules.error"))}</p>`; return; }
    host.innerHTML = rulesHtml(data);
    wire();
  };
  const done = async (res) => { if (res && res.ok === false) say(res.message || t("config.rules.error")); else say(t("config.rules.saved")); await load(); };
  function wire() {
    host.querySelectorAll(".cf-rule-val").forEach(el => el.onchange = () => {
      const raw = el.value;
      const value = el.dataset.type === "boolean" ? raw === "true" : el.dataset.type === "number" ? Number(raw) : raw;
      api.editRule(el.dataset.rule, { value }).then(done);
    });
    host.querySelectorAll(".cf-rule-on").forEach(el => el.onchange = () => api.editRule(el.dataset.rule, { active: el.checked }).then(done));
    host.querySelectorAll(".cf-rule-del").forEach(el => el.onclick = () => api.deleteRule(el.dataset.rule).then(done));
  }
  host.innerHTML = `<p class="cf-loading">…</p>`;
  await load();
}

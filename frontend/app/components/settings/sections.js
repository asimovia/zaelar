// The ⚙ Settings pages that are plain forms or lists, each built from the ONE layout (`./layout.js`): FlashBrain,
// Brain Workers, Memory, Voice, Web search, Music, APIs & balance, Notifications, Appearance and Widgets. Pure
// builders — HTML from the loaded config; ConfigPanel wires them and saves. Field ids are what the saves read.
import { t } from "../../core/i18n.js?v=1";
import { esc, row, group, page, btn } from "./layout.js?v=1";
import * as push from "../../services/push.js?v=1";
import { THEMES } from "../../core/themes.js?v=1";

export const opt = (list, sel) => (list || []).map(o => { const v = o.value != null ? o.value : o;
  return `<option value="${esc(v)}"${v === sel ? " selected" : ""}>${esc(o.label != null ? o.label : o)}</option>`; }).join("");
const badge = st => `<span class="cf-badge cf-${esc(st || "off")}">${({ ok: t("config.badge.ok"), warn: t("config.badge.warn"), error: t("config.badge.error"), off: t("config.badge.off"), unknown: "—" }[st] || st || "—")}</span>`;
const sec = (id, title, sub, body, more = {}) => page({ id, crumb: [t("config.sec." + id)], title, sub, body, ...more });

// A CLOSED model list: only what that provider serves (the backend refuses anything else on save too).
export const modelSelect = (id, models, sel, blank) =>
  `<select id="${id}">${blank != null ? `<option value=""${sel ? "" : " selected"}>${esc(blank)}</option>` : ""}${opt(models || [], sel)}</select>`;

// The API key of the chosen provider (cloud providers with a key env only). Redacted: only whether it is set.
export function providerKeyRow(cfg, prov) {
  if (!prov || !prov.cloud || !prov.key_env) return "";
  const setNow = (cfg.credentials || []).some(c => (c.env || []).includes(prov.key_env) && c.set);
  return row(t("config.apikey.label", { env: prov.key_env }),
    `<input id="cf_key_${esc(prov.key_env)}" type="password" placeholder="${setNow ? t("config.key.ph_saved_keep") : t("config.key.ph_paste")}" autocomplete="off"/>`,
    setNow ? t("config.key.configured") : t("config.key.not_configured"), "cf_key_" + prov.key_env);
}

export function sec_fast(cfg) {
  const c = (cfg.catalog || {}).fast || {}, f = (cfg.v2 && cfg.v2.fast) || {};
  const provs = c.providers || [];
  const cur = provs.find(p => p.id === f.provider) || provs[0] || {};
  return sec("fast", t("config.fast.title"), t("config.fast.sub"), group(
    row(t("config.row.provider"), `<select id="cf_fast_provider">${opt(provs.map(p => ({ value: p.id, label: p.label })), f.provider)}</select>`, "", "cf_fast_provider") +
    row(t("config.row.model"), `<span id="cf_fast_modelbox">${modelSelect("cf_fast_model", cur.models, f.model)}</span>`, "", "cf_fast_model") +
    `<div id="cf_fast_keyrow" class="set-rowslot">${providerKeyRow(cfg, cur)}</div>`), { form: true });
}

// Is that provider's CLI installed on THIS machine, and does its own config ask for a model the API does not serve?
export const cliState = p => {
  if (p.detected === undefined) return "";
  if (!p.detected) return `<span class="cf-warn-text">⚠ ${esc(t("config.code.cli_missing"))}</span>`;
  let s = `✓ ${esc(t("config.code.cli_found", { version: p.version || "?" }))}`;
  if (p.stale_default) s += ` · <span class="cf-warn-text">⚠ ${esc(t("config.code.stale_default", { model: p.stale_default }))}</span>`;
  return s;
};
const codeHint = (p, c) => [cliState(p), esc(p.note || c.note || "")].filter(Boolean).join("<br>");

export const codeModelRows = (p, a) => {
  const ms = p.models || [];
  // The CLI's own default (read from its config) leads the blank option's text when that model exists.
  const dflt = p.default_model && ms.includes(p.default_model) ? p.default_model : "";
  const g = t("config.ph.provider_default") + (dflt ? ` (${dflt})` : "");
  return row(t("config.code.model_global"), modelSelect("cf_code_model", ms, a.model, g), "", "cf_code_model") +
    row(t("config.code.model_memory"), modelSelect("cf_code_model_memory", ms, a.model_memory, t("config.ph.inherits")), "", "cf_code_model_memory") +
    row(t("config.code.model_web"), modelSelect("cf_code_model_web", ms, a.model_web, t("config.ph.inherits")), "", "cf_code_model_web") +
    row(t("config.code.model_code"), modelSelect("cf_code_model_code", ms, a.model_code, t("config.ph.inherits")), "", "cf_code_model_code");
};

// A preset moves CLI + endpoint + model TOGETHER (picking them apart is where mismatches came from). Picking one
// fills the form; Save writes it. One that cannot work says why on the card.
const presetCard = (p, activeId) => {
  const on = p.id === activeId;
  const money = p.billing === "subscription" ? "◆" : (p.billing === "licence" ? "◇" : "$");
  const state = p.ready ? "" : `<span class="cf-warn-text">⚠ ${esc(p.blocked_by === "cli"
    ? t("config.preset.no_cli") : t("config.preset.no_key", { env: p.key_env || "" }))}</span>`;
  return `<button type="button" class="cf-preset${on ? " on" : ""}${p.ready ? "" : " off"}" data-preset="${esc(p.id)}" aria-pressed="${on}">
    <span class="cf-preset-h">${money} ${esc(p.label)}</span><span class="set-hint">${esc(p.cost || "")}</span>${state}</button>`;
};
// Which preset is set? The whole triple is compared: two presets can share a CLI and differ only in the endpoint.
export const activePreset = (presets, a) => (presets.find(p =>
  p.provider === (a.provider || "") && (p.base_url || "") === (a.base_url || "") && (p.model || "") === (a.model || "")) || {}).id || "";

export function sec_code(cfg) {
  const c = (cfg.catalog || {}).code_agent || {}, a = (cfg.v2 && cfg.v2.code_agent) || {};
  const provs = c.providers || [], presets = c.presets || [];
  const cur = provs.find(p => p.id === a.provider) || provs[0] || {};
  const act = activePreset(presets, a);
  return sec("code", t("config.code.title"), t("config.code.sub"), group(
    (presets.length ? row(t("config.code.preset"), `<div class="cf-presets" id="cf_code_presets">${presets.map(p => presetCard(p, act)).join("")}</div>`,
      t("config.code.preset_hint")) : "") +
    row(t("config.row.provider"), `<select id="cf_code_provider">${opt(provs.map(p => ({ value: p.id, label: p.label })), a.provider)}</select>` +
      `<input type="hidden" id="cf_code_base_url" value="${esc(a.base_url || "")}"/>`,
      `<span id="cf_code_provnote">${codeHint(cur, c)}</span>`, "cf_code_provider") +
    `<div id="cf_code_models" class="set-rowslot">${codeModelRows(cur, a)}</div>`),
  { form: true });
}
export { codeHint };

export function sec_memory(cfg) {
  const cat = cfg.catalog || {}, m = (cfg.v2 && cfg.v2.memory) || {};
  const emb = (cat.memory_embed && cat.memory_embed.providers) || [], rer = (cat.memory_rerank && cat.memory_rerank.providers) || [];
  const input = (id, v, extra = "") => `<input id="${id}" value="${esc(v)}"${extra}/>`;
  return sec("memory", t("config.memory.title"), t("config.memory.sub"),
    group(row(t("config.memory.embedding"), `<select id="cf_mem_embed_provider">${opt(emb.map(p => ({ value: p.id, label: p.label })), m.embed_provider)}</select>`, t("config.memory.embed_warn"), "cf_mem_embed_provider") +
      row(t("config.memory.embed_model"), input("cf_mem_embed_model", m.embed_model), "", "cf_mem_embed_model")) +
    group(row(t("config.memory.reranker"), `<select id="cf_mem_rerank_provider">${opt(rer.map(p => ({ value: p.id, label: p.label })), m.rerank_provider)}</select>`, "", "cf_mem_rerank_provider") +
      row(t("config.memory.rerank_model"), input("cf_mem_rerank_model", m.rerank_model, ` placeholder="${esc(t("config.ph.provider_default"))}"`), "", "cf_mem_rerank_model") +
      row(t("config.memory.top_n"), input("cf_mem_rerank_top_n", m.rerank_top_n, ' type="number" min="1" max="100"'), "", "cf_mem_rerank_top_n") +
      row(t("config.memory.blend"), input("cf_mem_rerank_blend", m.rerank_blend, ' type="number" step="0.05" min="0" max="1"'), "", "cf_mem_rerank_blend")) +
    group(row(t("config.memory.write_processor"), input("cf_mem_mem_processor_model", m.mem_processor_model), "", "cf_mem_mem_processor_model")),
  { form: true });
}

// Server knobs (saved by Save) and THIS browser's capture (applied the moment it changes, so `data-set-live`: it
// never makes the page dirty). The capture ids stay `micsel`/`micmode`: the session fills and drives them by id.
export function sec_voice(cfg, cloudProfile, lockedKeys) {
  const v = cfg.voice || {}, free = new Set(v.free_text || []);
  const knobs = (v.knobs || []).filter(k => !(cloudProfile && lockedKeys.has(k.key)));
  const rows = knobs.map(k => row(k.label, free.has(k.key)
    ? `<input id="cfv_${k.key}" list="dlv_${k.key}" value="${esc(k.value)}"/><datalist id="dlv_${k.key}">${opt(k.options)}</datalist>`
    : `<select id="cfv_${k.key}">${opt(k.options, k.value)}</select>`, k.note ? esc(k.note) : "", "cfv_" + k.key)).join("");
  // The capture block sits BELOW the bar: it applies at once, and Save is never a button under controls it does not save.
  return sec("voice", t("config.voice.title"), t("config.voice.sub"),
    group(rows, { note: cloudProfile ? t("config.voice.cloud_locked") : "" }), { form: true, after:
    group(row(t("config.voice.device"), `<select id="micsel"></select>`, esc(t("config.voice.device_hint")), "micsel") +
      row(t("config.voice.capture"), `<select id="micmode"></select>`, esc(t("config.voice.capture_hint")), "micmode"),
    { title: t("config.voice.device_title"), note: `${t("config.voice.device_sub")} ${t("config.voice.wakeword_privacy")}`, attrs: 'id="cf_voice_device" data-set-live' }) });
}

// Voice › Voice recognition (V2-651 F1): built and wired in its own file, listed here with the other pages.
export { sec_voiceid } from "./voice-id.js?v=1";

// Web search picks its provider from the keys present; the keys ARE its settings. Empty = keep what is saved.
export function sec_search(cfg) {
  const creds = cfg.credentials || [];
  const keyRow = (prov, env, label) => {
    const setNow = creds.some(c => c.key === prov && c.set);
    return row(label, `<input id="cf_key_${esc(env)}" type="password" placeholder="${setNow ? t("config.key.ph_saved") : t("config.key.ph_paste_optional")}" autocomplete="off"/>`,
      `${esc(env)} · ${setNow ? t("config.key.active") : t("config.key.not_configured")}`, "cf_key_" + env);
  };
  return sec("search", t("config.search.title"), t("config.search.sub"), group(
    keyRow("perplexity", "PERPLEXITY_API_KEY", t("config.search.perplexity")) +
    keyRow("tavily", "TAVILY_API_KEY", t("config.search.tavily")) +
    keyRow("brave", "BRAVE_SEARCH_KEY", t("config.search.brave"))), { form: true });
}
export const SEARCH_ENVS = ["PERPLEXITY_API_KEY", "TAVILY_API_KEY", "BRAVE_SEARCH_KEY"];

export function sec_music(cfg) {
  const sp = cfg.spotify || {};
  const st = sp.logged_in ? t("config.music.connected") : (sp.can_connect ? t("config.music.ready") : t("config.music.missing_client"));
  const act = sp.logged_in ? btn(t("config.music.disconnect"), { cls: "cf-spotify-dis" })
    : btn(t("config.music.connect"), { kind: "primary", cls: "cf-spotify", attrs: sp.can_connect ? "" : "disabled" });
  return sec("music", t("config.music.title"), t("config.music.sub"),
    group(row(t("config.row.status"), `<span class="cf-status">${esc(st)}${sp.logged_in ? "" : (sp.default_available ? t("config.music.oneclick") : "")}</span>` +
      `<span class="set-inline">${act}</span>`)));
}

const bar = b => { const pct = b.limit ? Math.min(100, Math.round((b.used / b.limit) * 100)) : 0;
  return `<span class="cf-bar"><i style="width:${pct}%"></i></span> ${pct}%`; };
export const apisRows = cfg => (cfg.apis || []).map(a => `<tr class="cf-api cf-api-${esc(a.state)}">
    <td class="cf-api-name">${esc(a.key)}<span>${esc(a.enables || "")}</span></td><td>${badge(a.state)}</td>
    <td class="cf-api-detail">${esc(a.detail || "")}${a.balance && a.balance.limit ? ` · ${bar(a.balance)}` : ""}</td></tr>`).join("") || '<tr><td colspan="3">—</td></tr>';
export const sec_apis = cfg => sec("apis", t("config.apis.title"), t("config.apis.sub"),
  `<div class="set-group set-table"><table class="cf-apis"><tbody id="cf_apis_tbody">${apisRows(cfg)}</tbody></table></div>`,
  { tools: btn(t("config.apis.refresh"), { cls: "cf-refresh-apis" }) });

// Can THIS browser be reached when zaelar is closed? The engine sends each notice by voice when he is in front of
// a screen, and to every subscribed browser when he is not (`nucleo/pulse/notices.py`).
export function sec_notices() {
  const p = push.permission();
  const state = !push.supported() ? "—" : p === "granted" ? t("push.settings_on") : p === "denied" ? t("push.denied") : t("push.settings_off");
  const ctl = !push.supported() ? "" : p === "granted" ? btn(t("push.test"), { cls: "cf-push-test" })
    : p === "default" ? btn(t("push.button"), { kind: "primary", cls: "cf-push-on" }) : "";
  return sec("notices", t("push.title"), t("push.body"),
    group(row(t("push.settings_label"), `<span class="cf-status">${esc(state)}</span>${ctl ? `<span class="set-inline">${ctl}</span>` : ""}`)));
}

// Appearance: every change is PREVIEWED at once; Save keeps it on the account, Cancel puts the saved look back.
// The cards and the mode buttons write hidden fields, so the page knows it is dirty like any other form.
export function sec_apariencia({ profile, custom, mode, langPicker, langArmed, themeName }) {
  const cards = Object.entries(THEMES).map(([id, th]) => {
    const sw = (th.swatches || []).map(c => `<i style="background:${esc(c)}"></i>`).join("");
    return `<button type="button" class="cf-th-card${id === profile ? " on" : ""}" data-profile="${esc(id)}" aria-pressed="${id === profile}">
      <span class="cf-th-sw">${sw}</span><span class="cf-th-name">${esc(themeName(id, th))}</span></button>`;
  }).join("");
  const sel = (id, pairs, cur) => `<select id="${id}">${pairs.map(([v, l]) => `<option value="${v}"${cur === v ? " selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
  const modeBtn = m => `<button type="button" class="cf-th-modebtn${mode === m ? " on" : ""}" data-mode="${m}" aria-pressed="${mode === m}">${t("config.theme.mode_" + m)}</button>`;
  const look = group(
    `<div class="set-row set-row--wide"><span class="set-label">${esc(t("config.theme.profile"))}</span><div class="set-ctl"><div class="cf-th-cards">${cards}</div>` +
      `<input type="hidden" id="cf_th_profile" value="${esc(profile)}"/></div></div>` +
    row(t("config.theme.mode"), `<span class="cf-th-mode">${modeBtn("dark")}${modeBtn("light")}</span><input type="hidden" id="cf_th_mode" value="${esc(mode)}"/>`) +
    row(t("config.theme.accent"), `<span class="cf-th-accent"><input type="color" id="cf_th_accent" data-set-live value="${esc(custom.accent || "#A48FFF")}">` +
      btn(t("config.theme.accent_clear"), { cls: "cf-th-accent-clear", attrs: custom.accent ? "" : "disabled" }) +
      `<input type="hidden" id="cf_th_accent_val" value="${esc(custom.accent || "")}"/></span>`, t("config.theme.accent_hint"), "cf_th_accent") +
    row(t("config.theme.fs"), sel("cf_th_fs", [["s", t("config.theme.fs_s")], ["m", t("config.theme.fs_m")], ["l", t("config.theme.fs_l")]], custom.fs || "m"), "", "cf_th_fs") +
    row(t("config.theme.font"), sel("cf_th_font", [["system", t("config.theme.font_system")], ["rounded", t("config.theme.font_rounded")], ["serif", t("config.theme.font_serif")]], custom.font || "system"),
      t("config.theme.font_hint"), "cf_th_font"));
  // The language is NOT part of this form: it is asked twice and applied on its own (`/api/i18n/choose`).
  const langs = (langPicker.rows || []).map(l => `<option value="${esc(l.code)}"${l.code === langPicker.active ? " selected" : ""}>${esc(l.flag || "")} ${esc(l.native || l.code)}</option>`).join("");
  const lang = langs ? group(row(t("config.lang.pick"), `<select id="cf_lang_sel">${langs}</select>` +
      `<span class="set-inline">${btn(langArmed ? t("config.lang.confirm") : t("config.lang.apply"), { kind: langArmed ? "primary" : "secondary", cls: "cf-lang-go" + (langArmed ? " armed" : "") })}</span>`,
    t("config.lang.hint"), "cf_lang_sel"), { title: t("config.lang.title"), note: t("config.lang.sub"), attrs: 'id="cf_idioma" data-set-live' }) : "";
  return page({ id: "apariencia", crumb: [t("config.tab.apariencia")], title: t("config.theme.title"), sub: t("config.theme.sub"), body: look, form: true, after: lang });
}

// Every widget the person can open, alphabetical, with its built-in / yours badge and the names it answers to.
export function sec_widgets(cfg, lang) {
  const ws = (cfg.widgets || []).filter(w => w.surface === "user")
    .sort((a, b) => String(a.name || a.id).localeCompare(String(b.name || b.id), lang || "en"));
  const rows = ws.map(w => {
    const kind = w.origin === "builtin" ? `<span class="cf-wbadge builtin">${t("config.widgets.builtin_badge")}</span>`
      : `<span class="cf-wbadge user">${t("config.widgets.yours_badge")}</span>`;
    const al = (w.aliases || []).filter(a => a.toLowerCase() !== String(w.name || "").toLowerCase()).slice(0, 6).join(" · ");
    return `<div class="set-row cf-wrow"><span class="set-label cf-wname">${esc(w.name || w.id)} ${kind}</span><div class="set-ctl"><span class="set-hint cf-waliases">${esc(al)}</span></div></div>`;
  }).join("");
  return page({ id: "widgets", crumb: [t("config.tab.widgets")], title: t("config.widgets.title"), sub: t("config.widgets.sub"),
    body: ws.length ? group(rows) : `<p class="set-hint">${t("config.widgets.load_error")}</p>` });
}

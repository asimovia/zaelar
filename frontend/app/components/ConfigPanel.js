// ConfigPanel — the full-screen ⚙ Settings area (V2-043): which API/model each piece uses, voice, search, music,
// balances, notices, rules, permissions, appearance, the agent's face, connectors and widgets. ONE left menu (a
// section visible at a time) and a content column where EVERY page is drawn by the one layout in
// `settings/layout.js` — breadcrumb, title, one line, rows with a fixed label column, Cancel + Save at the bottom
// right. The plain pages are built in `settings/sections.js`; this file holds the menu, the wiring and the saves.
import { h, raw } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/api.js?v=2";
import * as session from "../services/session.js?v=3";
import { GEAR_ICON, BRAIN_ICON, CPU_ICON, DATABASE_ICON, MIC_ICON, SEARCH_ICON, MUSIC_ICON, SERVER_ICON, BELL_ICON, MOON_ICON, LINK_ICON, WIDGETS_ICON, LIST_ICON, LOCK_ICON, FACE_ICON } from "../lib/icons.js?v=2";
import { mountRules } from "./RulesSection.js?v=2";   // V2-806 — his rules and preferences, one table
import { mountPermissions } from "./PermissionsSection.js?v=2";   // V2-875 — his permission switches
import { mountPresence } from "../presence/PresenceSection.js?v=1";   // V2-928 — the agent's face
import * as push from "../services/push.js?v=1";
import { t } from "../core/i18n.js?v=1";
import * as themeSvc from "../services/theme.js?v=2";
import { theme as themeSignal, setTheme } from "../core/store.js?v=2";
import { connectorList, connectorWizard, connectorForm, isSettling, groupGoogle, focusOf } from "./ConnectorWizard.js?v=7";
import { esc, page, btn, bindForm, say } from "./settings/layout.js?v=1";
import * as S from "./settings/sections.js?v=1";

const SECTIONS = [
  { id: "fast", icon: BRAIN_ICON },
  { id: "code", icon: CPU_ICON },
  { id: "memory", icon: DATABASE_ICON },
  { id: "voice", icon: MIC_ICON },
  { id: "search", icon: SEARCH_ICON },
  { id: "music", icon: MUSIC_ICON },
  { id: "apis", icon: SERVER_ICON },
  { id: "notices", icon: BELL_ICON },     // V2-796 — Web Push on this browser
  { id: "rules", icon: LIST_ICON },       // V2-806 — his standing rules and preferences
  { id: "permissions", icon: LOCK_ICON }, // V2-875 — location, files, observability kept, data tagged
];

// Sections that PICK a provider/model — hidden in the cloud profile, where the deployment sets them (V2-043; the
// backend gate is _CLOUD_LOCKED_V2_SECTIONS in server/config_api.py). `apis` stays visible: information, no choice.
const CLOUD_LOCKED_NAV_SECTIONS = new Set(["fast", "code", "memory"]);
// voice_api's STT/TTS provider knobs specifically (the rest of `voice` — language, VAD, etc. — stays editable).
const CLOUD_LOCKED_VOICE_KEYS = new Set(["stt_provider", "tts_provider"]);

// The panel's top-level areas: the groups of ONE left menu since 2026-10-25 (operator: «un menú a la izquierda…»);
// «settings» carries its sections as sub-items. On a phone the menu is the first page, a section opens over it.
const TABS = [
  { id: "settings", icon: GEAR_ICON },
  { id: "apariencia", icon: MOON_ICON },   // V2-617: design profiles + custom knobs — the whole desktop's skin
  { id: "presence", icon: FACE_ICON },     // V2-928: the agent's face — choose it, tune it, switch it off
  { id: "conectores", icon: LINK_ICON },
  { id: "widgets", icon: WIDGETS_ICON },
];

export function ConfigPanel() {
  let cfg = null, bodyEl, msgEl, ovl;
  let activeSec = SECTIONS[0].id;
  let activeTab = "settings";
  // Phone only: is the menu the page on screen (true) or the section it opened (false)? Desktop shows both.
  let navOpen = true;
  // The Conectores tab shows ONE connector at a time behind a breadcrumb (`cxFocus`), on its guide's `cxStep`.
  let cxFocus = null, cxStep = 0, cxPolling = false, cxService = "";   // cxService: the Google service picked out
  // Where «Volver» goes when something OUTSIDE the panel opened it on one connector (a card, the wall, the voice):
  // {from: "<caller's name>" | ""}. Then the connector's «Volver» closes the panel — back to the caller.
  let cxReturn = null;
  // The consent URL the browser REFUSED to open in a window (pop-up blocker), kept per connector so its form can
  // offer the way in (a «connecting…» that never moves read as a hang).
  let cxConsent = null;   // null | { id, url }
  // V2-694 — the language picker's rows and the code in force, read from GET /api/i18n/state (the SAME source the
  // first-run veil uses). `langArmed` is the first half of the two-click consent: see `applyLanguage`.
  let langPicker = { rows: [], active: "" };
  let langArmed = false;
  // Appearance previews before it saves: the look that is SAVED, put back by Cancel or by leaving the page.
  let savedLook = null;

  // A result is said in the bar of the page on screen; with no page (loading) it goes to the top line.
  const msg = (text, bad) => { if (!say(bodyEl, text, bad === true ? "error" : "") && msgEl) msgEl.textContent = text || ""; };

  // ---- render ----
  function render() {
    const cloudProfile = !!cfg.cloud_profile;
    const visibleSections = cloudProfile ? SECTIONS.filter(s => !CLOUD_LOCKED_NAV_SECTIONS.has(s.id)) : SECTIONS;
    const host = (id, sid, form) => page({ id: sid, crumb: [t("config.sec." + sid)], title: t("config.sec." + sid), sub: t(`config.${id}.sub`),
      body: `<div id="cf_${sid}_host"></div>`, form });
    const builders = {
      fast: () => S.sec_fast(cfg),
      code: () => S.sec_code(cfg),
      memory: () => S.sec_memory(cfg),
      voice: () => S.sec_voice(cfg, cloudProfile, CLOUD_LOCKED_VOICE_KEYS),
      search: () => S.sec_search(cfg),
      music: () => S.sec_music(cfg),
      apis: () => S.sec_apis(cfg),
      notices: () => S.sec_notices(),
      rules: () => page({ id: "rules", crumb: [t("config.sec.rules")], title: t("config.rules.title"), sub: t("config.rules.sub"), body: `<div id="cf_rules_host"></div>`, form: true }),
      permissions: () => host("perm", "permissions", true),
    };
    if (!builders[activeSec] || (cloudProfile && CLOUD_LOCKED_NAV_SECTIONS.has(activeSec))) activeSec = visibleSections[0].id;
    // ONE left menu: each area a row; «settings» lists its sections under it, always visible.
    const subs = visibleSections.map(sc => `<button type="button" class="cf-nav-item cf-nav-sub${activeTab === "settings" && sc.id === activeSec ? " active" : ""}" data-sec="${sc.id}">` +
      `${sc.icon}<span>${esc(t("config.sec." + sc.id))}</span></button>`).join("");
    const menu = `<nav class="cf-nav cf-side" aria-label="${esc(t("config.menu"))}">` + TABS.map(tab =>
      `<button type="button" class="cf-nav-item cf-nav-top${tab.id === activeTab && (tab.id !== "settings") ? " active" : ""}${tab.id === activeTab ? " on" : ""}" data-tab="${tab.id}">` +
      `${tab.icon}<span>${esc(t("config.tab." + tab.id))}</span></button>` + (tab.id === "settings" ? `<div class="cf-nav-subs">${subs}</div>` : "")).join("") + `</nav>`;
    const here = activeTab === "settings" ? t("config.sec." + activeSec) : t("config.tab." + activeTab);
    let content;
    if (activeTab === "conectores") content = sec_connectors();
    else if (activeTab === "apariencia") content = S.sec_apariencia({ profile: themeSvc.themeProfile(), custom: themeSvc.themeCustom(), mode: themeSignal(), langPicker, langArmed, themeName });
    else if (activeTab === "widgets") content = S.sec_widgets(cfg, store.lang());
    else if (activeTab === "presence") content = page({ id: "presence", crumb: [t("config.tab.presence")], title: t("config.tab.presence"), sub: t("config.presence.sub"), body: `<div id="cf_presence_host"></div>` });
    else content = builders[activeSec]();
    const pane = `<div class="cf-main"><div class="cf-mback"><button type="button" class="cf-mback-btn" data-menu="1">← ${esc(t("config.menu"))}</button><b>${esc(here)}</b></div>` +
      `<div class="cf-scroll"><div class="cf-panel">${content}</div></div></div>`;
    bodyEl.innerHTML = `<div class="cf-layout${navOpen ? " is-menu" : ""}">${menu}${pane}</div>`;
    wire();
  }

  // Leaving Appearance with an unsaved look puts the saved one back (a preview is never kept by walking away).
  function dropPreview() {
    if (!savedLook) return;
    themeSvc.previewTheme(savedLook); if (themeSignal() !== savedLook.mode) setTheme(savedLook.mode);
    savedLook = null;
  }
  const lookNow = () => ({ profile: themeSvc.themeProfile(), custom: themeSvc.themeCustom(), mode: themeSignal() });

  // ---- wiring ----
  function wire() {
    const pg = bodyEl.querySelector(".set-page");
    if (activeTab === "settings" && activeSec === "rules") mountRules(document.getElementById("cf_rules_host"), msg, pg);
    if (activeTab === "settings" && activeSec === "permissions") mountPermissions(document.getElementById("cf_permissions_host"), msg, cfg, pg);
    if (activeTab === "presence") mountPresence(document.getElementById("cf_presence_host"), msg);
    // The menu: an area row opens that area (Settings on its current section); a sub-item opens that section.
    // Re-clicking the open area on a phone still has to leave the menu, so it always renders.
    bodyEl.querySelectorAll(".cf-nav-top").forEach(b => b.onclick = () => {
      dropPreview();
      if (b.dataset.tab === "conectores" && activeTab !== "conectores") { cxFocus = null; cxService = ""; cxStep = 0; }
      activeTab = b.dataset.tab; navOpen = false; render(); bodyEl.querySelector(".cf-scroll")?.scrollTo(0, 0); });
    bodyEl.querySelectorAll(".cf-nav-sub").forEach(b => b.onclick = () => {
      dropPreview();
      activeTab = "settings"; activeSec = b.dataset.sec; navOpen = false; render(); bodyEl.querySelector(".cf-scroll")?.scrollTo(0, 0); });
    bodyEl.querySelectorAll("[data-menu]").forEach(b => b.onclick = () => { navOpen = true; render(); });
    if (activeTab === "apariencia") wireAppearance(pg);
    // controles of the pestaña Conectores
    bodyEl.querySelectorAll(".cf-cx-act").forEach(b => b.onclick = () => cxAct(b.dataset.act, b.dataset.id, b));
    bodyEl.querySelectorAll("[data-cx]").forEach(b => b.onclick = () => { ({ focus: cxFocus, service: cxService } = focusOf(b.dataset.cx)); cxStep = 0; cxConsent = null; render(); });
    bodyEl.querySelectorAll("[data-cx-back]").forEach(b => b.onclick = () => { cxFocus = null; cxService = ""; cxStep = 0; cxConsent = null; cxReturn = null; render(); });
    // The connector's own way out: back to whoever sent the person here, else to the list (data-cx-back's job).
    bodyEl.querySelectorAll("[data-cx-done]").forEach(b => b.onclick = () => {
      if (cxReturn) close(); else { cxFocus = null; cxService = ""; cxStep = 0; cxConsent = null; render(); } });
    bodyEl.querySelectorAll("[data-cx-close]").forEach(b => b.onclick = () => close());
    bodyEl.querySelectorAll("[data-cx-step]").forEach(b => b.onclick = () => { cxStep = Number(b.dataset.cxStep) || 0; render(); });
    bodyEl.querySelectorAll("[data-copy]").forEach(b => b.onclick = async () => {
      try { await navigator.clipboard.writeText(b.dataset.copy); b.textContent = t("config.cxw.copied"); } catch (_) {}
    });
    const cxr = bodyEl.querySelector(".cf-cx-refresh"); if (cxr) cxr.onclick = () => reloadConnectors();
    const pon = bodyEl.querySelector(".cf-push-on"); if (pon) pon.onclick = async () => { await push.enable(); render(); };
    const pts = bodyEl.querySelector(".cf-push-test"); if (pts) pts.onclick = async () => { await push.test(); msg(t("push.on")); };
    const emp = document.getElementById("cx_em_provider");
    if (emp) emp.onchange = () => {
      bodyEl.querySelectorAll(".cf-em-link").forEach(a => { a.hidden = a.dataset.em !== emp.value; });
      const o = bodyEl.querySelector(".cf-em-other"); if (o) o.hidden = emp.value !== "other";
    };
    wireModels();
    const rf = bodyEl.querySelector(".cf-refresh-apis"); if (rf) rf.onclick = () => refreshApis(rf);
    const sc = bodyEl.querySelector(".cf-spotify"); if (sc) sc.onclick = () => connectSpotify(sc);
    const sd = bodyEl.querySelector(".cf-spotify-dis"); if (sd) sd.onclick = () => disconnectSpotify(sd);
    // The capture block is filled by the session engine, which owns the device list and the reconnect. Filling is
    // ASYNC (`enumerateDevices`); a select nobody filled is a control that does nothing — its row goes, and the
    // block goes when it is left empty (the legacy engine has no capture-mode picker).
    const dev = bodyEl.querySelector("#cf_voice_device");
    if (dev) {
      const filled = session.mountMicPickers ? session.mountMicPickers() : Promise.resolve();
      Promise.resolve(filled).catch(() => {}).then(() => {
        dev.querySelectorAll("select").forEach(sel => { if (!sel.options.length) { const r = sel.closest(".set-row"); if (r) r.remove(); } });
        if (!dev.querySelector("select")) dev.remove();
      });
    }
    // Every page that edits values: Cancel puts the loaded values back by drawing the page again from them.
    const saves = { fast: () => saveV2("fast"), code: () => saveV2("code_agent"), memory: () => saveV2("memory"),
      voice: saveVoice, search: () => saveKeys(S.SEARCH_ENVS) };
    if (pg && activeTab === "settings" && saves[activeSec]) bindForm(pg, { save: saves[activeSec], reset: render });
  }

  // A provider change repopulates ITS models (a model of the previous provider is one this one does not serve),
  // its key row and its notes; a Brain Workers preset fills provider + endpoint + model, saved with the page.
  function wireModels() {
    const cat = cfg.catalog || {};
    const fp = document.getElementById("cf_fast_provider");
    if (fp) fp.onchange = () => {
      const p = ((cat.fast && cat.fast.providers) || []).find(x => x.id === fp.value) || {};
      document.getElementById("cf_fast_modelbox").innerHTML = S.modelSelect("cf_fast_model", p.models, (p.models || [])[0]);
      document.getElementById("cf_fast_keyrow").innerHTML = S.providerKeyRow(cfg, p);
    };
    const ca = cat.code_agent || {};
    const cp = document.getElementById("cf_code_provider");
    const setCode = (p, a) => {
      document.getElementById("cf_code_models").innerHTML = S.codeModelRows(p, a);
      document.getElementById("cf_code_provnote").innerHTML = S.codeHint(p, ca);
    };
    const markPreset = () => {
      const a = { provider: cp.value, base_url: document.getElementById("cf_code_base_url").value, model: (document.getElementById("cf_code_model") || {}).value };
      const on = S.activePreset(ca.presets || [], a);
      bodyEl.querySelectorAll(".cf-preset").forEach(b => { b.classList.toggle("on", b.dataset.preset === on); b.setAttribute("aria-pressed", b.dataset.preset === on); });
    };
    if (cp) {
      cp.onchange = () => {
        const p = (ca.providers || []).find(x => x.id === cp.value) || {};
        setCode(p, { model: p.default_model || "", model_memory: "", model_web: "", model_code: "" });
        markPreset();
      };
      bodyEl.querySelector("#cf_code_models")?.addEventListener("change", markPreset);
    }
    // The per-kind models are CLEARED on purpose: they belong to another provider, and dragging them along is the
    // mismatch a preset exists to avoid.
    bodyEl.querySelectorAll(".cf-preset").forEach(b => b.onclick = () => {
      const p = (ca.presets || []).find(x => x.id === b.dataset.preset); if (!p || !cp) return;
      cp.value = p.provider;
      setCode((ca.providers || []).find(x => x.id === p.provider) || {}, { model: p.model || "", model_memory: "", model_web: "", model_code: "" });
      const bu = document.getElementById("cf_code_base_url"); bu.value = p.base_url || "";
      markPreset(); bu.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }

  function wireAppearance(pg) {
    if (!savedLook) savedLook = lookNow();
    const field = id => document.getElementById(id);
    const set = (id, v) => { const el = field(id); el.value = v; el.dispatchEvent(new Event("change", { bubbles: true })); };
    const preview = () => {
      const custom = { accent: field("cf_th_accent_val").value, fs: field("cf_th_fs").value === "m" ? "" : field("cf_th_fs").value,
        font: field("cf_th_font").value === "system" ? "" : field("cf_th_font").value };
      themeSvc.previewTheme({ profile: field("cf_th_profile").value, custom });
      if (themeSignal() !== field("cf_th_mode").value) setTheme(field("cf_th_mode").value);
      bodyEl.querySelectorAll(".cf-th-card").forEach(b => b.classList.toggle("on", b.dataset.profile === field("cf_th_profile").value));
      bodyEl.querySelectorAll(".cf-th-modebtn").forEach(b => b.classList.toggle("on", b.dataset.mode === field("cf_th_mode").value));
      const clr = bodyEl.querySelector(".cf-th-accent-clear"); if (clr) clr.disabled = !field("cf_th_accent_val").value;
    };
    bodyEl.querySelectorAll(".cf-th-card").forEach(b => b.onclick = () => { set("cf_th_profile", b.dataset.profile); preview(); });
    bodyEl.querySelectorAll(".cf-th-modebtn").forEach(b => b.onclick = () => { set("cf_th_mode", b.dataset.mode); preview(); });
    field("cf_th_accent").oninput = e => { set("cf_th_accent_val", e.target.value); preview(); };
    bodyEl.querySelector(".cf-th-accent-clear").onclick = () => { set("cf_th_accent_val", ""); field("cf_th_accent").value = "#A48FFF"; preview(); };
    field("cf_th_fs").addEventListener("change", preview);
    field("cf_th_font").addEventListener("change", preview);
    bindForm(pg, {
      save: async () => { const look = lookNow(); themeSvc.saveTheme(look); savedLook = look; return { ok: true }; },
      reset: () => { dropPreview(); render(); },
    });
    const lg = bodyEl.querySelector(".cf-lang-go"); if (lg) lg.onclick = () => applyLanguage(lg);
    const ls = field("cf_lang_sel");
    // a fresh pick disarms the confirmation: the second click must mean «yes, THAT one».
    if (ls) ls.onchange = () => { if (langArmed) { langArmed = false; render(); } };
  }

  const val = id => { const el = document.getElementById(id); return el ? el.value : undefined; };

  async function saveKey(env) {
    const v = val("cf_key_" + env);
    if (v && v.trim()) { await api.saveConfigCredential(env, v.trim()); return true; }
    return false;
  }

  // After a save the page is drawn again from the server's copy, so Cancel's «loaded values» are the saved ones.
  async function reloadCfg() { try { Object.assign(cfg, await api.getConfig()); } catch (_) {} render(); }

  async function saveV2(section) {
    let patch = {};
    if (section === "fast") {
      const p = ((cfg.catalog.fast && cfg.catalog.fast.providers) || []).find(x => x.id === val("cf_fast_provider")) || {};
      // The endpoint comes FROM the provider: choosing one and leaving an old base_url pointing elsewhere was a
      // silent way to break the FlashBrain.
      patch = { provider: val("cf_fast_provider"), model: val("cf_fast_model"), base_url: p.base_url || "" };
      if (p.key_env) await saveKey(p.key_env);
    } else if (section === "code_agent") {
      patch = { provider: val("cf_code_provider"), base_url: val("cf_code_base_url") || "", model: val("cf_code_model"), model_memory: val("cf_code_model_memory"),
        model_web: val("cf_code_model_web"), model_code: val("cf_code_model_code"), max_parallel: Number(val("cf_code_max_parallel")) || 3 };
    } else if (section === "memory") {
      patch = { embed_provider: val("cf_mem_embed_provider"), embed_model: val("cf_mem_embed_model"),
        rerank_provider: val("cf_mem_rerank_provider"), rerank_model: val("cf_mem_rerank_model"),
        rerank_top_n: Number(val("cf_mem_rerank_top_n")) || 20, rerank_blend: Number(val("cf_mem_rerank_blend")) || 0.85,
        mem_processor_model: val("cf_mem_mem_processor_model") };
    }
    const r = await api.saveConfigV2(section, patch);
    api.uiEvent("config.save", { section });
    if (!r.ok) return { ok: false, message: r.error || t("config.msg.error") };
    await reloadCfg();
    return { ok: true, message: t("config.msg.saved_next_turn").replace(/^✓\s*/, "") };
  }

  async function saveVoice() {
    const payload = {};
    (cfg.voice.knobs || []).forEach(k => { const el = document.getElementById("cfv_" + k.key); if (el) payload[k.key] = el.value; });
    const r = await api.saveSettings(payload);
    if (!r.ok) return { ok: false, message: t("config.msg.no_changes") };
    let note = r.note || t("config.msg.saved");
    if (r.needs_reconnect) {
      try { await session.loadVoices(); } catch (_) {}
      if (session.isActive()) { msg(t("config.msg.applying_reconnect")); await session.reconnect(); note = t("config.msg.applied"); }
      else note = t("config.msg.saved_on_connect");
    }
    await reloadCfg();
    return { ok: true, message: String(note).replace(/^✓\s*/, "") };
  }

  async function saveKeys(envs) {
    let n = 0; for (const e of envs) { if (await saveKey(e)) n++; }
    await reloadApis();
    await reloadCfg();
    return { ok: true, message: n ? t("config.msg.keys_saved", { n }).replace(/^✓\s*/, "") : t("config.msg.no_changes") };
  }

  async function refreshApis(b) {
    b.disabled = true; msg(t("config.msg.querying_balances"));
    try { await reloadApis(true); msg(t("config.msg.balances_updated")); } catch (_) { msg(t("config.msg.couldnt_query"), true); } finally { b.disabled = false; }
  }

  async function reloadApis(refresh) {
    const r = await api.getApiSummary(refresh);
    cfg.apis = r.apis || [];
    store.setApiSummary(r.apis || []); store.setApiAlerts(r.alerts || []);
    const tb = document.getElementById("cf_apis_tbody");
    if (tb) tb.innerHTML = S.apisRows(cfg);
  }

  // The login window opens INSIDE the click and is pointed at Spotify when the endpoint answers (a window
  // opened after an await is blocked in silence). Your own app's Client ID is optional: the shipped one is
  // used when it is there.
  async function connectSpotify(btn) {
    btn.disabled = true; msg(t("config.msg.opening_spotify"));
    const popup = openConsent();
    try {
      const cid = (val("cx_sp_cid") || "").trim();
      const r = await fetch("/api/spotify/connect", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cid ? { client_id: cid } : {}) }).then(x => x.json());
      if (r.url) { landConsent(popup, { ok: true, url: r.url }, "spotify"); msg(t("config.msg.spotify_authorize")); }
      else { try { popup && popup.close(); } catch (_) {} msg("✗ " + (r.error === "no_client_id" ? t("config.cx.sp_need_id") : (r.error || t("config.msg.couldnt_start")))); }
    } catch (_) { try { popup && popup.close(); } catch (_2) {} msg(t("config.msg.error_generic")); } finally { btn.disabled = false; }
  }
  async function disconnectSpotify(btn) {
    btn.disabled = true;
    try { await fetch("/api/spotify/disconnect", { method: "POST" }); msg(t("config.msg.spotify_disconnected")); await load(); } catch (_) {} finally { btn.disabled = false; }
  }

  // ═══ PESTAÑA CONECTORES (V2-083) ═══════════════════════════════════════════════════════════════════════
  // Etiqueta traducida directa (without depender of the texto renderizado by badge): connected/error/off.
  const cxBadge = c => {
    if (c.services) {   // the Google group: how many of its services are linked, never a blanket «connected»
      const n = c.services.filter(x => x.connected).length;
      return `<span class="cf-badge cf-${n ? "ok" : "off"}">${esc(t("config.cx.of_services", { n, total: c.services.length }))}</span>`;
    }
    const st = c.connected ? (c.warning ? "warn" : "ok") : (c.status === "error" ? "error" : "off");
    const label = c.connected ? (c.warning ? t(`config.cx.warn.${c.warning}`) : t("config.cx.connected"))
      : (c.status === "error" ? t("config.badge.error") : t("config.cx.disconnected"));
    return `<span class="cf-badge cf-${esc(st)}">${label}</span>`;
  };

  function sec_connectors() {
    const cs = cfg.connectors || [];
    if (!cs.length) return page({ id: "conectores", crumb: [t("config.tab.conectores")], title: t("config.tab.conectores"), body: `<p class="set-hint">${t("config.cx.load_error")}</p>` });
    const fams = [["google", "Google"], ["mensajeria", t("config.cx.fam_messaging")], ["musica", t("config.cx.fam_music")],
                  ["archivos", t("config.cx.fam_files")], ["fotos", t("config.cx.fam_photos")],
                  ["video", t("config.cx.fam_video")], ["agenda", t("config.cx.fam_calendar")],
                  ["contactos", t("config.cx.fam_contacts")],
                  ["infra", t("config.cx.fam_infra")]];
    const ui = { t, esc, badge: cxBadge };
    const famTitle = f => (fams.find(([x]) => x === f) || [f, f])[1];
    const view = groupGoogle(cs);
    const c = cxFocus && view.find(x => x.id === cxFocus);
    if (c) {
      if (isSettling(c)) settle();
      // One connector: its own breadcrumb (← back to the list) and hero head the page; same column, same buttons.
      return `<section class="set-page set-page--cx" data-settings-page="conectores">` +
        connectorWizard(c, cxStep, connectorForm(c, famTitle, { ...ui, service: cxService, consent: cxConsent }), famTitle(c.family), { ...ui, returnTo: cxReturn }) + `</section>`;
    }
    // The list's way out sits in the page's bar, beside the refresh.
    return page({ id: "conectores", crumb: [t("config.tab.conectores")], title: t("config.tab.conectores"), sub: t("config.cxw.choose"),
      body: connectorList(view, fams, ui),
      tools: btn(t("config.cx.refresh_status"), { cls: "cf-cx-refresh" }) + btn(t("config.cxw.close"), { attrs: 'data-cx-close="1"' }) });
  }
  // A QR to appear, a scan to land: while the chosen connector is still settling AND on screen, its state is
  // re-read. No time cap: Telegram rotates its QR every 30 s, and a cap (it was 2 min) left a dead code on the
  // screen that the phone then refused — finding the phone's «link device» menu takes longer than that.
  async function settle() {
    if (cxPolling) return;
    cxPolling = true;
    const focus = cxFocus;
    try {
      while (activeTab === "conectores" && cxFocus === focus && store.configOpen()) {
        await sleep(2000);
        const before = JSON.stringify((cfg.connectors || []).find(x => x.id === cxFocus) || {});
        try { cfg.connectors = (await api.getConnectors()).connectors || []; } catch (_) {}
        const now = (cfg.connectors || []).find(x => x.id === cxFocus);
        const typing = bodyEl.contains(document.activeElement) && /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName);
        if (JSON.stringify(now || {}) !== before && !typing) render();
        if (!isSettling(now)) { render(); break; }
      }
    } finally { cxPolling = false; }
  }

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  async function reloadConnectors() {
    try { cfg.connectors = (await api.getConnectors()).connectors || []; } catch (_) {}
    if (activeTab === "conectores") render();
  }
  async function pollConnectors() {   // tras conectar mensajería, the QR/estado tardan un momento en aparecer
    for (let i = 0; i < 6; i++) { await sleep(1500); await reloadConnectors(); }
  }

  // An OAuth consent window has to be opened INSIDE the click: one opened after an `await` is blocked by every
  // mainstream browser without a word (the canvas learned it in V2-679, `desktop._connectFlow`). So it opens
  // blank now and is pointed at Google's URL when the endpoint answers — or closed if it refuses.
  const OAUTH_ACTS = new Set(["calendar-connect", "contacts-connect", "cloudfiles-connect", "photos-connect", "video-connect"]);
  const openConsent = () => {
    try { return (window.innerWidth || 0) < 700 ? window.open("", "zaelar_connect") : window.open("", "zaelar_connect", "width=520,height=760"); }
    catch (_) { return null; }
  };
  function landConsent(popup, r, id) {
    if (!(r && r.ok && r.url)) { try { popup && popup.close(); } catch (_) {} msg("✗ " + ((r && r.error) || t("config.msg.error"))); return; }
    // A window the browser refuses is not an error of ours — but it IS something the operator has to be told,
    // with a link he can click himself: a click of his own is never blocked.
    let opened = false;
    try { if (popup) { popup.location = r.url; opened = true; } else opened = !!window.open(r.url, "_blank"); } catch (_) { opened = false; }
    if (opened) { cxConsent = null; msg(t("config.msg.connecting", { id })); }
    else { cxConsent = { id, url: r.url }; msg(t("config.cx.popup_blocked_short")); if (activeTab === "conectores") render(); }
    waitConnected(id);
  }
  // The consent happens in Google's window, at the operator's pace: watch THAT connector until it lands (3 min).
  async function waitConnected(id) {
    for (let i = 0; i < 90 && store.configOpen(); i++) {
      await sleep(2000);
      try { cfg.connectors = (await api.getConnectors()).connectors || []; } catch (_) { continue; }
      if (((cfg.connectors || []).find(x => x.id === id) || {}).connected) { cxConsent = null; msg(t("config.msg.connected", { id })); break; }
    }
    if (activeTab === "conectores") render();
  }

  async function cxAct(act, id, btn) {
    btn.disabled = true;
    const popup = OAUTH_ACTS.has(act) ? openConsent() : null;
    try {
      if (act === "disconnect") {
        if (id === "gdrive" || id === "onedrive") { await api.cloudFilesDisconnect(id); msg(t("config.msg.disconnected", { id })); }
        else if (id === "google-photos") { await api.photosDisconnect(); msg(t("config.msg.disconnected", { id })); }
        else if (id === "youtube") { await api.videoDisconnect(id); msg(t("config.msg.disconnected", { id })); }
        else if (btn.dataset.fam === "agenda") { await api.calendarDisconnect(id); msg(t("config.msg.disconnected", { id })); }
        else if (btn.dataset.fam === "contactos") { await api.contactsDisconnect(); msg(t("config.msg.disconnected", { id })); }
        else if (id === "spotify") { await disconnectSpotify(btn); }
        else if (id === "architect") { await api.architectDisconnect(); msg(t("config.msg.architect_revoked")); }
        else { await api.disconnectMessaging(id, {}); msg(t("config.msg.disconnected", { id })); }
        await reloadConnectors();
      } else if (act === "connect") {
        if (id === "spotify") { await connectSpotify(btn); return; }
        let payload = {};
        if (id === "telegram") {
          payload = { api_id: String(val("cx_tg_api_id") || "").trim(), api_hash: String(val("cx_tg_api_hash") || "").trim() };
          // Said HERE, beside the two boxes, before any round-trip — not as a server sentence in the top bar.
          const shipped = !!((cfg.connectors || []).find(x => x.id === "telegram") || { config: {} }).config.app_shipped;
          if (shipped) payload = {};                                                  // the install's app: QR only
          else if (!/^\d+$/.test(payload.api_id) || !payload.api_hash) { msg("✗ " + t("config.cxw.telegram.missing")); return; }
        }
        if (id === "email") {
          // The provider PRINTS the password in groups; IMAP AUTH does not want the spaces.
          payload = { email_address: val("cx_em_address"), email_password: String(val("cx_em_pass") || "").replace(/\s+/g, ""),
                      provider: val("cx_em_provider") };
          if (payload.provider === "other") { payload.imap_host = val("cx_em_imap"); payload.smtp_host = val("cx_em_smtp"); }
        }
        const r = await api.connectMessaging(id, payload);
        msg(r.ok ? t("config.msg.connecting", { id }) : ("✗ " + (r.error || t("config.msg.error"))));
        pollConnectors();
      } else if (act === "contacts-connect") {
        const r = await api.contactsConnect({ client_id: val("cx_g_id"), client_secret: val("cx_g_sec") });
        landConsent(popup, r, id);
      } else if (act === "photos-connect" || act === "video-connect" || act === "calendar-connect") {
        const payload = { client_id: val("cx_g_id"), client_secret: val("cx_g_sec") };
        if (act === "video-connect" || act === "calendar-connect") payload.provider = id;
        const r = act === "photos-connect" ? await api.photosConnect(payload)
          : (act === "video-connect" ? await api.videoConnect(payload) : await api.calendarConnect(payload));
        landConsent(popup, r, id);
      } else if (act === "cloudfiles-connect") {
        const r = await api.cloudFilesConnect({
          provider: id, client_id: val(`cx_cf_id_${id}`) ?? val("cx_g_id"), client_secret: val(`cx_cf_sec_${id}`) ?? val("cx_g_sec"),
          tier: val(`cx_cf_tier_${id}`),
        });
        landConsent(popup, r, id);
      } else if (act === "architect-save") {
        const token = val("cx_arch_token"), url = val("cx_arch_url");
        const r = await api.architectConnect({ token, url });
        // A hosted agent needs the daemon's public address and checks it answers; its two refusals are sentences.
        const why = { hosted_needs_public_url: "config.msg.architect_public_url", daemon_unreachable: "config.msg.architect_unreachable" };
        msg(r.ok ? t("config.msg.token_saved") : ("✗ " + (why[r.error] ? t(why[r.error]) : (r.error || t("config.msg.error"))))); await reloadConnectors();
      } else if (act === "mesh-add") {
        const r = await api.meshkoreAdd({ name: val("cx_mk_name"), cluster_id: val("cx_mk_cid"), token: val("cx_mk_token"), handle: val("cx_mk_handle") });
        msg(r.ok ? t("config.msg.cluster_added") : ("✗ " + (r.error || t("config.msg.error")))); await reloadConnectors();
      } else if (act === "mesh-remove") {
        await api.meshkoreRemove(btn.dataset.name); msg(t("config.msg.cluster_revoked")); await reloadConnectors();
      }
    } catch (e) { try { popup && popup.close(); } catch (_) {} msg(t("config.msg.error_generic")); } finally { btn.disabled = false; }
  }

  // A profile added later ships its `label` before anyone writes its bundle row; `t()` answers with the raw key
  // when it has none, so the card falls back to the label instead of painting `config.theme.profile_x`.
  function themeName(id, th) {
    const key = "config.theme.profile_" + id, s = t(key);
    return (s && s !== key) ? s : (th.label || id);
  }

  // ═══ LANGUAGE (V2-694) — changed from Settings by hand, never by voice. It posts to `/api/i18n/choose/{code}` and
  // NEVER to the raw `stt_language` knob: that endpoint LOCKS the choice, generates the bundle for a language we do
  // not ship, realigns the TTS voice and speaks the confirmation. It asks TWICE on purpose: it re-translates every
  // label, prompt and widget, and one stray click on a dropdown should not start it.
  async function applyLanguage(btn) {
    const sel = document.getElementById("cf_lang_sel");
    const code = sel && sel.value;
    if (!code || code === langPicker.active) { msg(t("config.lang.same")); return; }
    if (!langArmed) { langArmed = true; render(); return; }   // the second click is the consent
    langArmed = false;
    btn.disabled = true;
    msg(t("config.lang.working"));
    try {
      const r = await fetch("/api/i18n/choose/" + encodeURIComponent(code), { method: "POST" }).then(x => x.json());
      if (!r || r.ok === false) { msg(t("config.msg.error_generic")); return; }
      langPicker.active = code;
      msg(t("config.lang.done"));
    } catch (_) { msg(t("config.msg.error_generic")); }
    finally { btn.disabled = false; render(); }
  }

  async function load() {
    msg(""); bodyEl.innerHTML = `<p class="cf-loading">${t("config.loading")}</p>`;
    try {
      cfg = await api.getConfig();
      // V2-083: conectores + widgets for sus pestañas (best-effort, en paralelo).
      try {
        const [cx, wr] = await Promise.all([api.getConnectors(), api.getWidgetsRegistry()]);
        cfg.connectors = (cx && cx.connectors) || [];
        cfg.widgets = (wr && wr.registry) || [];
      } catch (_) { cfg.connectors = cfg.connectors || []; cfg.widgets = cfg.widgets || []; }
      // Best-effort and in parallel with the rest: an unreachable i18n state costs the language ROW, never the
      // whole panel — every other setting still has to be reachable.
      try {
        const st = await fetch("/api/i18n/state").then(r => r.json());
        langPicker = { rows: (st && st.picker) || [], active: (st && st.active) || "" };
      } catch (_) { langPicker = { rows: [], active: "" }; }
      render();
      store.setApiSummary(cfg.apis || []);
      store.setApiAlerts((cfg.apis || []).filter(a => a.state === "warn" || a.state === "error"));
    } catch (e) { bodyEl.innerHTML = `<p class="cf-loading">${t("config.load_config_error")}</p>`; }
  }
  const close = () => { dropPreview(); cxReturn = null; store.setConfigOpen(false); };
  const onKey = e => { if (e.key === "Escape" && store.configOpen()) close(); };
  window.addEventListener("keydown", onKey);

  ovl = h("div", { class: () => "cfgfull" + (store.configOpen() ? " open" : ""), onClick: e => { if (e.target === ovl) close(); } },
    h("div", { class: "cf-shell" },
      h("div", { class: "cf-head" },
        h("h3", {}, raw(GEAR_ICON), () => t("config.tab.settings")),
        h("span", { class: "cf-msg", ref: el => (msgEl = el) }),
        h("button", { class: "cf-x", onClick: close }, () => t("config.close")),
      ),
      h("div", { class: "cf-body", ref: el => (bodyEl = el) }, h("p", { class: "cf-loading" }, () => t("config.loading_short"))),
    ),
  );

  let wasOpen = false;
  createEffect(() => {
    const o = store.configOpen();
    if (o && !wasOpen) {
      // V2-561 — a caller (the ChatWall connector catalog) can ask to land on a specific tab, e.g.
      // "conectores", instead of always reopening on whatever `activeTab` was left at. Consumed once so a
      // later plain ⚙ click is not forced onto the same tab forever.
      // Both requests are READ before either is cleared: clearing one re-runs this effect synchronously, and a
      // re-run that consumed the connector first left this run reading null (the chosen connector never opened).
      const want = store.configInitialTab(), cxWant = store.configConnector(), from = store.configFrom();
      if (want && TABS.some(t => t.id === want)) { activeTab = want; store.setConfigInitialTab(null); }
      // …and the catalog row it was clicked on: that connector opens alone, on its first step (consumed once too).
      store.setConfigFrom(null); const wantSec = store.configInitialSection(); if (wantSec && SECTIONS.some(x => x.id === wantSec)) { activeTab = "settings"; activeSec = wantSec; store.setConfigInitialSection(null); }
      navOpen = !(want || cxWant);   // phone: a plain ⚙ opens on the menu; a request opens what it asked for
      if (cxWant) { activeTab = "conectores"; ({ focus: cxFocus, service: cxService } = focusOf(cxWant)); cxStep = 0; cxReturn = { from: from || "" }; store.setConfigConnector(null); }
      else { cxReturn = null; if (want) { cxFocus = null; cxService = ""; cxStep = 0; } }
      load();
    }
    wasOpen = o;
  });
  return ovl;
}

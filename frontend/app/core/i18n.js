// ============================================================================
// i18n.js — runtime UI localization for the frontend (V2-089 multilingual).
//
// SINGLE SOURCE OF TRUTH = the backend JSON bundles under config/i18n/ (English
// is the base/manifest; Spanish is preset; ANY other language is generated on
// the fly by the i18n engine — see .meshkore/docs/architecture/zaelar-i18n.md).
// The frontend never hardcodes copy: it FETCHES the active bundle from
// /api/i18n/bundle/<code> and caches it in localStorage, so repeat visits paint
// instantly (no flash) while the boot veil covers the very first fetch.
//
// t(key) is REACTIVE on TWO things: the active language (store.lang()) AND the
// CONTENT of the loaded bundles. Any t() inside a dom.js function-prop/child
// re-renders when the operator switches language (applyLang) AND when a bundle
// arrives with strings the cached copy didn't have — no page reload, no voice
// reconnect. That second dependency is not optional: the first paint comes from
// the localStorage cache, which is stale by definition right after a release.
//
// Resolution order: active-language bundle → English base → the key itself.
// English is guaranteed complete (it's the manifest), so it's always a safe net.
// ============================================================================
import * as store from "./store.js?v=2";
import { createSignal } from "./reactive.js?v=2";   // SAME specifier as store.js → same instance (V2-087 lesson)

const BUNDLES = {};            // code -> { key: string }
const _loading = {};           // code -> Promise (dedupe concurrent fetches)
const CACHE_KEY = (code) => "hb_i18n_" + code;

// BUNDLE CONTENT, not just the language CODE (fix 2026-08-09). `t()` depended only on `store.lang()`, and
// `setLang` is a no-op when the value is unchanged (Solid semantics, `Object.is`) → at startup the UI rendered
// the CACHED localStorage bundle and, when the backend response brought NEW keys, stored them in memory but
// **did not re-render anything**: new strings remained their raw key (`debug.col_time`) until the operator changed
// language or cleared localStorage. This counter is read inside `t()` and incremented whenever a bundle REALLY
// changes → the UI reconciles itself. It also covers an upgrade to a generated language (same code, new strings),
// which had the same blind spot.
const [bundleRev, setBundleRev] = createSignal(0);
function bumpIfChanged(code, dict) {
  const prev = BUNDLES[String(code)];
  BUNDLES[String(code)] = dict;
  // Compare content: an identical re-fetch (the normal case) must not invalidate the entire tree.
  if (JSON.stringify(prev) !== JSON.stringify(dict)) setBundleRev((n) => n + 1);
}

export function registerBundle(code, dict) { if (dict) bumpIfChanged(code, dict); }
export function hasBundle(code) { return !!BUNDLES[String(code)]; }
export function available() { return Object.keys(BUNDLES); }

// Hydrate synchronously from the localStorage cache at module load, so the FIRST paint already has strings
// (English base + the last active language) with zero network wait. The fetch below then reconciles.
(function hydrate() {
  for (const code of ["en", store.lang()]) {
    try { const raw = localStorage.getItem(CACHE_KEY(code)); if (raw) BUNDLES[code] = JSON.parse(raw); } catch (_) {}
  }
})();

// SURFACE VARIANT. The native companion marks <html class="in-app"> at document start (mobile-app/www/in-app.js).
// Inside it, a key that has a `<key>@app` sibling in the bundle reads the sibling — the wording a store build needs
// is DATA in the bundle, per language, and every other surface keeps the plain key. No sibling = the plain string.
const SURFACE = (() => {
  try { return document.documentElement.classList.contains("in-app") ? "@app" : ""; } catch (_) { return ""; }
})();

// t(key, params?) — localized string. Reads store.lang() (reactive dependency).
// The cold start has no bundle yet. Nothing rendered by a module is on screen then: the one loader (V2-881) is
// narrated by core/preboot.js, which reads the cached bundle with its own English floor — so `t()` keeps a single
// fallback chain and a missing string stays visible as its key.
export function t(key, params) {
  const code = store.lang();
  bundleRev();                            // reactive dependency: re-renders when bundle content changes
  const dict = BUNDLES[code] || BUNDLES.en || {};
  const en = BUNDLES.en || {};
  let s = SURFACE ? (dict[key + SURFACE] ?? en[key + SURFACE]) : null;
  if (s == null) s = dict[key];
  if (s == null) s = en[key];
  if (s == null) s = key;                 // last resort: show the key (visible = "needs a string")
  if (params) for (const k in params) s = s.split("{" + k + "}").join(String(params[k]));
  return s;
}

// loadBundle(code) — ensure a bundle is in memory, fetching it from the backend (which serves presets from
// config/i18n/ and generated languages the engine produced). Caches to localStorage for a flash-free next boot.
export async function loadBundle(code) {
  code = String(code || "en");
  if (_loading[code]) return _loading[code];
  _loading[code] = (async () => {
    try {
      const r = await fetch("/api/i18n/bundle/" + encodeURIComponent(code), { cache: "no-cache" });
      const d = await r.json();
      if (d && d.strings && Object.keys(d.strings).length) {
        bumpIfChanged(code, d.strings);   // ← the missing reconciliation: the fetch can bring new keys
        try { localStorage.setItem(CACHE_KEY(code), JSON.stringify(d.strings)); } catch (_) {}
      }
    } catch (_) {}
    return BUNDLES[code] || null;
  })();
  const out = await _loading[code];
  delete _loading[code];
  return out;
}

// applyLang(code) — make `code` the active UI language: load its bundle, flip the signal (re-renders every
// t() in the tree), persist the mirror for a flash-free next boot. Falls back to English if unavailable.
export async function applyLang(code) {
  code = String(code || "en");
  await loadBundle(code);
  const final = BUNDLES[code] ? code : "en";
  store.setLang(final);
  // <html lang> follows the instance language (screen readers, hyphenation, `document.documentElement.lang` readers).
  try { document.documentElement.lang = final; } catch (_) {}
  try { localStorage.setItem("hb_lang", final); } catch (_) {}
  return final;
}

// initI18n() — at boot: always have English (the fallback manifest) loaded, then reconcile the UI language with
// the backend's active language (ZAELAR_LANGUAGE is the single source of truth). t() is reactive, so any
// correction re-renders the UI in place — behind the boot veil this is invisible.
export async function initI18n() {
  loadBundle("en");                        // fallback net, fire-and-forget (cache usually already served it)
  try {
    const r = await fetch("/api/i18n/state", { cache: "no-cache" });
    const d = await r.json();
    if (d && d.active) await applyLang(d.active);
  } catch (_) { await applyLang(store.lang()); }
}

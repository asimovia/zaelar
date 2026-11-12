// Inside the native companion (<html class="in-app">, set at document start by mobile-app/www/in-app.js) a key
// that has a `<key>@app` sibling in the bundle reads the sibling; a key without one reads the plain string; a
// language that lacks the sibling falls back to the English sibling before the plain key. A browser never reads
// a sibling. The wording is DATA in the bundle — t() knows no word.
import assert from "node:assert/strict";

const mem = new Map([["hb_lang", "es"]]);
globalThis.localStorage = {
  getItem: (k) => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: (k) => mem.delete(k),
};
const classes = new Set(["in-app"]);
globalThis.document = { documentElement: { classList: { contains: (c) => classes.has(c) } } };

const EN = { "nav.list": "Apps", "nav.list@app": "Views", "nav.next": "Next app", "nav.next@app": "Next view", "nav.back": "Back" };
const ES = { "nav.list": "Aplicaciones", "nav.list@app": "Vistas", "nav.next": "App siguiente", "nav.back": "Atrás" };

// `?v=2` is the specifier i18n.js itself uses for store/reactive (one module graph, V2-087).
const app = await import("../../../../frontend/app/core/i18n.js?v=2");
app.registerBundle("en", EN);
app.registerBundle("es", ES);
assert.equal(app.t("nav.list"), "Vistas", "inside the app the sibling of the active language is read");
assert.equal(app.t("nav.next"), "Next view", "a language without the sibling reads the English sibling, never the plain wording");
assert.equal(app.t("nav.back"), "Atrás", "a key with no sibling reads the plain string");
assert.equal(app.t("nav.missing"), "nav.missing", "a missing key still shows itself");

// A browser tab: same bundles, no mark on <html> → the plain strings. A second specifier = a second instance,
// whose surface is read when IT loads.
classes.clear();
const web = await import("../../../../frontend/app/core/i18n.js?surface=web");
web.registerBundle("en", EN);
web.registerBundle("es", ES);
assert.equal(web.t("nav.list"), "Aplicaciones", "a browser read the app's wording");
assert.equal(web.t("nav.next"), "App siguiente");

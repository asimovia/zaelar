// The boot screen speaks the INSTANCE's language, never the browser's (2026-10-21).
//
// `preboot.js` read `navigator.language`: an English instance in a Spanish browser booted in Spanish. It now reads
// the mirror `core/i18n.js` keeps (`hb_lang` + the cached `hb_i18n_<code>` bundle), and English with no mirror.
// Runs the REAL file in a minimal DOM. Usage: node <this> <lang|""> <browser-language>  → prints the title.
import fs from "node:fs";
import vm from "node:vm";

const [, , lang, browser] = process.argv;
const el = () => ({ className: "", textContent: "", innerHTML: "", classList: { add() {}, remove() {} },
  appendChild() {}, insertBefore() {}, replaceWith() {}, setAttribute() {}, querySelector: () => null });
const made = [];
const mem = new Map();
if (lang) {
  mem.set("hb_lang", lang);
  mem.set("hb_i18n_" + lang, JSON.stringify({ "preboot.boot.title": "BUNDLE:" + lang }));
}
const ctx = {
  navigator: { language: browser },
  localStorage: { getItem: (k) => (mem.has(k) ? mem.get(k) : null) },
  document: {
    getElementById: () => el(),
    createElement: () => { const e = el(); made.push(e); return e; },
    head: { appendChild() {} },
  },
  window: {},
  fetch: () => new Promise(() => {}),
  setTimeout: () => 0, clearTimeout() {}, Date, Math, JSON, String,
};
vm.runInNewContext(fs.readFileSync(new URL("../../../../frontend/app/core/preboot.js", import.meta.url), "utf8"), ctx);
const title = made.find((e) => e.className === "pb-title");
console.log(title ? title.textContent : "");

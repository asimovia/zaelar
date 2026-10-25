// V2-796 (node 4.271) — the phone is offered the app first, then notifications, and never nagged.
// Also pins the service worker's push half: it SHOWS every push (iOS revokes a subscription whose pushes are not
// shown) and reports the click back to the ledger. «Never caches» stays node 4.18's.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../../..");
const { step } = await import(join(ROOT, "frontend/mobile/app/shell/install-step.js"));

const base = { installed: false, os: "ios", canAsk: false, snoozedInstall: false, snoozedPush: false };
assert.equal(step(base), "install", "an iPhone in Safari is offered the install");
assert.equal(step({ ...base, snoozedInstall: true }), "", "iOS cannot push from a tab: nothing else to offer");
assert.equal(step({ ...base, os: "android", snoozedInstall: true, canAsk: true }), "push", "Android can push from a tab");
assert.equal(step({ ...base, installed: true, canAsk: true }), "push", "installed → turn on notifications");
assert.equal(step({ ...base, installed: true, canAsk: false }), "", "granted or denied → nothing (no nagging)");
assert.equal(step({ ...base, installed: true, canAsk: true, snoozedPush: true }), "", "«not now» is honoured");
assert.equal(step({ ...base, os: "desktop", canAsk: true }), "push", "a desktop browser is never told to install");

const sw = readFileSync(join(ROOT, "frontend/mobile/sw.js"), "utf8");
assert.match(sw, /addEventListener\("push"/, "the worker handles push");
assert.match(sw, /showNotification\(/, "and shows every push");
assert.match(sw, /addEventListener\("notificationclick"/, "a click is handled");
assert.match(sw, /\/api\/notices\/\$\{[^}]+\}\/seen/, "and reported to the ledger as seen");

const surfaces = readFileSync(join(ROOT, "frontend/mobile/app/shell/mobile-surfaces.js"), "utf8");
assert.match(surfaces, /comp: InstallBanner/, "the banner is mounted from the canonical list");

for (const lang of ["es", "en"]) {
  const ui = JSON.parse(readFileSync(join(ROOT, `i18n/genesis/${lang}/ui.json`), "utf8"));
  for (const k of ["install.title", "install.body", "install.button", "install.later", "install.ios_steps",
                   "install.android_steps", "push.title", "push.body", "push.button", "push.denied",
                   "push.settings_label", "push.settings_on", "push.settings_off", "push.test", "config.sec.notices"]) {
    assert.ok(ui[k], `${lang}/ui.json has ${k}`);
  }
}
console.log("ok");

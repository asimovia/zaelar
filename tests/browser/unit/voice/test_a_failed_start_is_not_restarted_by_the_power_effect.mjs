// test_a_failed_start_is_not_restarted_by_the_power_effect.mjs — a voice start that fails is retried by its bounded
// retry, never by the ⏻ effect that brings the voice back. Runs main.js's OWN `ensureVoice` and effect over the
// engine's reactive core, with a session whose start fails the way a 503 `voice_starting` does (asynchronously).
// Run: node tests/browser/unit/voice/test_a_failed_start_is_not_restarted_by_the_power_effect.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const R = await import("../../../../frontend/app/core/reactive.js?v=2");
const main = readFileSync(new URL("../../../../frontend/app/main.js", import.meta.url), "utf8");

function block(src, from) {          // the text from `from` to its matching closing brace
  let i = src.indexOf("{", from), depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}" && --depth === 0) return src.slice(from, j + 1);
  }
  throw new Error("unbalanced");
}
const fnAt = main.indexOf("function ensureVoice()");
assert.ok(fnAt >= 0, "main.js has no ensureVoice: this test would be watching nothing");
const anchor = main.indexOf("if (store.powerOff() || store.langOnboardOpen()) return;");
assert.ok(anchor >= 0, "the ⏻-back-ON effect moved: this test would be watching nothing");
const effAt = main.lastIndexOf("createEffect(() => {", anchor);
const src = block(main, fnAt) + "\n" + block(main, effAt) + ");";

const sig = (v) => R.createSignal(v);
const [powerOff, setPowerOff] = sig(false), [lang, setLang] = sig(false), [pending] = sig(false);
const [started, setStarted] = sig(false), [starting, setStarting] = sig(false);
const store = { powerOff, langOnboardOpen: lang, powerOnPending: pending, started, starting };
const answers = [];                  // the token door's replies still travelling
let starts = 0;
const session = {
  start() {                          // what session-lk.start does on a 503 voice_starting: up, then down again
    starts++; setStarting(true); setStarted(true);
    answers.push(() => { setStarted(false); setStarting(false); });
    return Promise.resolve();
  },
};
new Function("createEffect", "untrack", "store", "session", src)(R.createEffect, R.untrack, store, session);
assert.equal(starts, 1, "the effect starts the voice once at boot");

for (let i = 0; i < 20 && answers.length; i++) answers.shift()();
assert.equal(starts, 1, `a failed start was re-fired by the ⏻ effect ${starts - 1} times: a tight loop past the bounded retry`);

setPowerOff(true); setPowerOff(false);
assert.equal(starts, 2, "⏻ coming back ON still brings the voice up");
answers.splice(0).forEach((f) => f());
setLang(true); setLang(false);
assert.equal(starts, 3, "the language veil closing still brings the voice up");
console.log("ok");

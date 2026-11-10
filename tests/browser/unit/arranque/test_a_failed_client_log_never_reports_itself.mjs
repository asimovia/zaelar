// ============================================================================
// test_a_failed_client_log_never_reports_itself.mjs
//
// The page reports its own JS errors and unhandled rejections through `api.clientLog`. That call's POST used to
// return a rejected promise nobody caught, so ONE failed report raised `unhandledrejection`, whose handler called
// `clientLog` again: an endless loop of requests that starved every other fetch of the tab. A report must swallow
// its own failure, and a storm of reports is capped per minute.
//
// Run: node tests/browser/unit/arranque/test_a_failed_client_log_never_reports_itself.mjs
// ============================================================================
import assert from "node:assert/strict";

globalThis.location = { pathname: "/" };
globalThis.localStorage = { getItem: () => "dev1", setItem() {} };
let calls = 0;
const rejections = [];
process.on("unhandledRejection", (r) => rejections.push(r));
globalThis.fetch = () => { calls += 1; return Promise.reject(new TypeError("Failed to fetch")); };

const api = await import("../../../../frontend/app/services/api.js?v=2");

// ── 1. a failed report leaves no rejection behind (the loop's fuel) ─────────────────────────────────────────
api.clientLog("⚠️ JS error", { text: "x" });
await new Promise((r) => setTimeout(r, 20));
assert.equal(calls, 1);
assert.equal(rejections.length, 0, "a failed client-log POST must not surface as an unhandled rejection");

// ── 2. a storm of the SAME report is capped per minute; a different report still goes out ──────────────────
for (let i = 0; i < 500; i++) api.clientLog("⚠️ promesa sin capturar", { text: "y" });
await new Promise((r) => setTimeout(r, 20));
assert.equal(calls, 1 + api.CLIENT_LOG_PER_MIN, `the same report capped at ${api.CLIENT_LOG_PER_MIN}/min, sent ${calls - 1}`);
api.clientLog("🔊 device", { state: "problem:silent_while_speaking" });
await new Promise((r) => setTimeout(r, 20));
assert.equal(calls, 2 + api.CLIENT_LOG_PER_MIN, "a different report is never held back by another one's storm");
assert.equal(rejections.length, 0);
console.log("ok");

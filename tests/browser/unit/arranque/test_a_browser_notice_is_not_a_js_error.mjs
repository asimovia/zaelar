// test_a_browser_notice_is_not_a_js_error.mjs — V2-873: an `error` event with no exception is a browser notice.
// Run: node tests/browser/unit/arranque/test_a_browser_notice_is_not_a_js_error.mjs
import assert from "node:assert/strict";
globalThis.location = { pathname: "/" };
globalThis.localStorage = { getItem: () => "dev1", setItem() {} };
const { errorLabel } = await import("../../../../frontend/app/services/api.js?v=2");

// What Chrome dispatches for a layout that settles over two frames: an ErrorEvent with a message and no Error.
const notice = { message: "ResizeObserver loop completed with undelivered notifications.", error: null, filename: "", lineno: 0 };
assert.equal(errorLabel(notice), "ℹ️ browser notice (no exception)");
// An opaque cross-origin script carries no exception either.
assert.equal(errorLabel({ message: "Script error.", error: null }), "ℹ️ browser notice (no exception)");
// A script that THREW: its Error object rides the event.
assert.equal(errorLabel({ message: "x is not a function", error: new TypeError("x is not a function") }), "⚠️ JS error");
assert.equal(errorLabel(undefined), "ℹ️ browser notice (no exception)");
console.log("ok");

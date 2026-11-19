// ============================================================================
// test_a_typed_echo_is_not_painted_again.mjs — INI-042 #36.
//
// Live: with the engine's loop held for seconds, he typed a line, then the next, and the engine's echo of the first
// (`text-injected chat`) came back AFTER the second bubble. The wall compared the echo with the LAST line only, so
// the first was painted again underneath. Drives the real `typed-echo.js`.
//
// Run: node tests/browser/unit/chat/test_a_typed_echo_is_not_painted_again.mjs
// ============================================================================
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "../../../..");
const { createTypedEcho } = await import(path.join(root, "frontend/app/services/typed-echo.js"));

const ME = "computer:abc123", A = "Add a cello lesson on Thursday", B = "and dinner on Sunday";
const you = (text) => ({ role: "you", text });

{ // the echo of A lands after B was typed: A is already on this wall — not painted again
  const paints = createTypedEcho(), wall = [you(A), you(B)];
  assert.equal(paints(A, ME, ME, wall), false, "the late echo of an earlier line is painted again below the next");
  assert.equal(paints(B, ME, ME, wall), false);
}
{ // the same line typed twice here: two bubbles, two echoes, nothing more
  const paints = createTypedEcho(), wall = [you(A), you(A)];
  assert.equal(paints(A, ME, ME, wall), false);
  assert.equal(paints(A, ME, ME, wall), false);
}
{ // a line typed on ANOTHER screen is always painted here, even if the same words are on this wall
  const paints = createTypedEcho();
  assert.equal(paints(A, "mobile:zz9", ME, [you(A)]), true);
}
{ // a reload lost the bubble: the echo of this screen's own line is painted, once
  const paints = createTypedEcho(), wall = [];
  assert.equal(paints(A, ME, ME, wall), true);
  wall.push(you(A));
  assert.equal(paints(A, ME, ME, wall), true, "a second genuine echo after a painted one still paints");
}
{ // the screen id is compared as the engine stores it (`voice/screens.clean`: lowercase, safe characters)
  const paints = createTypedEcho();
  assert.equal(paints(A, "computer:abc123", "Computer:ABC123", [you(A)]), false);
}
console.log("ok");

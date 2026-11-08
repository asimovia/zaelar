// ============================================================================
// test_an_errand_reference_is_one_box_that_updates.mjs — V2-862.
//
// An errand that delivers into a card leaves ONE reference box on the chat wall (`store.upsertChatRef`, fed by the
// SSE `artifact` kind). The first event draws it where the conversation is; retitled / closed / a relay's re-open
// update it IN PLACE — it never doubles and never moves down the thread. `skipped` draws nothing (it is for the
// audit). A half-done errand keeps its box. The row carries its title as `text`, since a restored history keeps
// only rows with a string text.
//
// Run: node tests/browser/unit/chat/test_an_errand_reference_is_one_box_that_updates.mjs
// ============================================================================
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "../../../..");
const store = readFileSync(path.join(root, "frontend/app/core/store.js"), "utf8");
const i = store.indexOf("export const upsertChatRef");
const j = store.indexOf("\n};\n", i);
assert.ok(i > 0 && j > i, "upsertChatRef was not found in store.js — was it renamed?");
const shim = `
let msgs = [];
const setChatMsgs = (fn) => { msgs = fn(msgs); };
const _capChat = (xs) => xs;
${store.slice(i, j + 3)}
export const reset = () => { msgs = []; };
export const rows = () => msgs;
export const push = (m) => { msgs = [...msgs, m]; };
`;
const S = await import("data:text/javascript," + encodeURIComponent(shim));

for (const [lang, said, title, named] of [
  ["en", "Find me the exact bulb", "Kitchen hood light", "Your kitchen hood light — the exact fitting"],
  ["es", "Búscame la bombilla exacta", "Luz de la campana", "La luz de tu campana — el casquillo exacto"],
]) {
  S.reset();
  S.push({ role: "you", text: said });
  S.upsertChatRef({ kind: "artifact", label: "opened", ref: "t-9", surface: "informe", card: "documento",
                    title, state: "started" });
  S.push({ role: "agent", text: "…" });
  S.upsertChatRef({ kind: "artifact", label: "retitled", ref: "t-9", surface: "informe", card: "documento",
                    title: named, state: "started" });
  S.upsertChatRef({ kind: "artifact", label: "opened", ref: "t-9", surface: "informe", title: named,
                    state: "started" });                                   // a relay re-opens the same row
  S.upsertChatRef({ kind: "artifact", label: "closed", ref: "t-9", surface: "informe", card: "",
                    title: named, state: "partial", file: "documents/x.md" });
  const refs = S.rows().filter((m) => m.role === "ref");
  assert.equal(refs.length, 1, `[${lang}] one errand, one box`);
  assert.equal(S.rows()[1], refs[0], `[${lang}] the box stays where it was born in the thread`);
  assert.equal(refs[0].text, named, `[${lang}] it wears the composed name`);
  assert.equal(refs[0].state, "partial", `[${lang}] a half-done errand keeps its box, marked as such`);
  assert.equal(refs[0].card, "documento", `[${lang}] a later event without a card keeps the known one`);
  assert.equal(refs[0].file, "documents/x.md");
  assert.equal(typeof refs[0].text, "string", "a restored history keeps only rows with a string text");

  S.upsertChatRef({ kind: "artifact", label: "skipped", ref: "t-10", surface: "voz", reason: "no_card" });
  S.upsertChatRef({ kind: "artifact", label: "opened", ref: "", surface: "lista" });
  assert.equal(S.rows().filter((m) => m.role === "ref").length, 1, `[${lang}] skipped or unnamed events draw nothing`);
}

// Both shells draw the row through the ONE view (components/ChatRef.js), and it reopens through the one door.
const wall = readFileSync(path.join(root, "frontend/app/components/ChatWall.js"), "utf8");
const phone = readFileSync(path.join(root, "frontend/mobile/app/shell/ChatSheet.js"), "utf8");
const view = readFileSync(path.join(root, "frontend/app/components/ChatRef.js"), "utf8");
assert.match(wall, /m\.role === "ref"\) \{ rows\.push\(chatRefView\(m\)\)/, "the desktop wall draws the box");
assert.match(phone, /m\.role === "ref"\) return chatRefView\(m, "zm-msg"\)/, "the phone draws the same box");
assert.match(view, /api\.taskReopen\(m\.ref\)/, "the box reopens through the existing door");
assert.match(view, /hb:open-card/, "…and the card opens like every other click");
for (const lang of ["en", "es"]) {
  const ui = JSON.parse(readFileSync(path.join(root, `i18n/genesis/${lang}/ui.json`), "utf8"));
  for (const k of ["open", "untitled", "started", "done", "partial", "cancelled", "gone"]) {
    assert.ok(ui["chat.ref." + k], `[${lang}] chat.ref.${k} is translated`);
  }
}
console.log("ok — an errand reference is one box that updates");

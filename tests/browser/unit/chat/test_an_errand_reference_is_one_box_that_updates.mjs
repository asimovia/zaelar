// ============================================================================
// test_an_errand_reference_is_one_box_that_updates.mjs — V2-862.
//
// An errand that delivers into a card leaves ONE reference box on the chat wall (`legacy.upsertChatRef`, fed by the
// SSE `artifact` kind; writer `legacy:ref`, line id `ref_<ref>`). The first event draws it where the conversation is;
// retitled / closed / a relay's re-open update it IN PLACE (a `replace` of the same box) — it never doubles and never
// moves down the thread. `skipped` draws nothing (it is for the audit). A half-done errand keeps its box. The box
// carries its title as `text` and is a FINAL line, since a restored history keeps only final lines with their text.
//
// Driven on the REAL old-path writer attached to the REAL wall model (wallkit.mjs), no slice of a file.
//
// Run: node tests/browser/unit/chat/test_an_errand_reference_is_one_box_that_updates.mjs
// ============================================================================
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import { wall } from "./wallkit.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "../../../..");
const { keepable } = await import(pathToFileURL(path.join(root, "frontend/chat-wall/model.js")).href);

for (const [lang, said, title, named] of [
  ["en", "Find me the exact bulb", "Kitchen hood light", "Your kitchen hood light — the exact fitting"],
  ["es", "Búscame la bombilla exacta", "Luz de la campana", "La luz de tu campana — el casquillo exacto"],
]) {
  const w = await wall();
  w.legacy.youSaid(said);
  w.legacy.upsertChatRef({ kind: "artifact", label: "opened", ref: "t-9", surface: "informe", card: "documento",
                           title, state: "started" });
  w.legacy.pushAgentChat("…");
  w.legacy.upsertChatRef({ kind: "artifact", label: "retitled", ref: "t-9", surface: "informe", card: "documento",
                           title: named, state: "started" });
  w.legacy.upsertChatRef({ kind: "artifact", label: "opened", ref: "t-9", surface: "informe", title: named,
                           state: "started" });                            // a relay re-opens the same row
  w.legacy.upsertChatRef({ kind: "artifact", label: "closed", ref: "t-9", surface: "informe", card: "",
                           title: named, state: "partial", file: "documents/x.md" });
  const lines = w.lines();
  const refs = lines.filter((l) => l.kind === "ref");
  assert.equal(refs.length, 1, `[${lang}] one errand, one box`);
  assert.deepEqual(lines.map((l) => l.role), ["you", "box", "agent"], `[${lang}] the thread is his line, the box, ours`);
  assert.equal(lines[1].id, "ref_t-9", `[${lang}] the box stays where it was born in the thread`);
  assert.equal(refs[0].owner, "legacy:ref", `[${lang}] the box is the old path's ref writer's`);
  assert.equal(refs[0].text, named, `[${lang}] it wears the composed name`);
  assert.equal(refs[0].data.text, named);
  assert.equal(refs[0].data.state, "partial", `[${lang}] a half-done errand keeps its box, marked as such`);
  assert.equal(refs[0].data.card, "documento", `[${lang}] a later event without a card keeps the known one`);
  assert.equal(refs[0].data.file, "documents/x.md");
  assert.equal(refs[0].data.ref, "t-9", "the box reopens its own row");
  assert.equal(typeof refs[0].text, "string", "a restored history keeps only lines with a string text");
  assert.ok(keepable(lines).some((l) => l.id === "ref_t-9"), `[${lang}] the box is kept across a reload (final)`);
  assert.deepEqual(w.rejected, [], `[${lang}] every update of the box was accepted in place`);

  w.legacy.upsertChatRef({ kind: "artifact", label: "skipped", ref: "t-10", surface: "voz", reason: "no_card" });
  w.legacy.upsertChatRef({ kind: "artifact", label: "opened", ref: "", surface: "lista" });
  assert.equal(w.lines().filter((l) => l.kind === "ref").length, 1, `[${lang}] skipped or unnamed events draw nothing`);
  assert.equal(w.lines().length, 3, `[${lang}] …and nothing else either`);
}

// Both shells draw the box through the ONE view (components/ChatRef.js) — the wall's `ref` renderer — and it reopens
// through the one door.
const desk = readFileSync(path.join(root, "frontend/app/components/ChatWall.js"), "utf8");
const phone = readFileSync(path.join(root, "frontend/mobile/app/shell/ChatSheet.js"), "utf8");
const view = readFileSync(path.join(root, "frontend/app/components/ChatRef.js"), "utf8");
assert.match(desk, /renderers: \{[^}]*\bref: \(data\) => chatRefView\(data\)/, "the desktop wall draws the box");
assert.match(phone, /renderers: \{[^}]*\bref: \(data\) => chatRefView\(data, "zm-msg"\)/, "the phone draws the same box");
assert.match(view, /api\.taskReopen\(m\.ref\)/, "the box reopens through the existing door");
assert.match(view, /hb:open-card/, "…and the card opens like every other click");
for (const lang of ["en", "es"]) {
  const ui = JSON.parse(readFileSync(path.join(root, `i18n/genesis/${lang}/ui.json`), "utf8"));
  for (const k of ["open", "untitled", "started", "done", "partial", "cancelled", "gone"]) {
    assert.ok(ui["chat.ref." + k], `[${lang}] chat.ref.${k} is translated`);
  }
}
console.log("ok — an errand reference is one box that updates");

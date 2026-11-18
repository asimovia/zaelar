// yes-no.js — the face nods when the agent answers YES and shakes its head when it answers NO (V2-928, the operator
// 2026-11-18: «it could move the face while it says it, but only when we ask a question that needs that answer»).
// The signal is the agent's own reply, as it is SPOKEN (the audio-synced caption segments, store.captionSeg): a reply
// that OPENS with a bare yes or no — the word, then a pause (comma, stop, end) — is an answer to a yes/no question;
// «no te preocupes», «sí quieres…» are not (no pause after the word). The words are language data, one line per
// language in the i18n bundles (`presence.says_yes` / `presence.says_no`, «|»-separated), never a table in code.
// Pure: `polarity(text, yes, no)` → "yes" | "no" | null.

const norm = (s) => String(s || "").trim().toLowerCase().replace(/^[¡¿"«(\s]+/, "");
const words = (line) => String(line || "").split("|").map((w) => w.trim().toLowerCase()).filter(Boolean);

/** Does `text` open with one of the yes / no phrases followed by a pause? */
export function polarity(text, yesLine, noLine) {
  const t = norm(text);
  const opens = (w) => t.startsWith(w) && /^[\s]*([,.;:!?…—-]|$)/.test(t.slice(w.length));
  for (const w of words(yesLine)) if (opens(w)) return "yes";
  for (const w of words(noLine)) if (opens(w)) return "no";
  return null;
}

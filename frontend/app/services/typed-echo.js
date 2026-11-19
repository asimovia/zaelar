// typed-echo.js — the engine's echo of a typed line is painted only when this wall does not already show it
// (INI-042 #36). The tab that typed a line paints its bubble at once (`submitChat`); the engine then announces the
// line to every screen (`text-injected chat`, stamped with the `dev` that typed it). The echo used to be compared
// with the LAST line only: with the loop held for seconds, he typed the next line before the echo of the first came
// back, and the first was painted again below the second — «what I wrote comes out repeated underneath».
// Identity first: an echo from ANOTHER screen is always painted. An echo of this screen's own line (or of the
// holder's data channel, which names no screen) is that line's — it paints only when the wall has no copy of it
// left to answer for (a reload that lost the bubble). Pure: the wall's lines and this tab's id are handed in.

const norm = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9:_-]/g, "").slice(0, 40);   // voice/screens.clean

export function createTypedEcho() {
  const claimed = new Map();      // text → how many of this wall's lines an echo already answered for
  return function paints(text, dev, me, lines) {
    if (dev && norm(dev) !== norm(me)) return true;
    const mine = (lines || []).filter((m) => m && m.role === "you" && m.text === text).length;
    const n = claimed.get(text) || 0;
    claimed.set(text, n + 1);    // a painted echo makes a line of its own: the next echo answers for it too
    return n >= mine;
  };
}

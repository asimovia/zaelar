// orb-colour.js — WHEN THE ORB IS ORANGE (V2-792 §9, operator 2026-10-25).
//
// The orb is grey, and it turns orange only while the AGENT IS TALKING on the screen that holds the voice. A screen
// where the voice lives elsewhere is never orange, even though it receives the same «speaking» events: the agent is
// not talking THERE. This replaces the 2026-09-10 rule (orange = «I am listening to you», V2-648) by the operator's
// own decision; whether the mic is hearing him is now the mic icon's job (lilac, with its level meter).
//
// Dependency-free on purpose: the test drives THIS function with the states `store.screenState()` returns.
export function orbWarm(screenState) {
  return screenState === "speaking";
}

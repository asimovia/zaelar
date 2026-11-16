// card-front.js — ONE door for «a card just came to the front» (2026-11-16, App Review recording: «open activity»
// opened the widget BEHIND the phone's full-screen chat, and the agent said «it's open» over a screen that showed none
// of it). Both hosts (app/widgets/desktop.js, mobile/app/shell/Deck.js) knock here when a show is NOT a background or
// restore one; every surface that can cover a card listens and gives way (the phone's pages, the desktop's floating
// chat when it covers the screen). A host that brings a card forward without knocking is the bug this file exists for.
export const CARD_FRONT = "hb:card-front";

export function frontDoor(id, by = "code") {
  try { document.dispatchEvent(new CustomEvent(CARD_FRONT, { detail: { id: String(id || ""), by: String(by || "code") } })); }
  catch (_) { /* no document (a unit test without a DOM): nothing on screen to give way */ }
}

export function onCardFront(fn) {
  try { document.addEventListener(CARD_FRONT, (e) => fn((e && e.detail) || {})); } catch (_) {}
}

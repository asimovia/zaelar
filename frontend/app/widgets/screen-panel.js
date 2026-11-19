// ============================================================================
// screen-panel.js — which NATIVE surface is open over the canvas, for the screen document (V2-907 T9, §3.1 `panel`).
//
// A surface is not a card: it lives in the store's signals (`core/system-surfaces.js` says which signal opens each).
// This module is ONE declared table of the desktop's named surfaces → the signal that says it is open, in the order
// they stack (the full-screen settings over a modal over a side panel over the chat wall), and a reader that names
// the topmost one, or "" when the canvas is bare. The chat wall names its tab: `apps` and `conectores` are surfaces
// of their own, any other tab is `chat` (`chat:<tab>` when it is not the conversation). The phone passes its own
// table (its pages, `mobile/app/shell/pages.js`). `watchPanel` reports every change of any signal in the table.
// ============================================================================
import * as store from "../core/store.js?v=2";
import { createEffect, untrack } from "../core/reactive.js?v=2";

const _chat = (open) => () => {
  if (!open()) return "";
  const tab = String(store.chatTab() || "chat");
  return tab === "apps" || tab === "conectores" ? tab : tab === "chat" ? "chat" : `chat:${tab}`;
};
const _is = (id, open) => () => (open() ? id : "");

//: The desktop's named surfaces, topmost first: [surface id, reader → the id when open, else ""].
export const DESKTOP_PANELS = [
  ["config", _is("config", store.configOpen)],
  ["wizard", _is("wizard", store.wizardOpen)],
  ["vault", _is("vault", store.vaultOpen)],
  ["memory-map", _is("memory-map", store.memOpen)],
  ["debug", _is("debug", store.debugOpen)],
  ["status", _is("status", store.statusOpen)],
  ["feedback", _is("feedback", store.feedbackOpen)],
  ["chat", _chat(store.chatOpen)],
];

//: How a close of everything shuts each of them (INI-042 #47: Settings opened by voice outlived «close all»). The wall
//: stays — it is the conversation — but goes back to it from any other tab.
const DESKTOP_CLOSE = {
  config: () => store.setConfigOpen(false), wizard: () => store.setWizardOpen(false), vault: () => store.closeVault(),
  "memory-map": () => store.setMemOpen(false), debug: () => store.setDebugOpen(false),
  status: () => store.setStatusOpen(false), feedback: () => store.setFeedbackOpen(false),
  chat: () => { if (store.chatOpen() && String(store.chatTab() || "chat") !== "chat") store.setChatTab("chat"); },
};

/** Close every native surface over the desktop but the conversation (a close-all order). */
export function closePanels() {
  for (const [id, read] of DESKTOP_PANELS) { try { if (read()) DESKTOP_CLOSE[id](); } catch (_) {} }
}

/** The phone's pages as a table: `pages` = [[get, set, id]…] (`pages.js`), the chat page naming its tab. */
export const pagePanels = (pages) => pages.map(([get, , id]) => [id, id === "chat" ? _chat(get) : _is(id, get)]);

/** The topmost open surface of `table`, or "". */
export function panelOf(table = DESKTOP_PANELS) {
  for (const [, read] of table) { const v = read(); if (v) return v; }
  return "";
}

/** Call `onChange` whenever the open surface of `table` changes. */
export function watchPanel(table, onChange) {
  let last = null;
  try {
    createEffect(() => {
      const now = table.map(([, read]) => read()).find(Boolean) || "";
      if (last !== null && now !== last) untrack(onChange);
      last = now;
    });
  } catch (_) {}
}

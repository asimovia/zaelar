// PresenceSheet.js — Settings ▸ Presence on the PHONE (V2-928 T11): the agent's face, chosen and tuned. The SAME section
// the desktop mounts in Settings (app/presence/PresenceSection.js) in a full-screen page; presence.css lays it out for
// the hand — categories, a strip of faces, the face, and «Customise» as a step. Opened from a row of Settings, from the
// ☰ page's face row, and by voice («abre los ajustes de presencia»: presence/state.js names this page the door).
// The live preview exists only while the page is open: closing it removes the section, which stops its face.
import { h } from "../../../app/core/dom.js?v=2";
import { createSignal, createEffect, untrack } from "../../../app/core/reactive.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import { mountPresence } from "../../../app/presence/PresenceSection.js?v=1";
import { setPresencePage } from "../../../app/presence/state.js?v=1";
import { Page } from "./Page.js?v=1";

// The page's own open signal, as ConnectorsSheet's: only this shell has the page.
export const [presenceOpen, setPresenceOpen] = createSignal(false);

export function PresenceSheet() {
  setPresencePage(() => setPresenceOpen(true));
  const host = h("div", { class: "zm-pz" });
  createEffect(() => {
    if (!presenceOpen()) { host.replaceChildren(); return; }
    const inner = h("div");
    host.replaceChildren(inner);
    untrack(() => mountPresence(inner));     // the section reads the choice; picking a face must not re-mount it
  });
  const close = () => setPresenceOpen(false);
  return Page({ id: "presence", open: presenceOpen, title: () => t("config.tab.presence"), close,
    back: () => { close(); store.setMobileSettingsOpen(true); } }, host);
}

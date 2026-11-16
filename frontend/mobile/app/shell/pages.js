// pages.js — ONE PAGE AT A TIME (V2-876 D-A/D-D). Every shell surface is a full-screen page (Page.js) and pages never
// stack: opening one closes the others. Settings, feedback and connectors are opened FROM the ☰ page, so back returns there.
import { createEffect, untrack } from "../../../app/core/reactive.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import { appsOpen, setAppsOpen } from "./AppsPane.js?v=2";
import { onCardFront } from "../../../app/widgets/card-front.js?v=1";
import { connectorsOpen, setConnectorsOpen } from "./ConnectorsSheet.js?v=1";

// Each page: [is open, set open, the surface it is (`mobile-surfaces.js` id — the screen document's `panel`)].
export const PAGES = [[store.chatOpen, store.setChatOpen, "chat"], [store.mobileMenuOpen, store.setMobileMenuOpen, "menu"],
  [store.mobileSettingsOpen, store.setMobileSettingsOpen, "settings"], [store.mobileFeedbackOpen, store.setMobileFeedbackOpen, "feedback"],
  [connectorsOpen, setConnectorsOpen, "connectors"],
  [appsOpen, setAppsOpen, "apps"]];

export function onePageAtATime() {
  for (const [get] of PAGES) createEffect(() => { if (get()) untrack(() => PAGES.forEach(([g, set]) => { if (g !== get && g()) set(false); })); });
  // A card brought to the front (by voice, by hand, by a link) is the screen now: every page over the deck gives way.
  // The chat is not lost — it is one tap away on the dock, with the agent's «it's open» line in it.
  onCardFront(() => PAGES.forEach(([g, set]) => { if (g()) set(false); }));
}

/** The platform's back: closes the open page (one of the ☰'s goes back to it). False when no page was open. */
export function backFromPage() {
  for (const [get, set] of PAGES) if (get()) {
    set(false);
    if (get === store.mobileSettingsOpen || get === store.mobileFeedbackOpen || get === connectorsOpen) store.setMobileMenuOpen(true);
    return true;
  }
  return false;
}

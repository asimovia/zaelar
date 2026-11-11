// pages.js — ONE PAGE AT A TIME (V2-876 D-A/D-D). Every shell surface is a full-screen page (Page.js) and pages never
// stack: opening one closes the others. Settings and feedback are opened FROM the ☰ page, so back returns there.
import { createEffect, untrack } from "../../../app/core/reactive.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import { appsOpen, setAppsOpen } from "./AppsPane.js?v=2";

export const PAGES = [[store.chatOpen, store.setChatOpen], [store.mobileMenuOpen, store.setMobileMenuOpen],
  [store.mobileSettingsOpen, store.setMobileSettingsOpen], [store.mobileFeedbackOpen, store.setMobileFeedbackOpen],
  [appsOpen, setAppsOpen]];

export function onePageAtATime() {
  for (const [get] of PAGES) createEffect(() => { if (get()) untrack(() => PAGES.forEach(([g, set]) => { if (g !== get && g()) set(false); })); });
}

/** The platform's back: closes the open page (one of the ☰'s goes back to it). False when no page was open. */
export function backFromPage() {
  for (const [get, set] of PAGES) if (get()) {
    set(false);
    if (get === store.mobileSettingsOpen || get === store.mobileFeedbackOpen) store.setMobileMenuOpen(true);
    return true;
  }
  return false;
}

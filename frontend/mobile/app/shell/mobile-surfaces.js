// mobile-surfaces.js — THE CANONICAL LIST of the phone shell's native surfaces (same role as app/core/system-surfaces.js):
// main.js mounts from here, so there is never a second list. A different list from the desktop's, by design: a phone is
// for USING the agent, so the camera unit, the activity honeycomb, the config and debug panels stay on the desk; the
// eye collapses to a six-target dock (DockBar.js: ≡ · chat · apps | ORB | mic · speaker), N cards to one deck of
// full-screen cards (Deck.js), and every other surface is a full-screen PAGE (Page.js, V2-876 D-A). Modal, full-bleed
// desktop surfaces are REUSED verbatim (BootOverlay, LanguageOnboarding, Alert…): forking a first-run gate is how two
// shells disagree about whether onboarding happened. Fields: id · comp · target ("deck" | "body") · phase ("scaffold"
// = load-bearing order | "overlay") · label · shared (the desktop's component, imported as-is).

import { Alert } from "../../../app/components/Alert.js?v=2";
import { BootOverlay } from "../../../app/components/BootOverlay.js?v=2";
import { LanguageOnboarding } from "../../../app/components/LanguageOnboarding.js?v=1";
import { UpdateSurface } from "../../../app/update/UpdateSurface.js?v=1";
import { EnergyNotice } from "../../../app/components/EnergyNotice.js?v=1";
import { DormantVeil } from "../../../app/components/DormantVeil.js?v=1";
import { ElsewhereChips } from "../../../app/components/ElsewhereChips.js?v=1";
import { ChatSheet } from "./ChatSheet.js?v=1";
import { DockBar } from "./DockBar.js?v=4";
import { MenuSheet } from "./MenuSheet.js?v=2";
import { SettingsSheet } from "./SettingsSheet.js?v=2";
import { InstallBanner } from "./InstallBanner.js?v=1";
import { FeedbackSheet } from "./FeedbackSheet.js?v=2";
import { EnergyLine } from "./EnergyLine.js?v=1";
import { AiConsentSheet } from "./AiConsentSheet.js?v=1";
import { AppsPane } from "./AppsPane.js?v=2";

export const MOBILE_SURFACES = [
  // ── the bar that owns every control ──
  { id: "dock",     comp: DockBar,     target: "body", phase: "scaffold", label: "Bottom dock (≡ · chat · apps · ORB · mic · speaker)", shared: false },
  // NO CAPTIONS BAND (V2-573, operator: «deactivate subtitles. dont want icon for that»). It was the second
  // scaffold surface and it is GONE from the phone, together with its 📝 button in the dock. Deleting the LINE is
  // the whole removal — which is the point of this file existing: a surface nobody mounts cannot half-exist.
  // The desktop's captions are untouched.
  // ── PAGES: full screen from the status bar to the dock, one open at a time (main.js), never stacked ──
  { id: "chat",     comp: ChatSheet,      target: "body", phase: "overlay", label: "Chat page", shared: false },
  { id: "menu",     comp: MenuSheet,      target: "body", phase: "overlay", label: "☰ page: processes · account · energy · settings · feedback · voice · desktop", shared: false },
  { id: "apps",     comp: AppsPane,       target: "body", phase: "overlay", label: "Apps page: every app, its icon, name and one line", shared: false },
  { id: "settings", comp: SettingsSheet,  target: "body", phase: "overlay", label: "Settings page (language · theme · speaker · wake word · notifications · permissions)", shared: false },
  { id: "feedback", comp: FeedbackSheet,  target: "body", phase: "overlay", label: "Feedback page (a row of the ☰ page)", shared: false },
  // ── V2-870 — inside the native app: the yes to the AI services, asked before the first turn ──
  { id: "ai-consent", comp: AiConsentSheet, target: "body", phase: "overlay", label: "AI services consent (native app only)", shared: false },
  // ── the Energy left, a thin line along the top edge (cloud only) ──
  { id: "energy-line", comp: EnergyLine,  target: "body", phase: "overlay", label: "Energy left, along the top edge", shared: false },
  // ── V2-796 — «install the app» / «turn on notifications»: the phone has to be REACHABLE for a notice ──
  { id: "install",    comp: InstallBanner,   target: "body", phase: "overlay", label: "Install the PWA, then allow notifications", shared: false },
  // ── SHARED WITH THE DESKTOP, imported verbatim (their CSS lives in app/core/shared-surfaces.css) ──
  { id: "alert",           comp: Alert,             target: "body", phase: "overlay", label: "Hard notice banner", shared: true },
  { id: "boot",            comp: BootOverlay,       target: "body", phase: "overlay", label: "Startup veil", shared: true },
  { id: "lang-onboarding", comp: LanguageOnboarding, target: "body", phase: "overlay", label: "First-run language onboarding", shared: true },
  // V2-553 — the update bar. An installed PWA is the surface most likely to be running code from days ago,
  // so it is the one that most needs to be told. `UpdateSurface` is bar-only now (V2-666 retired the
  // always-on version badge from BOTH shells' canvas); where the build number belongs on a phone — this
  // shell has no Settings screen yet — is still open.
  { id: "update",          comp: UpdateSurface, target: "body", phase: "overlay", label: "«New version — reload» bar", shared: true },
  // V2-785 — out of Energy, on screen, with the top-up button (the voice alone used to say it).
  { id: "energy-notice",   comp: EnergyNotice,  target: "body", phase: "overlay", label: "Out of Energy + top up", shared: true },
  // 2026-11-10 — the engine asleep, or the voice on another device: one black veil (it replaced the phone's own
  // «your voice is on the computer» notice), with the gesture that fixes each.
  { id: "dormant",         comp: DormantVeil,   target: "body", phase: "overlay", label: "Asleep / voice on another device — full-screen veil", shared: true },
  // V2-792 — what the agent did on the OTHER screen, one tap away (a report opened on the computer, a video there).
  { id: "elsewhere",       comp: ElsewhereChips, target: "body", phase: "overlay", label: "Opened on another screen — open here", shared: true },
];

const _IDS = new Set(MOBILE_SURFACES.map((s) => s.id));
export function isMobileSurface(id) { return _IDS.has(String(id || "")); }

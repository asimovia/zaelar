// MenuSheet.js — the ☰ PAGE (V2-876 D-D: full screen, scrollable, one header): the phone's counterpart of the desktop's
// TOP BAR — the person and the setup, never the agent's work. UNIFIED MENU (2026-11-16, operator: «el menú principal
// lleva arriba el perfil, la configuración, las voces y los conectores; el chat lleva lo del agente»). ORDER
// (2026-11-17, operator): Energy first, then My account (its own page, AccountSheet.js: the account area, profile,
// plans, invoices and deleting the account — what is done once goes one tap deeper, not on a page opened many times a
// day) · Physical display (the agent's face on or off, V2-928) · Settings · Voice · Connectors · Devices (its own page,
// DevicesSheet.js: this phone and his computer, read only) · then what has nothing to do with the session, at the foot:
// Feedback · Log out · the build number, last and readable (operator, 2026-11-17). Every row carries an
// outline icon from app/lib/icons.js. The «desktop version» row moved off this page: the escape hatch stays in
// Settings (SettingsSheet.js) and index.html's `?desktop=1`. The RUNNING PROCESSES live in the chat's Processes tab (ChatSheet.js); the widgets launcher is the
// dock's (AppsPane.js).
import { h, raw } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import * as session from "../../../app/services/session.js?v=3";
import * as api from "../../../app/services/api.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import { logoutLink } from "../../../app/core/account-link.js?v=2";
import { inNativeApp } from "../../../app/core/native.js?v=1";
import { ZAP_ICON, USER_ICON, GEAR_ICON, MIC_ICON, PLUG_ICON, MESSAGE_SQUARE_ICON, DESKTOP_ICON, LOG_OUT_ICON, FACE_ICON } from "../../../app/lib/icons.js?v=2";
import * as daemon from "../../../app/services/daemon.js?v=3";
import { Page } from "./Page.js?v=1";
import { setConnectorsOpen } from "./ConnectorsSheet.js?v=1";
import { setAccountOpen, openAccount } from "./AccountSheet.js?v=1";
import { setDevicesOpen, devicesSummaryKey } from "./DevicesSheet.js?v=1";
import { Row } from "./menu-row.js?v=1";
import { VersionLabel } from "../../../app/update/VersionLabel.js?v=1";
import { presenceOn, togglePresence } from "../../../app/presence/state.js?v=1";
import { currentEntry } from "../../../app/presence/PresenceLayer.js?v=1";
import { faceName } from "../../../app/presence/catalog-api.js?v=1";

// The daemon poll runs here too: the desktop starts it from the setup surface, which this shell does not
// mount. Without this the row would always read "not connected", which is a wrong answer rather than a
// missing one — the worst of the three states a status row can be in.
daemon.start();

/** Sign out of this device: a same-origin POST the deployment's front door answers (it revokes the session and
 *  clears its cookie), then the shell reloads and the front door asks to sign in again. Same origin on purpose: a
 *  write to another origin is refused by a front door that guards against cross-origin writes. The redirect it
 *  answers with is not followed here (`manual`): the reload below is the one navigation. */
async function logOut() {
  const u = logoutLink(store.accountUrl());
  api.uiEvent("mobile:logout", {});
  if (u) await fetch(u, { method: "POST", credentials: "same-origin", redirect: "manual" }).catch(() => {});
  location.replace(location.pathname || "/m");
}

export function MenuSheet() {
  const close = () => store.setMobileMenuOpen(false);
  // A row that opens another page: that page replaces this one, and its ‹ comes back (Page.js).
  const go = (set) => () => { close(); set(true); };

  return Page({ id: "menu", open: store.mobileMenuOpen, title: "zaelar", close },
    h("div", { class: "zm-rows" },
      // ── ENERGY, first: the balance shows inline instead of hiding it one tap deep, and the row IS the top-up (the
      //    account page's #buy, like the desktop battery). `known:false` (the machine still booting) renders "—",
      //    never a fabricated 0 — a wrong balance is worse than no balance.
      h("button", { class: () => "zm-energy" + (store.energy().cloud ? "" : " hide"), onClick: () => openAccount(inNativeApp() ? "" : "buy") },   // V2-870: no #buy in the app
        h("span", { class: "zm-row-i", "aria-hidden": "true" }, raw(ZAP_ICON)),
        h("span", null, () => t("energy.label")),
        h("b", null, () => {
          const e = store.energy();
          return e.known && e.balance != null ? String(Math.round(e.balance)) : "—";
        }),
        // The TRACK is the cycle's Energy and the fill is what is left. The fill used to be the flex item itself,
        // and `flex: 1 1 auto` stretched it over its own width: 61 of 400 drew a full bar.
        h("span", { class: "zm-energy-track" }, h("i", {
          style: {
            width: () => {
              const e = store.energy();
              if (!e.known || !e.capacity) return "0%";
              return Math.max(0, Math.min(100, (e.balance / e.capacity) * 100)) + "%";
            },
          },
        })),
      ),
      // ── MY ACCOUNT — cloud only. On self-host there is no account behind it, so the row is not rendered at all
      //    rather than rendered and dead: a control that does nothing teaches the operator to distrust the others.
      () => store.cloudProfile()
        ? Row(USER_ICON, () => t("mobile.account"), () => t("mobile.account_sub"), go(setAccountOpen))
        : null,
      // ── PHYSICAL DISPLAY (V2-928 T11): the agent's face behind the home, on or off — the desktop's ☺, by the account
      //    rows. The subtitle names the face it wears; choosing another is Settings ▸ Presence.
      h("button", { class: () => "zm-row zm-toggle" + (presenceOn() ? " on" : ""), "aria-pressed": () => String(presenceOn()),
        onClick: () => togglePresence("menu") },
        h("span", { class: "zm-row-i", "aria-hidden": "true" }, raw(FACE_ICON)),
        h("span", { class: "zm-row-t" }, h("b", null, () => t("presence.physical")), h("small", null, () => faceName(currentEntry()))),
        h("span", { class: "zm-sw", "aria-hidden": "true" })),
      Row(GEAR_ICON, () => t("mobile.settings"), () => t("mobile.settings_sub"), go(store.setMobileSettingsOpen)),
      Row(MIC_ICON, () => t("mobile.voice"), () => (store.voices()[store.voiceIdx()] || {}).label || "",
        () => { session.cycleVoice(); api.uiEvent("mobile:voice_cycle", {}); }),
      // ── CONNECTORS (2026-11-16): the desktop chat wall's list, one tap deep.
      Row(PLUG_ICON, () => t("chat.tabConnectors"), () => t("mobile.connectors_sub"), go(setConnectorsOpen)),

      // ── DEVICES: one line of title, one of subtitle — the computer's state, since the phone is always there. The
      //    rows (this phone, his computer and its daemon) and the explanation live on the page it opens.
      Row(DESKTOP_ICON, () => t("mobile.devices"),
        () => t(devicesSummaryKey(daemon.isOffered(), daemon.isConnected())), go(setDevicesOpen)),

      // ── AT THE FOOT, what has nothing to do with the session: Feedback, Log out, then the build number.
      Row(MESSAGE_SQUARE_ICON, () => t("feedback.title"), () => t("mobile.feedback_sub"), go(store.setMobileFeedbackOpen)),

      // ── LOG OUT, last — cloud only (self-host has no sign-in to leave).
      () => store.cloudProfile()
        ? Row(LOG_OUT_ICON, () => t("mobile.logout"), null, logOut)
        : null,
    ),
    // The build number, the very last line — the same live element as the desktop's badge, at a size he can read.
    VersionLabel({ cls: "zm-ver" }),
  );
}

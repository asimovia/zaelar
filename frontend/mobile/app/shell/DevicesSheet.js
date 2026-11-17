// DevicesSheet.js — ☰ → Devices, a full-screen page (operator, 2026-11-17): every device of his setup that this shell
// can read, one row each, READ ONLY — a phone reports devices, it does not set them up. Today that is this phone (the
// native app or the browser it runs in) and his computer (the local daemon, V2-575: installed, connected, the browser
// its sign-in window uses and the link to the agent). The explanation of what a phone cannot do lives here, under
// the rows, never in the ☰ page itself, which keeps one line of title and one of subtitle per row.
import { h, raw } from "../../../app/core/dom.js?v=2";
import { createSignal } from "../../../app/core/reactive.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import { inNativeApp } from "../../../app/core/native.js?v=1";
import { DESKTOP_ICON } from "../../../app/lib/icons.js?v=2";
import * as daemon from "../../../app/services/daemon.js?v=3";
import { Page } from "./Page.js?v=1";

// The page's own open signal, as ConnectorsSheet's: only this shell has the page.
export const [devicesOpen, setDevicesOpen] = createSignal(false);

// A phone outline (lucide «smartphone»), local so the shared icon module does not change under a cached import.
const PHONE_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><path d="M12 18h.01"/></svg>`;

/** Which kind of phone surface this is: the native app (its platform) or a browser. Pure. */
export function thisPhoneKind(native, platform) {
  if (!native) return "browser";
  return platform === "android" ? "android" : "ios";
}

/** The one-line subtitle the ☰ page's Devices row shows: the computer's state, since the phone is always there. */
export function devicesSummaryKey(offered, connected) {
  if (!offered) return "mobile.devices_sub_phone";
  return connected ? "mobile.devices_sub_connected" : "mobile.devices_sub_not_connected";
}

function platform() {
  return document.documentElement.getAttribute("data-platform") || "";
}

export function DevicesSheet() {
  const open = devicesOpen, close = () => setDevicesOpen(false);
  return Page({ id: "devices", open, title: () => t("mobile.devices"), close,
    back: () => { close(); store.setMobileMenuOpen(true); } },
    h("div", { class: "zm-rows" },
      // ── THIS PHONE: always there — it is the device reading this page.
      h("div", { class: "zm-row zm-row-static zm-device-phone" },
        h("span", { class: "zm-row-i", "aria-hidden": "true" }, raw(PHONE_ICON)),
        h("span", { class: "zm-row-t" },
          h("b", null, () => t("mobile.devices_this_phone")),
          h("small", null, () => t("mobile.devices_phone_" + thisPhoneKind(inNativeApp(), platform()))),
        ),
      ),
      // ── 🖥 THE LOCAL DAEMON, READ ONLY (V2-575 P1). A phone does not install a desktop daemon, so this row has no
      //    chevron and no click: it REPORTS. It is here because "is my computer connected?" is a question somebody
      //    asks from wherever they are, and a shell that simply omitted the answer would read as "this device has no
      //    daemon" rather than "you cannot set it up from here".
      h("div", { class: () => "zm-row zm-row-static" + (daemon.isOffered() ? "" : " is-off") },
        h("span", { class: "zm-row-i", "aria-hidden": "true" }, raw(DESKTOP_ICON)),
        h("span", { class: "zm-row-t" },
          h("b", null, () => t("daemon.mobile.row")),
          h("small", null, () => (daemon.isConnected() ? t("mobile.devices_computer_connected") : t("mobile.devices_computer_not_connected"))),
          // The browser the sign-in window uses and the link to the cloud agent, one line each — the same words
          // the desktop's settings screen uses (`daemon.browserLine` / `daemon.linkLine`), read, never set here.
          h("small", { class: "zm-daemon-browser" }, () => {
            const b = daemon.browserLine();
            return t("daemon.mobile.browser_line", { state: t(b.key, b.vars || undefined) });
          }),
          h("small", { class: "zm-daemon-link" }, () => {
            const l = daemon.linkLine();
            return t("daemon.mobile.link_line", { state: t(l.key, l.vars || undefined) });
          }),
        ),
      ),
    ),
    // ── THE EXPLANATION, under the rows: what works FROM HERE, said plainly (P1) — the folders he granted can be
    //    read, a sign-in window cannot open on a phone (it opens on the computer), and the daemon is installed there.
    h("p", { class: "zm-devices-note" }, () => (daemon.isConnected() ? t("daemon.mobile.connected") : t("daemon.mobile.hint"))),
  );
}

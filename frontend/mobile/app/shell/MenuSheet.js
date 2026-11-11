// MenuSheet.js — the ☰ PAGE (V2-876 D-D: full screen, scrollable, one header): the phone's home for what the desktop
// keeps in its top bar. Running processes · Account (cloud) · Energy (the balance, the row is the top-up) · Settings
// (its own page; ‹ comes back here) · Feedback (its own page — it left the dock, D-C) · Voice · the daemon's state
// (read only) · the desktop version, the ESCAPE HATCH: a shell you cannot leave is a trap. The apps launcher left
// this page for the dock's Apps button (AppsPane.js).
import { h, raw } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import * as session from "../../../app/services/session.js?v=3";
import * as api from "../../../app/services/api.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import { accountLink } from "../../../app/core/account-link.js?v=1";
import { inNativeApp } from "../../../app/core/native.js?v=1";
import * as daemon from "../../../app/services/daemon.js?v=3";
import { ProcessEntry } from "../../../app/components/ProcessEntry.js?v=1";
import { Page } from "./Page.js?v=1";

// The daemon poll runs here too: the desktop starts it from the setup surface, which this shell does not
// mount. Without this the row would always read "not connected", which is a wrong answer rather than a
// missing one — the worst of the three states a status row can be in.
daemon.start();

const CHEV = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 6l6 6-6 6"/></svg>`;

// One menu row: bold label, quiet subtitle, chevron. `label`/`sub` may be a string OR a function — a function is a
// reactive binding (core/dom.js), which is how a row's subtitle can track a signal (the current voice, say) without
// this component knowing which signal it was.
function Row(label, sub, onClick) {
  return h("button", { class: "zm-row", onClick },
    h("span", { class: "zm-row-t" },
      h("b", null, label),
      sub ? h("small", null, sub) : null,
    ),
    raw(CHEV),
  );
}

export function MenuSheet() {
  const openAccount = (section) => {
    // V2-785: the engine's account url, never a relative "/account" — in a hosted deployment that is this agent's
    // own origin, where no account page exists.
    const u = accountLink(store.accountUrl(), section);
    if (u) window.open(u, "_blank", "noopener");
  };
  const close = () => store.setMobileMenuOpen(false);
  // A row that opens another page: that page replaces this one, and its ‹ comes back (Page.js).
  const go = (set) => () => { close(); set(true); };

  return Page({ id: "menu", open: store.mobileMenuOpen, title: "zaelar", close },
    h("div", { class: "zm-rows" },
      // ── RUNNING PROCESSES (V2-822). The phone has no processes tab, and since the cards stopped telling their
      //    errand's progress (a card shows only its deliverable), this is where a running process is told: the
      //    same entry the desktop's processes tab draws, from the same record. Absent when nothing runs.
      h("div", { class: "zm-procs" }, () => {
        const live = store.liveProcesses();      // the same reading as the dock's count (V2-822)
        if (!live.length) return null;
        return [h("div", { class: "zm-procs-t" }, () => t("chat.procMobileTitle")),
                ...live.map(x => h("div", { class: "zm-proc" },
                  h("b", null, (x.title || x.note || "").trim() || t("chat.working")),
                  ProcessEntry(x.id)))];
      }),

      // ── ACCOUNT — cloud only. On self-host there is no account behind this, so the row is not rendered at all
      //    rather than rendered and dead: a control that does nothing teaches the operator to distrust the others.
      () => store.cloudProfile()
        ? Row(() => t("mobile.account"), () => t("mobile.account_sub"), () => openAccount())
        : null,
      // V2-870 — inside the native app the account can be deleted from here (App Review 5.1.1(v)): the account page
      // at its #delete section, in the system browser (`openAccount` opens a new window, which leaves the app).
      () => store.cloudProfile() && inNativeApp()
        ? Row(() => t("mobile.delete_account"), () => t("mobile.delete_account_sub"), () => openAccount("delete"))
        : null,

      // ── ENERGY: the balance shows inline instead of hiding it one tap deep, and the row IS the top-up (the
      //    account page's #buy, like the desktop battery). `known:false` (the machine still booting) renders "—",
      //    never a fabricated 0 — a wrong balance is worse than no balance.
      h("button", { class: () => "zm-energy" + (store.energy().cloud ? "" : " hide"), onClick: () => openAccount(inNativeApp() ? "" : "buy") },   // V2-870: no #buy in the app
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

      Row(() => t("mobile.settings"), () => t("mobile.settings_sub"), go(store.setMobileSettingsOpen)),
      Row(() => t("feedback.title"), () => t("mobile.feedback_sub"), go(store.setMobileFeedbackOpen)),

      Row(() => t("mobile.voice"), () => (store.voices()[store.voiceIdx()] || {}).label || "",
        () => { session.cycleVoice(); api.uiEvent("mobile:voice_cycle", {}); }),

      // ── 🖥 THE LOCAL DAEMON, READ ONLY (V2-575 P1). A phone does not install a desktop daemon, so this row
      //    has no chevron and no click: it REPORTS. It is here because "is my computer connected?" is a
      //    question somebody asks from wherever they are, and a mobile shell that simply omitted the answer
      //    would read as "this device has no daemon" rather than "you cannot set it up from here".
      h("div", { class: () => "zm-row zm-row-static" + (daemon.isOffered() ? "" : " is-off") },
        h("span", { class: "zm-row-t" },
          h("b", null, () => t("daemon.mobile.row")),
          // What works FROM HERE, said plainly (P1): the folders he granted can be read, a sign-in window cannot
          // open on a phone — it opens on the computer, so the phone never promises one.
          h("small", null, () => (daemon.isConnected() ? t("daemon.mobile.connected") : t("daemon.mobile.hint"))),
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

      // ── THE ESCAPE HATCH. Persists the choice so index.html's picker stops redirecting this device.
      Row(() => t("mobile.desktop"), () => t("mobile.desktop_sub"),
        () => { try { localStorage.setItem("zaelar_shell", "desktop"); } catch (_) {} location.replace("/?desktop=1"); }),
    ),
  );
}

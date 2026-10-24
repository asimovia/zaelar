// ============================================================================
// MenuSheet.js — the ☰ sheet: the mobile home for everything the desktop keeps in its top bar and its floating
// launcher.  Operator's brief: «a menu button also to access feedback, the account, the profile, some
// other things… a small configuration device and from there manage all that too».
//
// WHAT IT HOLDS, and where each row's behaviour actually lives:
//   · Energy      — the balance, read from store.energy() (the SSE keeps it live; no polling here)
//   · Account     — cloud only (store.cloudProfile), because on self-host there is no account to open
//   · Feedback    — FeedbackForm.js, at parity with the desktop panel and on its same services
//   · Settings    — opens SettingsSheet (the «small settings device»)
//   · Voice       — cycles the TTS voice (session.cycleVoice), the same seam as tapping the orb
//   · Shell       — "open the desktop version": sets zaelar_shell=desktop and leaves. THE ESCAPE HATCH, and it is
//                   not optional — a shell you cannot leave is a trap, and the shell picker in index.html would
//                   otherwise bounce a tablet user back here on every load.
//
// The feedback form is INLINE rather than a second sheet on purpose: the desktop learned (V2-100) that the whole
// value of this feature is that it takes one gesture. Two sheets deep and nobody reports anything.
// ============================================================================

import { h, raw } from "../../../app/core/dom.js?v=2";
import { createEffect } from "../../../app/core/reactive.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import * as session from "../../../app/services/session.js?v=3";
import * as api from "../../../app/services/api.js?v=2";
import { FeedbackForm } from "./FeedbackForm.js?v=1";
import { t } from "../../../app/core/i18n.js?v=1";
import { accountLink } from "../../../app/core/account-link.js?v=1";
import * as daemon from "../../../app/services/daemon.js?v=3";

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
  // The form's open state lives in the store: the dock's feedback button opens it too (2026-10-24).
  const fbOpen = store.mobileFeedbackOpen, setFbOpen = store.setMobileFeedbackOpen;
  const close = () => store.setMobileMenuOpen(false);

  return h("section", {
    class: () => "zm-sheet zm-menu" + (store.mobileMenuOpen() ? " open" : ""),
    "aria-hidden": () => (store.mobileMenuOpen() ? "false" : "true"),
  },
    h("header", { class: "zm-sheet-h" },
      h("div", { class: "zm-sheet-grab" }),
      h("h2", null, "zaelar"),
      h("button", { class: "zm-sheet-x", "aria-label": () => t("desktop.close"), onClick: close }, "×"),
    ),

    h("div", { class: "zm-rows" },
      // ── ENERGY: the balance is the one number a hosted user checks, so it is the first row and it shows the
      //    value inline instead of hiding it one tap deep. `known:false` (self-host, or the machine still booting)
      //    renders "—", never a fabricated 0 — a wrong balance is worse than no balance.
      h("div", { class: () => "zm-energy" + (store.energy().cloud ? "" : " hide") },
        h("span", null, () => t("energy.label")),
        h("b", null, () => {
          const e = store.energy();
          return e.known && e.balance != null ? String(Math.round(e.balance)) : "—";
        }),
        h("i", {
          style: {
            width: () => {
              const e = store.energy();
              if (!e.known || !e.capacity) return "0%";
              return Math.max(0, Math.min(100, (e.balance / e.capacity) * 100)) + "%";
            },
          },
        }),
      ),

      // ── ACCOUNT — cloud only. On self-host there is no account behind this, so the row is not rendered at all
      //    rather than rendered and dead: a control that does nothing teaches the operator to distrust the others.
      () => store.cloudProfile()
        ? Row(() => t("mobile.account"), () => t("mobile.account_sub"),
            // V2-785: the engine's account url, never a relative "/account" — in a hosted deployment that is
            // this agent's own origin, where no account page exists.
            () => { const u = accountLink(store.accountUrl()); if (u) window.open(u, "_blank", "noopener"); })
        : null,

      Row(() => t("mobile.voice"), () => (store.voices()[store.voiceIdx()] || {}).label || "",
        () => { session.cycleVoice(); api.uiEvent("mobile:voice_cycle", {}); }),

      Row(() => t("mobile.settings"), () => t("mobile.settings_sub"),
        () => { store.setMobileSettingsOpen(true); }),

      // ── 🖥 THE LOCAL DAEMON, READ ONLY (V2-575 P1). A phone does not install a desktop daemon, so this row
      //    has no chevron and no click: it REPORTS. It is here because "is my computer connected?" is a
      //    question somebody asks from wherever they are, and a mobile shell that simply omitted the answer
      //    would read as "this device has no daemon" rather than "you cannot set it up from here".
      h("div", { class: () => "zm-row zm-row-static" + (daemon.isOffered() ? "" : " is-off") },
        h("span", { class: "zm-row-t" },
          h("b", null, () => t("daemon.mobile.row")),
          h("small", null, () => (daemon.isConnected() ? t("daemon.ok.lead") : t("daemon.mobile.hint"))),
        ),
      ),

      // ── FEEDBACK, inline (one gesture, V2-100) ──
      h("button", { class: "zm-row", onClick: () => setFbOpen(!fbOpen()) },
        h("span", { class: "zm-row-t" },
          h("b", null, () => t("feedback.title")),
          h("small", null, () => t("mobile.feedback_sub")),
        ),
        raw(CHEV),
      ),
      // The form itself, at parity with the desktop panel (FeedbackForm.js). It scrolls into view when opened from
      // the dock's button.
      h("div", { ref: (el) => createEffect(() => { if (fbOpen() && store.mobileMenuOpen()) setTimeout(() => {
        try { el.scrollIntoView({ block: "start", behavior: "smooth" }); const ta = el.querySelector("textarea"); ta && ta.focus({ preventScroll: true }); } catch (_) {}
      }, 60); }) }, FeedbackForm(() => fbOpen() && store.mobileMenuOpen())),

      // ── THE ESCAPE HATCH. Persists the choice so index.html's picker stops redirecting this device.
      Row(() => t("mobile.desktop"), () => t("mobile.desktop_sub"),
        () => { try { localStorage.setItem("zaelar_shell", "desktop"); } catch (_) {} location.replace("/?desktop=1"); }),
    ),
  );
}

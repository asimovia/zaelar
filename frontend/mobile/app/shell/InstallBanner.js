// ============================================================================
// InstallBanner.js — the top-of-screen offer that makes the phone REACHABLE (V2-796).
//
// The agent works in the background on the server; what the phone has to be is a place a notice can land. On iOS
// that place exists only once the PWA is on the Home Screen (Safari tabs get no Web Push at all), and on Android an
// installed app is where the notification belongs. So this banner walks two steps, one at a time:
//
//   1. NOT INSTALLED → «Install zaelar on your phone».
//        · Chromium captured `beforeinstallprompt` → the button installs in ONE tap (`push.install()`).
//        · iOS has no install API → the banner shows the two steps (Share → Add to Home Screen) instead of a button
//          that would do nothing. Same for an Android browser that has not offered the prompt.
//   2. INSTALLED (or a browser that can push without installing) and notifications NOT DECIDED → «Turn on
//      notifications». The tap IS the permission prompt (it must be a gesture, and on iOS the gesture's own stack).
//
// Granted → nothing is shown and the subscription is refreshed silently on every load. Denied → nothing is shown
// either: re-asking a «no» is nagging, and the browser would refuse to ask again anyway. «Not now» hides the step
// for 7 days on this device. Every load reports the device state to the engine (`push.report()`), so a phone that
// cannot be reached shows up as such instead of silently missing every notice.
// ============================================================================

import { h } from "../../../app/core/dom.js?v=2";
import { createSignal } from "../../../app/core/reactive.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import * as push from "../../../app/services/push.js?v=1";
import { t } from "../../../app/core/i18n.js?v=1";
import { step } from "./install-step.js?v=1";

const SNOOZE_MS = 7 * 24 * 3600 * 1000;
const _key = (step) => `zaelar_banner_snooze_${step}`;
const _snoozed = (step) => { try { return Date.now() < Number(localStorage.getItem(_key(step)) || 0); } catch (_) { return false; } };
const _snooze = (step) => { try { localStorage.setItem(_key(step), String(Date.now() + SNOOZE_MS)); } catch (_) {} };


export function InstallBanner() {
  const [tick, setTick] = createSignal(0);
  const [busy, setBusy] = createSignal(false);
  const bump = () => setTick((n) => n + 1);
  push.onChange(bump);
  push.report();
  push.refresh();

  const current = () => {
    tick();
    if (!store.bootReady() || store.langOnboardOpen()) return "";      // never over the first-run gates
    return step({ installed: push.installed(), os: push.os(), canAsk: push.canAsk(),
                  snoozedInstall: _snoozed("install"), snoozedPush: _snoozed("push") });
  };

  const onInstall = async () => {
    if (busy()) return;
    setBusy(true);
    try { await push.install(); } finally { setBusy(false); bump(); }
  };
  const onEnable = async () => {
    if (busy()) return;
    setBusy(true);
    try { await push.enable(); } finally { setBusy(false); bump(); }
  };
  const later = (s) => () => { _snooze(s); bump(); };

  return h("div", {
    class: () => "zm-banner" + (current() ? " show" : ""),
    role: "region",
    "aria-live": "polite",
  },
    () => {
      const s = current();
      if (s === "install") {
        const oneTap = push.canInstall();
        return h("div", { class: "zm-banner-in" },
          h("p", { class: "zm-banner-t" }, t("install.title")),
          h("p", { class: "zm-banner-b" }, oneTap ? t("install.body")
            : (push.os() === "ios" ? t("install.ios_steps") : t("install.android_steps"))),
          h("div", { class: "zm-banner-a" },
            oneTap ? h("button", { class: "zm-primary", onClick: onInstall, disabled: () => busy() }, t("install.button")) : null,
            h("button", { class: "zm-ghost", onClick: later("install") }, t("install.later")),
          ));
      }
      if (s === "push") {
        return h("div", { class: "zm-banner-in" },
          h("p", { class: "zm-banner-t" }, t("push.title")),
          h("p", { class: "zm-banner-b" }, t("push.body")),
          h("div", { class: "zm-banner-a" },
            h("button", { class: "zm-primary", onClick: onEnable, disabled: () => busy() }, t("push.button")),
            h("button", { class: "zm-ghost", onClick: later("push") }, t("install.later")),
          ));
      }
      return null;
    },
  );
}

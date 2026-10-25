// install-step.js — which offer the install banner shows (V2-796). Pure, no imports, so a test runs it in Node.
//
//   "install" — a phone browser TAB. iOS can only receive Web Push once the PWA is on the Home Screen; Android can
//               push from a tab, but the notice belongs to the app, so installing is offered first.
//   "push"    — installed (or a browser that can push as it is) and notifications not decided yet.
//   ""        — nothing to offer: granted, denied (re-asking a «no» is nagging), unsupported, or snoozed.

export function step({ installed, os, canAsk, snoozedInstall, snoozedPush }) {
  if (!installed && os !== "desktop") {
    if (!snoozedInstall) return "install";
    return os === "android" && canAsk && !snoozedPush ? "push" : "";
  }
  return canAsk && !snoozedPush ? "push" : "";
}

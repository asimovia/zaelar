// SettingsSheet.js — the Settings PAGE: «a small configuration device» (operator), and small is the specification. The
// desktop's ConfigPanel sets an installation UP (keys, a model per module, providers); a phone USES one. So this page
// carries only what matters while using the agent from a pocket — language (server-side, both shells follow), theme,
// the speaker, the wake word, notifications, the permissions — and DELEGATES the rest with a row that opens the
// desktop version, instead of a worse copy of a panel that already works.

import { h } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import * as session from "../../../app/services/session.js?v=3";
import { createSignal } from "../../../app/core/reactive.js?v=2";
import { toggleTheme } from "../../../app/services/theme.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import * as push from "../../../app/services/push.js?v=1";
import * as consent from "./ai-consent.js?v=1";
import * as privacy from "../../../app/services/privacy.js?v=1";
import { inNativeApp } from "../../../app/core/native.js?v=1";
import { Page } from "./Page.js?v=1";
import * as wake from "./wake.js?v=1";
import { Row } from "./menu-row.js?v=1";
import { setPresenceOpen } from "./PresenceSheet.js?v=1";
import { currentEntry } from "../../../app/presence/PresenceLayer.js?v=1";
import { faceName } from "../../../app/presence/catalog-api.js?v=1";
import * as look from "../../../app/presence/look-state.js?v=1";
import { VolumeSlider } from "../../../app/components/VolumeSlider.js?v=1";

// A switch with its explaining line under the label (the «look at me» rows: what it does, or why it could not start).
function HintToggle(label, hint, get, onToggle, cls) {
  return h("button", { class: () => "zm-row zm-toggle " + cls + (get() ? " on" : ""), "aria-pressed": () => String(!!get()), onClick: onToggle },
    h("span", { class: "zm-row-t" }, h("b", null, label), h("small", null, hint)),
    h("span", { class: "zm-sw", "aria-hidden": "true" }),
  );
}

function Toggle(label, get, onToggle) {
  return h("button", { class: () => "zm-row zm-toggle" + (get() ? " on" : ""), onClick: onToggle },
    h("span", { class: "zm-row-t" }, h("b", null, label)),
    h("span", { class: "zm-sw", "aria-hidden": "true" }),
  );
}

// Language names, for the codes this install actually has. Kept as a small map with a fall-through to the raw code
// so a language the operator GENERATED (V2-089/V2-101) still appears — as "PT" rather than "Português", which is
// worse than nothing but far better than being absent from the list.
const LANG_NAME = { en: "English", es: "Español", ca: "Català", fr: "Français", de: "Deutsch", it: "Italiano",
                    pt: "Português", nl: "Nederlands", ja: "日本語", zh: "中文" };

function NotifyRow() {
  const [p, setP] = createSignal(push.permission());
  push.onChange(() => setP(push.permission()));
  const on = () => p() === "granted";
  const sub = () => (!push.supported() ? (push.os() === "ios" && !push.installed() ? t("install.ios_steps") : "")
    : p() === "denied" ? t("push.denied") : on() ? t("push.settings_on") : t("push.settings_off"));
  return h("button", {
    class: "zm-row",
    onClick: async () => { if (on()) await push.test(); else if (push.supported()) setP(await push.enable()); },
  },
    h("span", { class: "zm-row-t" },
      h("b", null, () => t("push.settings_label")),
      h("small", null, () => sub()),
    ),
    h("span", { class: "zm-row-v" }, () => (on() ? t("push.test") : (push.canAsk() ? t("push.button") : ""))),
  );
}

export function SettingsSheet() {
  const [langs, setLangs] = createSignal([]);
  // The list of installed languages is server truth, not a hardcoded constant. Fetched once when the sheet is
  // built; `available` is whatever bundles exist on THIS install.
  fetch("/api/i18n/state", { cache: "no-store" }).then(r => r.json())
    .then(st => setLangs(Array.isArray(st && st.available) ? st.available : []))
    .catch(() => {});

  // Switching language goes through POST /api/i18n/choose/{code} — the SERVER owns the active language
  // (ZAELAR_LANGUAGE), and it answers by emitting the SSE `language` event that makes every t() in BOTH shells
  // re-render. Calling applyLang() directly from here would change this browser and leave the agent — and the
  // desktop tab on the same account — speaking the old one.
  const pick = (code) => { fetch("/api/i18n/choose/" + encodeURIComponent(code), { method: "POST" }).catch(() => {}); };

  const close = () => store.setMobileSettingsOpen(false);
  return Page({ id: "settings", open: store.mobileSettingsOpen, title: () => t("mobile.settings"), close,
    back: () => { close(); store.setMobileMenuOpen(true); } },
    h("div", { class: "zm-rows" },
      // ── LANGUAGE. `available()` is whatever bundles this install actually has, never a hardcoded list: a
      //    language the operator generated (V2-089/V2-101) has to appear here without anyone editing this file.
      h("label", { class: "zm-row zm-select" },
        h("span", { class: "zm-row-t" }, h("b", null, () => t("config.language"))),
        h("select", { onChange: (e) => pick(e.target.value) },
          () => langs().map((code) => h("option", {
            value: code, selected: code === store.lang() ? "" : false,
          }, LANG_NAME[code] || String(code).toUpperCase())),
        ),
      ),

      Toggle(() => t("config.theme_dark"),
        () => store.theme() === "dark",
        toggleTheme),

      // ── PRESENCE (V2-928 T11): the agent's face — which one and how it looks, on its own page (PresenceSheet.js).
      Row(null, () => t("config.tab.presence"), () => faceName(currentEntry()), () => { close(); setPresenceOpen(true); }),

      // ── THE SPEAKER LIVES HERE NOW (V2-573, 2026-09-04). Until the dock restyle it had its own button one tap
      //    away, and this sheet said — correctly, then — that a duplicate would be clutter. The restyle removed
      //    that button, so this row is not a duplicate any more: it is the ONLY way to silence zaelar's voice,
      //    and a control that exists nowhere is worse than one that takes two taps.
      //    It reads and writes the same signal the desktop's 🔊 icon does (`session.toggleBotMute`, the single
      //    owner of silence since V2-087/V2-088), never a second switch — that seam is why the icon and the
      //    server's synthesis cannot disagree.
      Toggle(() => t("mobile.speaker"),          // a row's label, never the desktop's «click to…» tooltip (V2-876 P-14)
        () => !store.botMuted(),
        () => (store.botMuted() && session.openSpeakerHere ? session.openSpeakerHere("settings") : session.toggleBotMute())),
      VolumeSlider("zm-row zm-vol", true),     // V2-930: his voice's level on this phone, the door his voice also takes

      // ── THE WAKE WORD (V2-876 D-C: its dock slot went to Apps). The desktop orb's 🤖, the same seam (wake.js).
      Toggle(() => t("mobile.wake_word", { name: store.assistantName() }), wake.on, wake.toggle),

      // ── V2-796 — can this phone be reached when zaelar is closed? Tapping asks (a gesture, as iOS requires);
      //    once on, the same row sends a test notice so «is it working?» has an answer.
      NotifyRow(),

      // Captions have no row either: the operator removed subtitles from this shell entirely (V2-573), band and
      // button both. `store.captionsOn` still exists and still drives the DESKTOP; adding a phone control for a
      // surface this shell does not render would be a switch that does nothing visible.

      // ── V2-875 — PERMISSIONS, the agent's (every device of it shares them): location into its state, reading
      //    files, keeping its events for debugging, tagging personal data in what is kept. services/privacy.js.
      h("div", { class: "zm-procs-t" }, () => t("config.sec.permissions")),
      ...privacy.KEYS.map((k) => Toggle(() => t(`config.perm.${k}`), () => !!privacy.values()[k], () => privacy.set(k, !privacy.values()[k]))),
      // ── V2-870, NATIVE APP ONLY: the yes to the AI services, withdrawable here (withdrawing ends this screen's
      //    voice; nothing reaches the AI services again until a new yes).
      () => inNativeApp() ? Toggle(() => t("consent.settings_label"), () => consent.accepted(),
        () => (consent.accepted() ? consent.decide(false).then((ok) => { if (ok && session.stop) session.stop(); })
                                  : consent.setSheetOpen(true))) : null,

      // ── DELEGATED, not hidden.
      h("button", {
        class: "zm-row",
        onClick: () => { try { localStorage.setItem("zaelar_shell", "desktop"); } catch (_) {} location.replace("/?desktop=1"); },
      },
        h("span", { class: "zm-row-t" },
          h("b", null, () => t("mobile.full_settings")),
          h("small", null, () => t("mobile.full_settings_sub")),
        ),
      ),

      // ── «LOOK AT ME» (V2-928 T10), last: the face turns to the person — the front camera (on the phone, nothing
      //    sent), and in the iPhone app the AirPods' head motion, a row that exists only when the app says it can.
      h("div", { class: "zm-procs-t" }, () => t("config.tab.presence")),
      HintToggle(() => t("presence.camera"),
        () => t(look.cameraProblem() ? look.CAMERA_PROBLEM[look.cameraProblem()] || look.CAMERA_PROBLEM.unavailable : "presence.camera_hint"),
        look.lookCamera, () => look.setLookCamera(!look.lookCamera(), "settings"), "zm-look-cam"),
      () => (look.probeAirpods(), look.airpodsAvailable()) ? HintToggle(() => t("presence.airpods"),
        () => t(look.airpodsProblem() ? look.AIRPODS_PROBLEM[look.airpodsProblem()] || look.AIRPODS_PROBLEM.unavailable : "presence.airpods_hint"),
        look.lookAirpods, () => look.setLookAirpods(!look.lookAirpods(), "settings"), "zm-look-airpods") : null,
    ),
  );
}

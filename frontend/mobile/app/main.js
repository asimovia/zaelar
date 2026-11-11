// mobile/app/main.js — ENTRY POINT OF THE PHONE SHELL (V2-124), the counterpart of app/main.js: the SAME engine through
// the SAME services and store (imported, never forked), a different screen — the Deck host, the dock, the pages, the
// CSS, the PWA plumbing. Order matters as on the desktop: the deck wrapper before the Deck, the dock before --dock-h.

import { h, mount, $ } from "../../app/core/dom.js?v=2";
import { createEffect } from "../../app/core/reactive.js?v=2";
import * as store from "../../app/core/store.js?v=2";
import * as firstRun from "../../app/core/first-run.js?v=1";
import * as session from "../../app/services/session.js?v=3";
import * as mic from "../../app/services/mic.js?v=1";
import * as screens from "../../app/services/screens.js?v=1";
import { openSSE } from "../../app/services/sse.js?v=6";
import * as api from "../../app/services/api.js?v=2";
import { startStatusPolling } from "../../app/services/status.js?v=2";
import { initTheme } from "../../app/services/theme.js?v=2";
import { initI18n, t } from "../../app/core/i18n.js?v=1";
import { submitChat } from "../../app/components/ChatWall.js?v=5";

import { Deck } from "./shell/Deck.js?v=5";
import { initKeyboard } from "./shell/keyboard.js?v=2";
import { MOBILE_SURFACES } from "./shell/mobile-surfaces.js?v=4";
import * as consent from "./shell/ai-consent.js?v=1";
import { setAppsOpen } from "./shell/AppsPane.js?v=2";
import { onePageAtATime, backFromPage } from "./shell/pages.js?v=1";
import * as privacy from "../../app/services/privacy.js?v=1";   // V2-875: his switches; location → the state

// ---- theme + language before mounting anything, so nothing flashes the wrong palette or the wrong words ----
initTheme();
initI18n();

// ---- the deck wrapper. ONE structural div, versus the desktop's #desk/.canvas/#wstage/#activity stack: there is
// nothing to place here, so there is nothing to build a coordinate system for. ----
const wrap = mount(h("div", { id: "zm-deck-wrap" }));
mount(h("div", { class: "zm-bg" }), wrap);                 // the canvas backdrop, purely decorative
const stage = mount(h("div", { id: "zm-stage" }), wrap);

// ---- A PHONE DOES NOT INHERIT SILENCE (V2-573) -------------------------------------------------------------
// `hb_bot_muted` is written by BOTH the speaker toggle and `power.setPower()` — stopping the agent from the dock
// persists "1". So: stop the agent on the phone, start it again later from the computer, open the app, and the
// phone comes up with the agent LIVE and its own output muted, hydrated from a decision made in another session
// about a different situation. Everything looks healthy and nothing can be heard. That is the operator's
// «i couldn't listen to the voice in mobile», and it is now impossible: on this shell a page load starts with the
// voice ON, and silencing is a decision taken IN the session you are in (the toggle lives in the config sheet).
//
// Deliberately mobile-only. The desktop keeps its persisted preference — it is a machine you sit at, with the
// speaker icon permanently on screen, so there the memory is a convenience instead of a trap.
try {
  if (localStorage.getItem("hb_bot_muted") === "1") {
    store.setBotMuted(false);
    localStorage.setItem("hb_bot_muted", "0");
    api.uiEvent("mobile:voice_unmuted_on_boot", {});
  }
} catch (_) {}

const botAudio = mount(h("audio", { id: "botaudio", autoplay: true, playsinline: true }));
session.attachBotAudio(botAudio);
// Reactive icon↔audio binding: the <audio> ALWAYS reflects botMuted(), the same signal the speaker toggle paints.
// Never "icon says muted but sound comes out" (the V2-043 startup bug).
createEffect(() => { try { botAudio.muted = store.botMuted(); } catch (_) {} });

// ---- native mobile surfaces, mounted from the canonical list (shell/mobile-surfaces.js) ----
for (const s of MOBILE_SURFACES.filter((s) => s.phase === "scaffold")) mount(s.comp(), s.target === "deck" ? wrap : undefined);
for (const s of MOBILE_SURFACES.filter((s) => s.phase === "overlay")) mount(s.comp(), s.target === "deck" ? wrap : undefined);

// The inline splash in mobile/index.html did its job (a loader from the FIRST byte, which on a cold-started instance
// is tens of seconds); the BootOverlay takes over. If this module had failed to load, #preboot would stay — better
// a loader than a black screen.
// V2-558 — the ring closes on a FACT, not on a clock: `__zaelarPrebootDone` paints it full and says
// "Ready", and only then does the splash go. Guarded because preboot.js is a separate file and a shell that
// failed to load it must still be able to get rid of its own splash.
try { window.__zaelarPrebootDone?.(); } catch { /* noop */ }
try { document.getElementById("preboot")?.remove(); } catch { /* noop */ }

// ---- CLOUD profile + Energy balance: same retry loop as the desktop, for the same reason. On the COLD START of an
// instance these endpoints answer 503 until FastAPI finishes coming up; a single failed attempt would leave
// `cloudProfile` false FOREVER and the menu would hide the account row when ZAELAR_USER_ID is set. ----
(async () => {
  for (let i = 0; i < 45; i++) {
    try {
      const cfg = await api.getConfig();
      if (cfg) { store.setCloudProfile(!!cfg.cloud_profile); store.setAccountUrl(cfg.account_url || ""); consent.loadFrom(cfg); privacy.loadFrom(cfg, () => !consent.pending()); return; }
    }
    catch { /* 503 while the instance boots: retry */ }
    await new Promise((r) => setTimeout(r, 2000));
  }
})();
(async () => {
  for (let i = 0; i < 45; i++) {
    try {
      const r = await fetch("/api/energy", { cache: "no-store" });
      if (r.ok) {
        const e = await r.json();
        store.setEnergy(e);
        if (e.account_url) store.setAccountUrl(e.account_url);
        return;
      }
    } catch { /* still booting: retry */ }
    await new Promise((r) => setTimeout(r, 2000));
  }
})();

// ---- V2-101 first-run language onboarding: identical gate to the desktop's (checked ONCE after bootReady flips).
// It matters MORE here: a phone is plausibly the first place someone ever opens their agent. ----
// V2-765: retried until the engine answers — with no language the agent stays stopped, so a picker that
// never opens would be a dead agent behind no screen at all.
// Any reset (not only a factory one) puts the browser's switches back to a fresh install's: the engine bumps a
// wipe epoch on every reset and first-run.js sweeps our namespace once per epoch (operator, 2026-09-25).
firstRun.takeoverOnReset({
  fetchEpoch: () => fetch("/api/desktop/epoch", { cache: "no-store" }).then(r => r.json()).then(j => j && j.epoch),
  local: localStorage, session: sessionStorage, reload: () => location.reload(),
}).catch(() => {});
let _langOnboardChecked = false;
async function _langStateUntilAnswered() {
  for (let i = 0; i < 90; i++) {
    try {
      const r = await fetch("/api/i18n/state", { cache: "no-store" });
      if (r.ok) return await r.json();
    } catch { /* the instance is still waking */ }
    await new Promise((res) => setTimeout(res, 2000));
  }
  return null;
}
createEffect(() => {
  if (_langOnboardChecked || !store.bootReady()) return;
  _langOnboardChecked = true;
  _langStateUntilAnswered().then((s) => {
    if (s && s.chosen === false) store.setLangOnboardOpen(true);
  });
});

// ---- THE HOST. `openSSE(deck)` is the whole point of the split: sse.js does not know which shell it is driving,
// so the brain's show/close/confirm/refresh reach the phone with zero changes to that file. ----
const deck = new Deck(stage);
window.__zaelarDesktop = deck;      // the name the SSE/session bridge looks for (session-lk.js). Kept AS IS
                                    // deliberately: renaming it would mean editing the shared session module to
                                    // teach it about a second shell, which is exactly the coupling this avoids.
window.__zaelarDeck = deck;         // …plus an honest alias, for anything mobile-only that comes later.
initKeyboard();                      // a field focused in a card: the deck fits above the keyboard (V2-813)
createEffect(() => deck.setRunning(!store.powerOff()));
// V2-613: same hook as the desktop host — a language switch re-renders every open card's own chrome, live.
createEffect(() => { t(""); deck.relanguage(); });
openSSE(deck);
deck.restore();

// ---- the orb's two canvases are inside the dock; startVisuals only needs the elements ----
session.startVisuals({ orbCanvas: $("#orb"), vizCanvas: $("#viz") });

// ---- ALWAYS-ON voice. Identical to the desktop's: browsers require a user gesture for the mic, so we also
// (re)connect on any pointer interaction while the session is down. Idempotent, and it respects the ONE exception —
// an explicit, persisted ⏻ off, or the very tap on ⏻ would re-arm the session it just stopped. ----
// Loading the phone TAKES the voice (operator, 2026-10-24): its mic and speaker come on here and the other surface
// turns its own off (services/session-lk.js, «one voice, claimed by hand»). Set before the first start() below.
if (session.claimOnNextStart && !store.powerOff()) {
  session.claimOnNextStart();
  mic.setMuted(false, "mobile-load");
}
function ensureVoice() {
  if (store.powerOff()) return;
  if (store.powerOnPending()) return;               // V2-792 §9: the ⏻ is switching the server on; it starts the voice itself
  if (store.langOnboardOpen()) return;              // V2-765: nothing listens while the language picker is up
  if (consent.pending()) return;                    // V2-870: inside the app, nothing listens before the yes
  if (!store.started() && !store.starting()) session.start().catch(() => {});
}
// V2-765 — the language picker lifts the gate: the `run` event drops `powerOff`, and this brings the voice up
// without waiting for another tap; the mic and speaker the boot probe muted come back as with ⏻ ON.
createEffect(() => {
  if (store.powerOff() || store.langOnboardOpen() || consent.pending()) return;
  ensureVoice();
});
document.addEventListener("hb:language-ready", () => {
  mic.setMuted(false, "language-ready");
  store.setBotMuted(false); try { localStorage.setItem("hb_bot_muted", "0"); } catch { /* private window */ }
});
if (store.powerOff()) store.setBootReady(true);   // nothing to wait for: don't leave the veil stuck (same as desktop)
ensureVoice();
// `pointerdown`, not `touchstart`: iOS requires a user gesture for the mic, and pointerdown fires for both.
window.addEventListener("pointerdown", ensureVoice);

// ---- …and the same gesture UNLOCKS PLAYBACK (V2-573): a mobile browser plays no remote track before a user gesture,
// and the voice connects at LOAD. Synchronous up to the SDK call — awaiting first spends the user activation. ----
window.addEventListener("pointerdown", () => { try { session.unlockAudio(); } catch (_) {} });

// The voice lock (one live voice session per machine) is surfaced by the shared DormantVeil, face "moved".

// ---- reconcile with the SERVER's truth about the global switch (V2-092), in the SAFE direction ----
// Identical logic to app/main.js, including the timestamp guard: this reply is a SNAPSHOT of when it was asked, not
// of when it arrives. On a machine waking from cold that is seconds, and the operator — staring at the screen
// precisely because it will not start — presses ⏻ inside that window. The slowest message must not beat the newest.
(async () => {
  try {
    const askedAt = Date.now();
    const r = await api.runState();
    if (!r || typeof r.running !== "boolean") return;
    if (store.powerCmdAt() > askedAt) return;
    // V2-654: through the door. The note below already named this exact failure — «the phone would paint itself
    // off with the mic open — the state that lies» — and this line was still only painting.
    if (!r.running) { store.setPowerOff(true); mic.setMuted(true, "boot-not-running"); store.setBotMuted(true); }
    else if (store.powerOff()) api.runStop();
  } catch { /* the server isn't answering yet: local state already applied */ }
})();

// STOPPED ⇒ NO VOICE SESSION, whoever gave the order (this dock, the seed above, or an SSE `run` event from the
// desktop tab). Without this the phone would paint itself off with the mic open — the state that lies, again.
createEffect(() => {
  if (!store.powerOff()) return;
  store.setBootReady(true);
  if (store.started() || store.starting()) { try { session.stop(); } catch (_) {} }
});

// ---- CLIENT STATE → observability. Same two events as the desktop, plus `shell:"mobile"` so a run can be told
// apart in the log: "it worked on the computer and not on the phone" must be answerable from the timeline. ----
let _prevAgentState = null;
createEffect(() => {
  const s = store.agentState();
  if (s === _prevAgentState) return;
  const prev = _prevAgentState;
  _prevAgentState = s;
  api.uiState("agent:state", { state: s, prev: prev || "none", shell: "mobile" });
});
try {
  document.addEventListener("visibilitychange", () => {
    // On a phone this is not an edge case, it is the normal life of the app: every incoming call, every switch to
    // another app. Without it, "it froze" and "you were in WhatsApp" are indistinguishable in the log.
    api.uiState("tab:visibility", { state: document.hidden ? "hidden" : "visible", shell: "mobile" });
  });
} catch (_) {}

onePageAtATime();                    // every shell surface is a page; never two at once (shell/pages.js)

// ---- ANDROID BACK BUTTON / iOS swipe-back. In a standalone PWA there is nowhere to go back TO, so an unhandled
// back gesture closes the app — losing the session over a reflex. Intercepted: back closes the top-most open
// surface, and only exits when there is nothing left to close. ----
function topMostClose() {
  if (backFromPage()) return true;
  // On a card, back goes HOME (the card stays open as a tile), as in any phone app; on the home it leaves the app.
  if (deck.at >= 0) return deck.home(), true;
  return false;
}
try {
  history.pushState({ zm: 1 }, "");
  window.addEventListener("popstate", () => {
    const handled = topMostClose();
    // Re-arm the trap either way: one entry always sits ahead of us, so the NEXT back press is ours too. If nothing
    // was open we still re-arm and simply do nothing — leaving the app is then the operator's second press.
    history.pushState({ zm: 1 }, "");
    if (!handled) api.uiEvent("mobile:back_noop", {});
  });
} catch (_) {}

// ---- system-status poller (keeps the agent-state signals live even with everything closed) + the voice catalog ----
startStatusPolling();
// V2-792 — this screen tells the server whether it is visible and touched (how it knows the active screen).
screens.wireScreen();
session.loadVoices();

// ---- manual control surface, mobile edition. Same shape as window.zaelar on the desktop so anything that scripts
// the UI (tests, the operator's console) works in both shells. ----
window.zaelar = {
  show: (id, q = "") => deck.show(id, { q, by: "console" }),
  close: (id) => (id ? deck.close(id, { by: "console" }) : deck.closeAll({ by: "console" })),
  next: () => deck.next(),
  prev: () => deck.prev(),
  home: () => deck.home(),
  chat: (text) => submitChat(text),
  panel: () => store.setChatOpen(true),
  apps: () => setAppsOpen(true),
  menu: () => store.setMobileMenuOpen(true),
  shell: "mobile",
};

// ---- /m?widget=<id> — the same deep link the desktop honours, which is also how a PWA shortcut can open straight
// into a widget (manifest.webmanifest `shortcuts`). ----
(function () {
  const w = new URLSearchParams(location.search).get("widget");
  if (w) setTimeout(() => deck.show(w, { by: "url" }), 700);
})();
